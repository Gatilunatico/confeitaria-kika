-- DoceFlow · 012 · Backend do app da confeiteira (Flutter)
-- Rodar depois da 011. Idempotente e NÃO destrutiva: só cria funções, uma view, um gatilho e um
-- índice. Nenhuma tabela é apagada ou recriada, nenhum dado existente é alterado.
--
-- Arquitetura aprovada (21/11/2026): o app fala direto com o Supabase, com o login da dona
-- (chave publishable + token do usuário). Toda autorização continua no banco (RLS com
-- is_store_admin). Esta migração acrescenta só o que o app não consegue fazer com segurança
-- pelas tabelas:
--
-- 1. painel_indicadores(): números do painel calculados no banco (uma chamada só, sem baixar
--    todos os pedidos e orçamentos para o celular). SECURITY INVOKER: respeita o RLS.
-- 2. clientes_resumo: view "Clientes" (pedidos + orçamentos agrupados por WhatsApp).
--    security_invoker: cada dona só vê os clientes da própria confeitaria.
-- 3. converter_orcamento_em_pedido(): a dona transforma um orçamento em pedido confirmado.
--    Sem duplicar (um pedido por orçamento) e com histórico de quem converteu.
-- 4. Endereço (slug) automático para produtos criados pelo app, sem repetir na confeitaria.
-- 5. Atualização em tempo real (Realtime) de pedidos e orçamentos, se o Supabase tiver a
--    publicação supabase_realtime. O Realtime também respeita o RLS.

-- ---------------------------------------------------------------- 1. indicadores do painel
-- Mesmas definições do painel web (services/dashboard_service.py e order_service.py):
--   * período pela data de registro no horário de Brasília (UTC-3), inclusive nas duas pontas;
--   * taxa de conversão = vendas concluídas / orçamentos do período;
--   * valor registrado = soma dos valores ESTIMADOS dos pedidos não cancelados (não é receita).
create or replace function public.painel_indicadores(p_inicio date default null, p_fim date default null)
returns jsonb
language plpgsql
stable
security invoker
set search_path = public, pg_temp
as $$
declare
    v_conf uuid;
    v_hoje date := ((now() at time zone 'UTC') - interval '3 hours')::date;
    v_leads jsonb;
    v_pedidos jsonb;
begin
    select a.confeitaria_id into v_conf
      from public.admin_profiles a
     where a.user_id = auth.uid() and a.ativo
     limit 1;
    if v_conf is null or not public.is_store_admin(v_conf) then
        raise exception 'sem_permissao' using errcode = '42501';
    end if;
    if p_inicio is not null and p_fim is not null and p_inicio > p_fim then
        raise exception 'periodo_invalido' using errcode = '22023';
    end if;

    with l as (
        select status from public.leads
         where confeitaria_id = v_conf
           and (p_inicio is null or ((created_at at time zone 'UTC') - interval '3 hours')::date >= p_inicio)
           and (p_fim    is null or ((created_at at time zone 'UTC') - interval '3 hours')::date <= p_fim)
    )
    select jsonb_build_object(
        'total',               count(*),
        'novos',               count(*) filter (where status = 'Novo'),
        'em_atendimento',      count(*) filter (where status = 'Em atendimento'),
        'orcamentos_enviados', count(*) filter (where status = 'Orçamento enviado'),
        'vendas_concluidas',   count(*) filter (where status = 'Venda concluída'),
        'perdidos',            count(*) filter (where status = 'Perdido'),
        'taxa_conversao',      case when count(*) = 0 then null
                                    else round(count(*) filter (where status = 'Venda concluída')::numeric
                                               / count(*), 4) end
    ) into v_leads from l;

    with o as (
        select status, valor_estimado, valor_final, data_entrega from public.orders
         where confeitaria_id = v_conf
           and (p_inicio is null or ((created_at at time zone 'UTC') - interval '3 hours')::date >= p_inicio)
           and (p_fim    is null or ((created_at at time zone 'UTC') - interval '3 hours')::date <= p_fim)
    )
    select jsonb_build_object(
        'total',                  count(*),
        'aguardando_confirmacao', count(*) filter (where status = 'Aguardando confirmação'),
        'confirmados',            count(*) filter (where status = 'Confirmado'),
        'em_producao',            count(*) filter (where status = 'Em produção'),
        'prontos',                count(*) filter (where status = 'Pronto'),
        'entregues',              count(*) filter (where status = 'Entregue'),
        'cancelados',             count(*) filter (where status = 'Cancelado'),
        'valor_registrado',       coalesce(sum(valor_estimado) filter (where status <> 'Cancelado'), 0),
        'sem_valor_estimado',     count(*) filter (where status <> 'Cancelado' and valor_estimado is null),
        'valor_final_combinado',  coalesce(sum(valor_final) filter (where status <> 'Cancelado'), 0)
    ) into v_pedidos from o;

    return jsonb_build_object(
        'confeitaria_id', v_conf,
        'periodo', jsonb_build_object('inicio', p_inicio, 'fim', p_fim),
        'hoje', v_hoje,
        'orcamentos', v_leads,
        'pedidos', v_pedidos,
        -- agenda: independe do período (o que a dona precisa produzir/entregar nos próximos 7 dias)
        'entregas_proximos_7_dias', (
            select count(*) from public.orders
             where confeitaria_id = v_conf
               and data_entrega between v_hoje and v_hoje + 7
               and status not in ('Entregue', 'Cancelado'))
    );
end;
$$;
revoke all on function public.painel_indicadores(date, date) from public, anon;
grant execute on function public.painel_indicadores(date, date) to authenticated;

-- ---------------------------------------------------------------- 2. clientes
-- Uma linha por (confeitaria, WhatsApp). O nome é o do contato mais recente.
-- security_invoker = true: a view roda com as permissões de quem consulta, então o RLS de
-- leads e orders vale aqui também (visitante e outras confeitarias não veem nada).
create or replace view public.clientes_resumo
with (security_invoker = true)
as
with contatos as (
    select o.confeitaria_id, o.cliente_whatsapp, o.cliente_nome, o.created_at,
           1 as pedido, 0 as orcamento,
           case when o.status not in ('Entregue', 'Cancelado') then 1 else 0 end as ativo,
           case when o.status <> 'Cancelado' then coalesce(o.valor_final, o.valor_estimado) end as valor
      from public.orders o
    union all
    select l.confeitaria_id, l.cliente_whatsapp, l.cliente_nome, l.created_at,
           0, 1, 0, null
      from public.leads l
)
select c.confeitaria_id,
       c.cliente_whatsapp,
       (array_agg(c.cliente_nome order by c.created_at desc))[1] as cliente_nome,
       sum(c.pedido)::int    as total_pedidos,
       sum(c.orcamento)::int as total_orcamentos,
       sum(c.ativo)::int     as pedidos_em_andamento,
       coalesce(sum(c.valor), 0)::numeric(12, 2) as valor_pedidos,
       min(c.created_at) as primeiro_contato,
       max(c.created_at) as ultimo_contato
  from contatos c
 group by c.confeitaria_id, c.cliente_whatsapp;

revoke all on public.clientes_resumo from public, anon, authenticated;
grant select on public.clientes_resumo to authenticated;

-- ---------------------------------------------------------------- 3. orçamento -> pedido
-- Um pedido por orçamento: o índice impede duplicar mesmo com dois toques ao mesmo tempo.
create unique index if not exists orders_lead_unico_idx on public.orders (lead_id) where lead_id is not null;

create or replace function public.converter_orcamento_em_pedido(
    p_lead_id              uuid,
    p_data_entrega         date    default null,   -- vazio: a data desejada do orçamento
    p_endereco_entrega     text    default '',     -- obrigatório quando o orçamento é de Entrega
    p_valor_final          numeric default null,   -- valor combinado com a cliente (opcional)
    p_observacoes_internas text    default ''
)
returns table (id uuid, protocolo text, criado boolean, status text)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
#variable_conflict use_column
declare
    v_lead     public.leads%rowtype;
    v_prod     public.produtos%rowtype;
    v_hoje     date := ((now() at time zone 'UTC') - interval '3 hours')::date;
    v_data     date;
    v_endereco text := regexp_replace(btrim(coalesce(p_endereco_entrega, '')), '\s+', ' ', 'g');
    v_obs_int  text := btrim(coalesce(p_observacoes_internas, ''));
    v_preco    numeric(10, 2);
    v_id       uuid;
    v_criado   boolean := false;
begin
    if auth.uid() is null then
        raise exception 'sem_permissao' using errcode = '42501';
    end if;
    -- Mesmo erro para "não existe" e "é de outra confeitaria": não revela orçamentos alheios.
    select * into v_lead from public.leads l where l.id = p_lead_id;
    if not found or not public.is_store_admin(v_lead.confeitaria_id) then
        raise exception 'orcamento_nao_encontrado' using errcode = '42501';
    end if;

    -- Já convertido: devolve o mesmo pedido (repetir o toque não duplica).
    select o.id into v_id from public.orders o where o.lead_id = v_lead.id;
    if v_id is null then
        if v_lead.status = 'Perdido' then
            raise exception 'orcamento_perdido' using errcode = '22023';
        end if;
        v_data := coalesce(p_data_entrega, v_lead.data_desejada);
        if v_data < v_hoje or v_data > v_hoje + 365 then
            raise exception 'data_invalida' using errcode = '22023';
        end if;
        if v_lead.modalidade = 'Entrega' then
            if char_length(v_endereco) < 10 then
                raise exception 'endereco_obrigatorio' using errcode = '22023';
            end if;
            if char_length(v_endereco) > 300 then
                raise exception 'endereco_invalido' using errcode = '22023';
            end if;
        else
            v_endereco := '';
        end if;
        if p_valor_final is not null and (p_valor_final < 0 or p_valor_final > 99999999) then
            raise exception 'valor_invalido' using errcode = '22023';
        end if;
        if char_length(v_obs_int) > 1000 then
            raise exception 'observacoes_invalidas' using errcode = '22023';
        end if;

        select * into v_prod from public.produtos pr
         where pr.id = v_lead.produto_id and pr.confeitaria_id = v_lead.confeitaria_id;
        v_preco := case when v_prod.tipo_preco = 'sob_consulta' then null else v_prod.preco end;

        insert into public.orders (protocolo, confeitaria_id, lead_id, cliente_nome, cliente_whatsapp,
                                   data_entrega, modalidade, endereco_entrega, observacoes,
                                   observacoes_internas, status, valor_estimado, valor_final, origem,
                                   consentimento, consentimento_em, fingerprint)
        values ('PD-' || to_char((now() at time zone 'UTC') - interval '3 hours', 'YYMMDD') || '-'
                    || upper(substr(md5(gen_random_uuid()::text), 1, 6)),
                v_lead.confeitaria_id, v_lead.id, v_lead.cliente_nome, v_lead.cliente_whatsapp,
                v_data, v_lead.modalidade, v_endereco, v_lead.observacoes, v_obs_int, 'Confirmado',
                case when v_preco is null then null else v_preco * v_lead.quantidade end,
                p_valor_final, v_lead.origem, true, v_lead.consentimento_em, 'lead:' || v_lead.id::text)
        on conflict do nothing
        returning orders.id into v_id;

        if v_id is null then  -- outro toque converteu ao mesmo tempo
            select o.id into v_id from public.orders o where o.lead_id = v_lead.id;
        else
            insert into public.order_items (order_id, confeitaria_id, produto_id, produto_nome, unidade,
                                            quantidade, preco_unitario, tipo_preco)
            values (v_id, v_lead.confeitaria_id, v_lead.produto_id, v_lead.produto_nome, v_lead.unidade,
                    v_lead.quantidade, v_preco, v_prod.tipo_preco);
            update public.leads set status = 'Venda concluída' where leads.id = v_lead.id;
            v_criado := true;
        end if;
    end if;

    return query select o.id, o.protocolo, v_criado, o.status from public.orders o where o.id = v_id;
end;
$$;
revoke all on function public.converter_orcamento_em_pedido(uuid, date, text, numeric, text) from public, anon;
grant execute on function public.converter_orcamento_em_pedido(uuid, date, text, numeric, text) to authenticated;

-- ---------------------------------------------------------------- 4. slug automático
-- O app pode criar produto sem informar o slug: o banco gera a partir do nome (sem acentos),
-- sem repetir dentro da confeitaria. Slug informado continua valendo (o CHECK valida o formato).
create or replace function public.produtos_slug_automatico()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
    v_base text;
    v_slug text;
    v_n    integer := 1;
begin
    if new.slug is not null and btrim(new.slug) <> '' then
        return new;
    end if;
    v_base := lower(translate(coalesce(new.nome, ''),
                              'áàâãäåéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÅÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
                              'aaaaaaeeeeiiiiooooouuuucnaaaaaaeeeeiiiiooooouuuucn'));
    v_base := btrim(regexp_replace(v_base, '[^a-z0-9]+', '-', 'g'), '-');
    v_base := btrim(left(v_base, 54), '-');
    if char_length(v_base) < 2 then
        v_base := 'produto';
    end if;
    v_slug := v_base;
    -- Quem cria é a administradora: o RLS deixa ela ver todos os produtos da própria loja.
    while exists (select 1 from public.produtos p where p.confeitaria_id = new.confeitaria_id and p.slug = v_slug) loop
        v_n := v_n + 1;
        v_slug := v_base || '-' || v_n;
    end loop;
    new.slug := v_slug;
    return new;
end;
$$;
revoke execute on function public.produtos_slug_automatico() from public, anon, authenticated;

drop trigger if exists produtos_slug_automatico on public.produtos;
create trigger produtos_slug_automatico before insert on public.produtos
    for each row execute function public.produtos_slug_automatico();

-- ---------------------------------------------------------------- 5. tempo real
do $$
declare
    t text;
begin
    if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
        foreach t in array array['orders', 'leads'] loop
            if not exists (select 1 from pg_publication_tables
                            where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
                execute format('alter publication supabase_realtime add table public.%I', t);
            end if;
        end loop;
    end if;
end $$;
