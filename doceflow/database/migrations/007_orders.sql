-- DoceFlow · 007 · Pedidos (orders + order_items) e limites contra abuso nos fluxos públicos
-- Rodar depois da 006. Idempotente e não destrutiva.
--
-- Visitante (anon): NÃO lê nem grava orders/order_items diretamente. Registra pedidos só
--   pela função criar_pedido (SECURITY DEFINER), que valida tudo e devolve só o próprio pedido.
-- Administradora: lê os pedidos da própria confeitaria e atualiza status, valor final,
--   data de entrega e observações internas.
-- Consistência multi-tenant: itens, produtos e lead de origem sempre da mesma confeitaria
--   (chaves estrangeiras compostas com confeitaria_id).
-- Limites: 5 envios/hora por WhatsApp e 30 envios/minuto por confeitaria (pedidos e orçamentos).

create table if not exists public.orders (
    id                   uuid primary key default gen_random_uuid(),
    protocolo            text not null unique,
    confeitaria_id       uuid not null references public.confeitarias (id) on delete cascade,
    lead_id              uuid,
    cliente_nome         text not null check (char_length(cliente_nome) between 2 and 80),
    cliente_whatsapp     text not null check (cliente_whatsapp ~ '^55[0-9]{10,11}$'),
    data_entrega         date not null,
    modalidade           text not null check (modalidade in ('Retirada', 'Entrega')),
    observacoes          text not null default '' check (char_length(observacoes) <= 500),
    observacoes_internas text not null default '' check (char_length(observacoes_internas) <= 1000),
    status               text not null default 'Recebido'
                         check (status in ('Recebido', 'Confirmado', 'Em produção', 'Pronto', 'Entregue', 'Cancelado')),
    valor_estimado       numeric(10, 2) check (valor_estimado is null or valor_estimado >= 0),
    valor_final          numeric(10, 2) check (valor_final is null or valor_final >= 0),
    origem               text not null default 'site' check (origem ~ '^[a-z0-9_-]{1,40}$'),
    consentimento        boolean not null check (consentimento),
    consentimento_em     timestamptz not null default now(),
    fingerprint          text not null,
    status_atualizado_em timestamptz,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    unique (id, confeitaria_id),
    unique (confeitaria_id, fingerprint),
    foreign key (lead_id, confeitaria_id) references public.leads (id, confeitaria_id)
);
create index if not exists orders_confeitaria_created_idx on public.orders (confeitaria_id, created_at desc);
create index if not exists orders_whatsapp_created_idx on public.orders (confeitaria_id, cliente_whatsapp, created_at desc);

create table if not exists public.order_items (
    id             uuid primary key default gen_random_uuid(),
    order_id       uuid not null,
    confeitaria_id uuid not null,
    produto_id     uuid not null,
    produto_nome   text not null,           -- snapshot no momento do pedido
    unidade        text not null,
    quantidade     integer not null check (quantidade > 0),
    preco_unitario numeric(10, 2) check (preco_unitario is null or preco_unitario >= 0),  -- "a partir de"
    tipo_preco     text not null check (tipo_preco in ('a_partir_de', 'estimado', 'sob_consulta')),
    created_at     timestamptz not null default now(),
    foreign key (order_id, confeitaria_id) references public.orders (id, confeitaria_id) on delete cascade,
    foreign key (produto_id, confeitaria_id) references public.produtos (id, confeitaria_id) on delete restrict
);
create index if not exists order_items_order_idx on public.order_items (order_id);

drop trigger if exists orders_updated_at on public.orders;
create trigger orders_updated_at before update on public.orders
    for each row execute function public.set_updated_at();
drop trigger if exists orders_status_atualizado_em on public.orders;
create trigger orders_status_atualizado_em before update of status on public.orders
    for each row execute function public.set_status_atualizado_em();

alter table public.orders enable row level security;
alter table public.order_items enable row level security;
revoke all on public.orders, public.order_items from anon, authenticated;
grant select on public.orders, public.order_items to authenticated;
grant update (status, valor_final, data_entrega, observacoes_internas) on public.orders to authenticated;

drop policy if exists orders_admin_read on public.orders;
create policy orders_admin_read on public.orders
    for select to authenticated using (public.is_store_admin(confeitaria_id));
drop policy if exists orders_admin_update on public.orders;
create policy orders_admin_update on public.orders
    for update to authenticated
    using (public.is_store_admin(confeitaria_id)) with check (public.is_store_admin(confeitaria_id));
drop policy if exists order_items_admin_read on public.order_items;
create policy order_items_admin_read on public.order_items
    for select to authenticated using (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- limites contra abuso
create or replace function public.verificar_limite_envios(p_confeitaria_id uuid, p_whatsapp text)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_por_whatsapp integer;
    v_por_minuto   integer;
begin
    select (select count(*) from public.leads l where l.confeitaria_id = p_confeitaria_id
              and l.cliente_whatsapp = p_whatsapp and l.created_at > now() - interval '1 hour')
         + (select count(*) from public.orders o where o.confeitaria_id = p_confeitaria_id
              and o.cliente_whatsapp = p_whatsapp and o.created_at > now() - interval '1 hour')
      into v_por_whatsapp;
    select (select count(*) from public.leads l where l.confeitaria_id = p_confeitaria_id
              and l.created_at > now() - interval '1 minute')
         + (select count(*) from public.orders o where o.confeitaria_id = p_confeitaria_id
              and o.created_at > now() - interval '1 minute')
      into v_por_minuto;
    if v_por_whatsapp >= 5 or v_por_minuto >= 30 then
        raise exception 'limite_excedido' using errcode = '22023';
    end if;
end;
$$;
revoke all on function public.verificar_limite_envios(uuid, text) from public, anon, authenticated;

-- ---------------------------------------------------------------- criar_pedido (fluxo público)
-- p_itens: [{"produto_slug": "bem-casado", "quantidade": 50}, ...] (1 a 20 itens, sem repetir produto)
create or replace function public.criar_pedido(
    p_confeitaria_slug text,
    p_cliente_nome     text,
    p_cliente_whatsapp text,
    p_data_entrega     date,
    p_modalidade       text,
    p_observacoes      text,
    p_itens            jsonb,
    p_origem           text,
    p_consentimento    boolean
)
returns table (id uuid, protocolo text, criado boolean, status text, valor_estimado numeric,
               confeitaria_nome text, confeitaria_whatsapp text)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
#variable_conflict use_column
declare
    v_conf    public.confeitarias%rowtype;
    v_prod    public.produtos%rowtype;
    v_item    jsonb;
    v_qtd     integer;
    v_slugs   text[] := '{}';
    v_chaves  text[] := '{}';
    v_total   numeric(10, 2) := 0;
    v_sem_preco boolean := false;
    v_nome    text := regexp_replace(btrim(coalesce(p_cliente_nome, '')), '\s+', ' ', 'g');
    v_obs     text := btrim(coalesce(p_observacoes, ''));
    v_origem  text := coalesce(nullif(lower(btrim(p_origem)), ''), 'site');
    v_hoje    date := ((now() at time zone 'UTC') - interval '3 hours')::date;
    v_fp      text;
    v_id      uuid;
    v_criado  boolean := false;
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
    if p_itens is null or jsonb_typeof(p_itens) <> 'array'
       or jsonb_array_length(p_itens) < 1 or jsonb_array_length(p_itens) > 20 then
        raise exception 'itens_invalidos' using errcode = '22023';
    end if;
    if v_origem !~ '^[a-z0-9_-]{1,40}$' then
        v_origem := 'site';
    end if;

    -- valida cada item: produto da MESMA confeitaria, publicado, disponível e quantidade permitida
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
                                   modalidade, observacoes, valor_estimado, origem, consentimento, fingerprint)
        values ('PD-' || to_char((now() at time zone 'UTC') - interval '3 hours', 'YYMMDD') || '-'
                    || upper(substr(md5(gen_random_uuid()::text), 1, 6)),
                v_conf.id, v_nome, p_cliente_whatsapp, p_data_entrega, p_modalidade, v_obs,
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
revoke all on function public.criar_pedido(text, text, text, date, text, text, jsonb, text, boolean) from public;
grant execute on function public.criar_pedido(text, text, text, date, text, text, jsonb, text, boolean)
    to anon, authenticated;

-- ---------------------------------------------------------------- criar_lead com as mesmas proteções
-- Mesma assinatura e retorno da 001 (compatível com o app). Novidades: só produtos publicados
-- e limite de envios por WhatsApp/confeitaria.
create or replace function public.criar_lead(
    p_confeitaria_slug text,
    p_produto_slug     text,
    p_cliente_nome     text,
    p_cliente_whatsapp text,
    p_quantidade       integer,
    p_data_desejada    date,
    p_modalidade       text,
    p_observacoes      text,
    p_origem           text,
    p_consentimento    boolean
)
returns table (
    id uuid, protocolo text, criado boolean, produto_nome text, unidade text,
    quantidade integer, data_desejada date, modalidade text, observacoes text,
    cliente_nome text, status text, confeitaria_nome text, confeitaria_whatsapp text
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
#variable_conflict use_column
declare
    v_conf     public.confeitarias%rowtype;
    v_prod     public.produtos%rowtype;
    v_nome     text := regexp_replace(btrim(coalesce(p_cliente_nome, '')), '\s+', ' ', 'g');
    v_obs      text := btrim(coalesce(p_observacoes, ''));
    v_origem   text := coalesce(nullif(lower(btrim(p_origem)), ''), 'site');
    v_hoje     date := ((now() at time zone 'UTC') - interval '3 hours')::date;
    v_fp       text;
    v_lead_id  uuid;
    v_criado   boolean := false;
    v_tentativa integer := 0;
begin
    select * into v_conf from public.confeitarias c where c.slug = p_confeitaria_slug and c.ativo;
    if not found then
        raise exception 'confeitaria_invalida' using errcode = '22023';
    end if;
    select * into v_prod from public.produtos pr
     where pr.confeitaria_id = v_conf.id and pr.slug = p_produto_slug and pr.publicado;
    if not found then
        raise exception 'produto_invalido' using errcode = '22023';
    end if;
    if not v_prod.disponivel then
        raise exception 'produto_indisponivel' using errcode = '22023';
    end if;
    if p_quantidade is null or p_quantidade < v_prod.qtd_min or p_quantidade > v_prod.qtd_max then
        raise exception 'quantidade_invalida' using errcode = '22023';
    end if;
    if p_data_desejada is null or p_data_desejada < v_hoje or p_data_desejada > v_hoje + 365 then
        raise exception 'data_invalida' using errcode = '22023';
    end if;
    if p_consentimento is not true then
        raise exception 'consentimento_obrigatorio' using errcode = '22023';
    end if;
    if v_origem !~ '^[a-z0-9_-]{1,40}$' then
        v_origem := 'site';
    end if;

    v_fp := md5(concat_ws('|', p_cliente_whatsapp, v_prod.id::text, p_quantidade::text,
                          p_data_desejada::text, p_modalidade));
    select l.id into v_lead_id from public.leads l
     where l.confeitaria_id = v_conf.id and l.fingerprint = v_fp;
    if v_lead_id is null then
        perform public.verificar_limite_envios(v_conf.id, p_cliente_whatsapp);
    end if;

    while v_lead_id is null loop
        v_tentativa := v_tentativa + 1;
        begin
            insert into public.leads (
                protocolo, confeitaria_id, produto_id, produto_nome, unidade, quantidade,
                data_desejada, modalidade, observacoes, cliente_nome, cliente_whatsapp,
                consentimento, origem, fingerprint
            ) values (
                'DF-' || to_char((now() at time zone 'UTC') - interval '3 hours', 'YYMMDD') || '-'
                    || upper(substr(md5(gen_random_uuid()::text), 1, 6)),
                v_conf.id, v_prod.id, v_prod.nome, v_prod.unidade, p_quantidade,
                p_data_desejada, p_modalidade, v_obs, v_nome, p_cliente_whatsapp,
                true, v_origem, v_fp
            )
            returning leads.id into v_lead_id;
            v_criado := true;
        exception when unique_violation then
            select l.id into v_lead_id from public.leads l
             where l.confeitaria_id = v_conf.id and l.fingerprint = v_fp;
            if v_tentativa >= 3 and v_lead_id is null then
                raise;
            end if;
        end;
    end loop;

    return query
        select l.id, l.protocolo, v_criado, l.produto_nome, l.unidade, l.quantidade,
               l.data_desejada, l.modalidade, l.observacoes, l.cliente_nome, l.status,
               v_conf.nome, v_conf.whatsapp
          from public.leads l
         where l.id = v_lead_id;
end;
$$;
revoke all on function public.criar_lead(text, text, text, text, integer, date, text, text, text, boolean) from public;
grant execute on function public.criar_lead(text, text, text, text, integer, date, text, text, text, boolean)
    to anon, authenticated;
