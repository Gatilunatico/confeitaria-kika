-- DoceFlow · 010 · Fluxo completo de pedidos (Etapa 4)
-- Rodar depois da 009. Idempotente e não destrutiva.
--
-- 1. Status inicial passa a ser "Aguardando confirmação" (antes "Recebido"): o pedido só
--    vale depois que a confeitaria confirma disponibilidade e preço final.
-- 2. orders.endereco_entrega: obrigatório quando a modalidade é Entrega.
-- 3. order_items.subtotal: calculado pelo banco (preço registrado × quantidade).
-- 4. order_history: histórico de alterações (status, valor final, data, observações internas),
--    gravado por gatilho. Ninguém escreve nele pelo app; a administradora só lê.
-- 5. criar_pedido ganha p_endereco_entrega e valida modalidade e endereço no servidor.
--
-- Mapeamento para a especificação (nomes mantidos do schema existente):
--   cliente_telefone → cliente_whatsapp · data_desejada → data_entrega
--   valor_total → valor_estimado ("a partir de", calculado no servidor) · criado_em → created_at
--   atualizado_em → updated_at · product_id → produto_id · nome_produto → produto_nome

-- ---------------------------------------------------------------- status
alter table public.orders drop constraint if exists orders_status_check;
update public.orders set status = 'Aguardando confirmação' where status = 'Recebido';
alter table public.orders alter column status set default 'Aguardando confirmação';
alter table public.orders add constraint orders_status_check
    check (status in ('Aguardando confirmação', 'Confirmado', 'Em produção', 'Pronto', 'Entregue', 'Cancelado'));

-- ---------------------------------------------------------------- endereço e subtotal
alter table public.orders add column if not exists endereco_entrega text not null default '';
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'orders_endereco_entrega_check') then
        alter table public.orders add constraint orders_endereco_entrega_check
            check (char_length(endereco_entrega) <= 300);
    end if;
end $$;

alter table public.order_items add column if not exists subtotal numeric(12, 2)
    generated always as (preco_unitario * quantidade) stored;

-- ---------------------------------------------------------------- histórico de alterações
create table if not exists public.order_history (
    id             bigint generated always as identity primary key,
    order_id       uuid not null,
    confeitaria_id uuid not null,
    campo          text not null check (campo in ('criado', 'status', 'valor_final', 'data_entrega',
                                                  'observacoes_internas')),
    valor_anterior text,
    valor_novo     text,
    alterado_por   uuid,               -- auth.uid() da administradora; null = cliente pelo site
    alterado_em    timestamptz not null default now(),
    foreign key (order_id, confeitaria_id) references public.orders (id, confeitaria_id) on delete cascade
);
create index if not exists order_history_order_idx on public.order_history (order_id, alterado_em);

alter table public.order_history enable row level security;
revoke all on public.order_history from anon, authenticated;
grant select on public.order_history to authenticated;
drop policy if exists order_history_admin_read on public.order_history;
create policy order_history_admin_read on public.order_history
    for select to authenticated using (public.is_store_admin(confeitaria_id));

create or replace function public.registrar_historico_pedido()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_quem uuid := auth.uid();
begin
    if tg_op = 'INSERT' then
        insert into public.order_history (order_id, confeitaria_id, campo, valor_novo, alterado_por)
        values (new.id, new.confeitaria_id, 'criado', new.status, v_quem);
        return new;
    end if;
    if new.status is distinct from old.status then
        insert into public.order_history (order_id, confeitaria_id, campo, valor_anterior, valor_novo, alterado_por)
        values (new.id, new.confeitaria_id, 'status', old.status, new.status, v_quem);
    end if;
    if new.valor_final is distinct from old.valor_final then
        insert into public.order_history (order_id, confeitaria_id, campo, valor_anterior, valor_novo, alterado_por)
        values (new.id, new.confeitaria_id, 'valor_final', old.valor_final::text, new.valor_final::text, v_quem);
    end if;
    if new.data_entrega is distinct from old.data_entrega then
        insert into public.order_history (order_id, confeitaria_id, campo, valor_anterior, valor_novo, alterado_por)
        values (new.id, new.confeitaria_id, 'data_entrega', old.data_entrega::text, new.data_entrega::text, v_quem);
    end if;
    if new.observacoes_internas is distinct from old.observacoes_internas then
        insert into public.order_history (order_id, confeitaria_id, campo, valor_anterior, valor_novo, alterado_por)
        values (new.id, new.confeitaria_id, 'observacoes_internas', old.observacoes_internas,
                new.observacoes_internas, v_quem);
    end if;
    return new;
end;
$$;
revoke all on function public.registrar_historico_pedido() from public, anon, authenticated;

drop trigger if exists orders_historico on public.orders;
create trigger orders_historico after insert or update on public.orders
    for each row execute function public.registrar_historico_pedido();

-- ---------------------------------------------------------------- criar_pedido (fluxo público)
-- Substitui a versão da 007 (assinatura nova com p_endereco_entrega).
drop function if exists public.criar_pedido(text, text, text, date, text, text, jsonb, text, boolean);

create or replace function public.criar_pedido(
    p_confeitaria_slug text,
    p_cliente_nome     text,
    p_cliente_whatsapp text,
    p_data_entrega     date,
    p_modalidade       text,
    p_observacoes      text,
    p_itens            jsonb,
    p_origem           text,
    p_consentimento    boolean,
    p_endereco_entrega text default ''
)
returns table (id uuid, protocolo text, criado boolean, status text, valor_estimado numeric,
               confeitaria_nome text, confeitaria_whatsapp text)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
#variable_conflict use_column
declare
    v_conf      public.confeitarias%rowtype;
    v_prod      public.produtos%rowtype;
    v_item      jsonb;
    v_qtd       integer;
    v_slugs     text[] := '{}';
    v_chaves    text[] := '{}';
    v_total     numeric(10, 2) := 0;
    v_sem_preco boolean := false;
    v_nome      text := regexp_replace(btrim(coalesce(p_cliente_nome, '')), '\s+', ' ', 'g');
    v_obs       text := btrim(coalesce(p_observacoes, ''));
    v_endereco  text := regexp_replace(btrim(coalesce(p_endereco_entrega, '')), '\s+', ' ', 'g');
    v_origem    text := coalesce(nullif(lower(btrim(p_origem)), ''), 'site');
    v_hoje      date := ((now() at time zone 'UTC') - interval '3 hours')::date;
    v_fp        text;
    v_id        uuid;
    v_criado    boolean := false;
begin
    select * into v_conf from public.confeitarias c where c.slug = p_confeitaria_slug and c.ativo;
    if not found then
        raise exception 'confeitaria_invalida' using errcode = '22023';
    end if;
    if p_consentimento is not true then
        raise exception 'consentimento_obrigatorio' using errcode = '22023';
    end if;
    if p_data_entrega is null or p_data_entrega < v_hoje or p_data_entrega > v_hoje + 365 then
        raise exception 'data_invalida' using errcode = '22023';
    end if;
    if p_modalidade is null or p_modalidade not in ('Retirada', 'Entrega') then
        raise exception 'modalidade_invalida' using errcode = '22023';
    end if;
    if p_modalidade = 'Entrega' then
        if char_length(v_endereco) < 10 then
            raise exception 'endereco_obrigatorio' using errcode = '22023';
        end if;
        if char_length(v_endereco) > 300 then
            raise exception 'endereco_invalido' using errcode = '22023';
        end if;
    else
        v_endereco := '';  -- retirada: não guarda endereço (minimização de dados)
    end if;
    if p_itens is null or jsonb_typeof(p_itens) <> 'array'
       or jsonb_array_length(p_itens) < 1 or jsonb_array_length(p_itens) > 20 then
        raise exception 'itens_invalidos' using errcode = '22023';
    end if;
    if v_origem !~ '^[a-z0-9_-]{1,40}$' then
        v_origem := 'site';
    end if;

    -- Cada item: produto da MESMA confeitaria, publicado, disponível e com quantidade permitida.
    -- Nome e preço vêm SEMPRE do banco (o navegador só informa slug e quantidade).
    for v_item in select * from jsonb_array_elements(p_itens) loop
        if jsonb_typeof(v_item -> 'quantidade') <> 'number' then
            raise exception 'quantidade_invalida' using errcode = '22023';
        end if;
        v_qtd := (v_item ->> 'quantidade')::integer;
        select * into v_prod from public.produtos pr
         where pr.confeitaria_id = v_conf.id and pr.slug = (v_item ->> 'produto_slug') and pr.publicado;
        if not found then
            raise exception 'produto_invalido' using errcode = '22023';
        end if;
        if not v_prod.disponivel then
            raise exception 'produto_indisponivel' using errcode = '22023';
        end if;
        if v_qtd < v_prod.qtd_min or v_qtd > v_prod.qtd_max then
            raise exception 'quantidade_invalida' using errcode = '22023';
        end if;
        if v_prod.slug = any(v_slugs) then
            raise exception 'itens_repetidos' using errcode = '22023';
        end if;
        v_slugs := v_slugs || v_prod.slug;
        v_chaves := v_chaves || (v_prod.id::text || ':' || v_qtd);
        if v_prod.preco is null or v_prod.tipo_preco = 'sob_consulta' then
            v_sem_preco := true;
        else
            v_total := v_total + v_prod.preco * v_qtd;
        end if;
    end loop;

    v_fp := md5(concat_ws('|', p_cliente_whatsapp, p_data_entrega::text, p_modalidade,
                          (select string_agg(k, ',' order by k) from unnest(v_chaves) k)));
    select o.id into v_id from public.orders o where o.confeitaria_id = v_conf.id and o.fingerprint = v_fp;

    if v_id is null then
        perform public.verificar_limite_envios(v_conf.id, p_cliente_whatsapp);
        insert into public.orders (protocolo, confeitaria_id, cliente_nome, cliente_whatsapp, data_entrega,
                                   modalidade, endereco_entrega, observacoes, valor_estimado, origem,
                                   consentimento, fingerprint)
        values ('PD-' || to_char((now() at time zone 'UTC') - interval '3 hours', 'YYMMDD') || '-'
                    || upper(substr(md5(gen_random_uuid()::text), 1, 6)),
                v_conf.id, v_nome, p_cliente_whatsapp, p_data_entrega, p_modalidade, v_endereco, v_obs,
                case when v_sem_preco then null else v_total end, v_origem, true, v_fp)
        returning orders.id into v_id;
        insert into public.order_items (order_id, confeitaria_id, produto_id, produto_nome, unidade, quantidade,
                                        preco_unitario, tipo_preco)
        select v_id, v_conf.id, pr.id, pr.nome, pr.unidade, (i ->> 'quantidade')::integer,
               case when pr.tipo_preco = 'sob_consulta' then null else pr.preco end, pr.tipo_preco
          from jsonb_array_elements(p_itens) i
          join public.produtos pr on pr.confeitaria_id = v_conf.id and pr.slug = (i ->> 'produto_slug');
        v_criado := true;
    end if;

    return query
        select o.id, o.protocolo, v_criado, o.status, o.valor_estimado, v_conf.nome, v_conf.whatsapp
          from public.orders o where o.id = v_id;
end;
$$;
revoke all on function public.criar_pedido(text, text, text, date, text, text, jsonb, text, boolean, text) from public;
grant execute on function public.criar_pedido(text, text, text, date, text, text, jsonb, text, boolean, text)
    to anon, authenticated;
