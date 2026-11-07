-- DoceFlow · Etapa 03 · Schema, RLS e função pública de criação de leads
-- Executar no Supabase: SQL Editor > New query > colar e rodar (ou `supabase db push`).
--
-- Modelo de acesso:
--   * anon (visitante da vitrine): lê confeitarias ativas e seus produtos;
--     NÃO lê nem grava diretamente na tabela leads. Só cria leads pela
--     função public.criar_lead (SECURITY DEFINER), que valida os dados.
--   * authenticated (dona da confeitaria, via Supabase Auth): lê e atualiza
--     somente os leads da confeitaria em que é owner_user_id.
--   * A chave service_role NUNCA deve ser usada pelo app.

-- ---------------------------------------------------------------- tabelas
create table if not exists public.confeitarias (
    id            uuid primary key default gen_random_uuid(),
    slug          text not null unique check (slug ~ '^[a-z0-9-]{2,60}$'),
    nome          text not null check (char_length(nome) between 2 and 120),
    whatsapp      text check (whatsapp ~ '^55[0-9]{10,11}$'),
    owner_user_id uuid references auth.users (id) on delete set null,
    ativo         boolean not null default true,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create table if not exists public.produtos (
    id             uuid primary key default gen_random_uuid(),
    confeitaria_id uuid not null references public.confeitarias (id) on delete cascade,
    slug           text not null check (slug ~ '^[a-z0-9-]{2,60}$'),
    nome           text not null check (char_length(nome) between 2 and 120),
    categoria      text not null check (char_length(categoria) between 2 and 60),
    descricao      text not null default '' check (char_length(descricao) <= 500),
    unidade        text not null check (char_length(unidade) between 1 and 40),
    preco          numeric(10, 2) check (preco is null or preco >= 0),
    tipo_preco     text not null check (tipo_preco in ('a_partir_de', 'estimado', 'sob_consulta')),
    disponivel     boolean not null default true,
    imagem         text,
    qtd_min        integer not null default 1 check (qtd_min >= 1),
    qtd_max        integer not null default 50 check (qtd_max >= qtd_min),
    ordem          integer not null default 0,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    unique (confeitaria_id, slug)
);

create table if not exists public.leads (
    id                uuid primary key default gen_random_uuid(),
    protocolo         text not null unique,
    confeitaria_id    uuid not null references public.confeitarias (id) on delete cascade,
    produto_id        uuid not null references public.produtos (id) on delete restrict,
    produto_nome      text not null,          -- snapshot do nome no momento do pedido
    unidade           text not null,
    quantidade        integer not null check (quantidade > 0),
    data_desejada     date not null,
    modalidade        text not null check (modalidade in ('Retirada', 'Entrega')),
    observacoes       text not null default '' check (char_length(observacoes) <= 500),
    cliente_nome      text not null check (char_length(cliente_nome) between 2 and 80),
    cliente_whatsapp  text not null check (cliente_whatsapp ~ '^55[0-9]{10,11}$'),
    consentimento     boolean not null check (consentimento),
    consentimento_em  timestamptz not null default now(),
    origem            text not null default 'site' check (origem ~ '^[a-z0-9_-]{1,40}$'),
    status            text not null default 'Novo'
                      check (status in ('Novo', 'Em contato', 'Orçamento enviado', 'Fechado', 'Perdido')),
    fingerprint       text not null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (confeitaria_id, fingerprint)
);

create index if not exists leads_confeitaria_created_idx on public.leads (confeitaria_id, created_at desc);
create index if not exists produtos_confeitaria_idx on public.produtos (confeitaria_id, ordem);

-- ---------------------------------------------------------------- updated_at
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists confeitarias_updated_at on public.confeitarias;
create trigger confeitarias_updated_at before update on public.confeitarias
    for each row execute function public.set_updated_at();
drop trigger if exists produtos_updated_at on public.produtos;
create trigger produtos_updated_at before update on public.produtos
    for each row execute function public.set_updated_at();
drop trigger if exists leads_updated_at on public.leads;
create trigger leads_updated_at before update on public.leads
    for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- RLS
alter table public.confeitarias enable row level security;
alter table public.produtos     enable row level security;
alter table public.leads        enable row level security;

revoke all on public.confeitarias, public.produtos, public.leads from anon, authenticated;
grant select on public.confeitarias, public.produtos to anon, authenticated;
grant select on public.leads to authenticated;
grant update (status) on public.leads to authenticated;

drop policy if exists confeitarias_public_read on public.confeitarias;
create policy confeitarias_public_read on public.confeitarias
    for select to anon, authenticated using (ativo);

drop policy if exists produtos_public_read on public.produtos;
create policy produtos_public_read on public.produtos
    for select to anon, authenticated
    using (exists (select 1 from public.confeitarias c where c.id = confeitaria_id and c.ativo));

drop policy if exists leads_owner_read on public.leads;
create policy leads_owner_read on public.leads
    for select to authenticated
    using (exists (select 1 from public.confeitarias c
                   where c.id = confeitaria_id and c.owner_user_id = auth.uid()));

drop policy if exists leads_owner_update on public.leads;
create policy leads_owner_update on public.leads
    for update to authenticated
    using (exists (select 1 from public.confeitarias c
                   where c.id = confeitaria_id and c.owner_user_id = auth.uid()))
    with check (exists (select 1 from public.confeitarias c
                        where c.id = confeitaria_id and c.owner_user_id = auth.uid()));
-- Sem política para anon em leads: com RLS ativa, o visitante não lê nem grava.

-- ---------------------------------------------------------------- criar_lead
-- Único caminho público de escrita. Valida tudo no servidor, é idempotente
-- (mesmo pedido = mesmo lead) e devolve só os dados do próprio pedido.
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
    v_hoje     date := ((now() at time zone 'UTC') - interval '3 hours')::date;  -- horário de Brasília (UTC-3, sem horário de verão)
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
     where pr.confeitaria_id = v_conf.id and pr.slug = p_produto_slug;
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
            -- pedido idêntico gravado em paralelo, ou colisão de protocolo
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
