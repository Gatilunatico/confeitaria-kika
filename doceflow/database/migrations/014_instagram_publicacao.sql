-- DoceFlow · 014 · Publicação no Instagram (conexão oficial da Meta, fila, tentativas e histórico)
-- Rodar depois da 013. Idempotente e NÃO destrutiva: cria tabelas e funções novas, acrescenta
-- colunas a instagram_accounts e cria o bucket privado instagram-media. Nada é apagado.
--
-- Quem faz o quê:
-- * App (dona logada, RLS): lê a conta e o histórico; agenda, cancela e tenta de novo pelas
--   funções abaixo. Nunca vê o token.
-- * Serviço do Instagram (doceflow/instagram_service, no servidor): faz a autorização oficial da
--   Meta (OAuth), guarda o token no Supabase Vault e publica pela API oficial. As funções do
--   serviço NÃO podem ser executadas por anon nem authenticated.
--
-- Garantias:
-- * Token só no Vault (instagram_accounts guarda a referência, que o app não lê).
-- * Idempotência: (confeitaria, idempotency_key) único; o mesmo pedido devolve o mesmo agendamento.
-- * Um agendamento ativo por post (índice único parcial).
-- * Concorrência: o serviço reserva com FOR UPDATE SKIP LOCKED; duas cópias não pegam o mesmo item.
-- * Nunca "publicado" sem o id real da mídia devolvido pela Meta (CHECK).
-- * Se não der para saber se a Meta publicou (serviço caiu no meio), o status vira "verificar"
--   em vez de publicar de novo: nada é duplicado nem dado como concluído sem prova.

-- ---------------------------------------------------------------- conta
alter table public.instagram_accounts add column if not exists account_type text;
alter table public.instagram_accounts add column if not exists conectado_em timestamptz;
alter table public.instagram_accounts add column if not exists ultimo_erro text;
do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'instagram_accounts_ultimo_erro_check') then
        alter table public.instagram_accounts add constraint instagram_accounts_ultimo_erro_check
            check (ultimo_erro is null or char_length(ultimo_erro) <= 300);
    end if;
end $$;
grant select (account_type, conectado_em, ultimo_erro) on public.instagram_accounts to authenticated;
-- As permissões da 008 (a dona cria a linha e edita só o username) continuam iguais. Status,
-- ig_user_id, token e validade só mudam pelo serviço (funções abaixo), nunca pelo app.

-- ---------------------------------------------------------------- estados do OAuth (uso único)
create table if not exists public.instagram_oauth_states (
    nonce_hash     text primary key check (char_length(nonce_hash) = 64),
    confeitaria_id uuid not null references public.confeitarias (id) on delete cascade,
    user_id        uuid not null,
    expira_em      timestamptz not null,
    usado_em       timestamptz,
    created_at     timestamptz not null default now()
);
alter table public.instagram_oauth_states enable row level security;
revoke all on public.instagram_oauth_states from public, anon, authenticated;

-- ---------------------------------------------------------------- publicações
create table if not exists public.instagram_publications (
    id                   uuid primary key default gen_random_uuid(),
    confeitaria_id       uuid not null references public.confeitarias (id) on delete cascade,
    marketing_post_id    uuid not null references public.marketing_posts (id) on delete restrict,
    formato              text not null check (formato in ('feed', 'story')),
    legenda              text not null default '' check (char_length(legenda) <= 2200),
    imagem_path          text not null,
    agendado_para        timestamptz not null,
    status               text not null default 'agendado'
                         check (status in ('agendado', 'publicando', 'publicado', 'falhou', 'cancelado', 'verificar')),
    tentativas           integer not null default 0 check (tentativas >= 0),
    max_tentativas       integer not null default 3 check (max_tentativas between 1 and 10),
    proxima_tentativa_em timestamptz,
    erro_codigo          text check (erro_codigo is null or char_length(erro_codigo) <= 60),
    erro_mensagem        text check (erro_mensagem is null or char_length(erro_mensagem) <= 500),
    ig_container_id      text,
    ig_media_id          text,
    permalink            text check (permalink is null or permalink ~ '^https://(www\.)?instagram\.com/'),
    publicado_em         timestamptz,
    idempotency_key      text not null check (idempotency_key ~ '^[A-Za-z0-9_-]{8,128}$'),
    bloqueado_em         timestamptz,
    bloqueado_por        text,
    criado_por           uuid default auth.uid(),
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    unique (confeitaria_id, idempotency_key),
    -- só a Meta diz que publicou: sem id da mídia, não existe "publicado"
    constraint instagram_publications_publicado_check
        check (status <> 'publicado' or (ig_media_id is not null and publicado_em is not null))
);
create unique index if not exists instagram_publications_post_ativo_uidx
    on public.instagram_publications (marketing_post_id) where status in ('agendado', 'publicando');
create index if not exists instagram_publications_fila_idx
    on public.instagram_publications (status, agendado_para);
create index if not exists instagram_publications_conf_idx
    on public.instagram_publications (confeitaria_id, created_at desc);

drop trigger if exists instagram_publications_updated_at on public.instagram_publications;
create trigger instagram_publications_updated_at before update on public.instagram_publications
    for each row execute function public.set_updated_at();

alter table public.instagram_publications enable row level security;
revoke all on public.instagram_publications from public, anon, authenticated;
grant select on public.instagram_publications to authenticated;   -- gravar: só pelas funções
drop policy if exists instagram_publications_admin_read on public.instagram_publications;
create policy instagram_publications_admin_read on public.instagram_publications
    for select to authenticated using (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- histórico (log)
create table if not exists public.instagram_publication_logs (
    id             bigint generated always as identity primary key,
    publication_id uuid not null references public.instagram_publications (id) on delete cascade,
    confeitaria_id uuid not null,
    evento         text not null check (char_length(evento) between 1 and 40),
    detalhe        text check (detalhe is null or char_length(detalhe) <= 500),
    created_at     timestamptz not null default now()
);
create index if not exists instagram_publication_logs_pub_idx on public.instagram_publication_logs (publication_id, id);
alter table public.instagram_publication_logs enable row level security;
revoke all on public.instagram_publication_logs from public, anon, authenticated;
grant select on public.instagram_publication_logs to authenticated;
drop policy if exists instagram_publication_logs_admin_read on public.instagram_publication_logs;
create policy instagram_publication_logs_admin_read on public.instagram_publication_logs
    for select to authenticated using (public.is_store_admin(confeitaria_id));

create or replace function public.instagram_log(p_pub uuid, p_evento text, p_detalhe text default null)
returns void
language sql
security definer
set search_path = public, pg_temp
as $$
    insert into public.instagram_publication_logs (publication_id, confeitaria_id, evento, detalhe)
    select p.id, p.confeitaria_id, p_evento, left(p_detalhe, 500) from public.instagram_publications p where p.id = p_pub
$$;
revoke all on function public.instagram_log(uuid, text, text) from public, anon, authenticated;

-- ---------------------------------------------------------------- Storage: JPEG para a Meta
-- A Meta só aceita JPEG e baixa a imagem por um link. O serviço converte o PNG do post, guarda
-- aqui (bucket PRIVADO) e entrega um link assinado temporário. Só o serviço escreve.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('instagram-media', 'instagram-media', false, 8388608, array['image/jpeg'])
on conflict (id) do update
    set public = false, file_size_limit = 8388608, allowed_mime_types = array['image/jpeg'];

-- ================================================================ funções do APP (dona logada)
create or replace function public._instagram_admin_conf() returns uuid
language sql stable security definer set search_path = public, pg_temp as $$
    select a.confeitaria_id from public.admin_profiles a
     where a.user_id = auth.uid() and a.ativo and public.is_store_admin(a.confeitaria_id) limit 1
$$;
revoke all on function public._instagram_admin_conf() from public, anon, authenticated;

create or replace function public.agendar_publicacao_instagram(
    p_post_id uuid, p_agendado_para timestamptz, p_idempotency_key text)
returns setof public.instagram_publications
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_conf uuid := public._instagram_admin_conf();
    v_post public.marketing_posts%rowtype;
    v_conta public.instagram_accounts%rowtype;
    v_id uuid;
    v_quando timestamptz := coalesce(p_agendado_para, now());
begin
    if v_conf is null then
        raise exception 'sem_permissao' using errcode = '42501';
    end if;
    -- mesmo pedido repetido: devolve o agendamento já criado
    select id into v_id from public.instagram_publications
     where confeitaria_id = v_conf and idempotency_key = p_idempotency_key;
    if v_id is not null then
        return query select * from public.instagram_publications where id = v_id;
        return;
    end if;
    if p_idempotency_key is null or p_idempotency_key !~ '^[A-Za-z0-9_-]{8,128}$' then
        raise exception 'chave_invalida' using errcode = '22023';
    end if;
    select * into v_post from public.marketing_posts where id = p_post_id and confeitaria_id = v_conf;
    if not found then
        raise exception 'post_nao_encontrado' using errcode = '42501';
    end if;
    if v_post.imagem_path is null then
        raise exception 'post_sem_imagem' using errcode = '22023';
    end if;
    select * into v_conta from public.instagram_accounts where confeitaria_id = v_conf;
    if not found or v_conta.status <> 'conectado' or v_conta.token_vault_id is null then
        raise exception 'instagram_desconectado' using errcode = '22023';
    end if;
    if v_quando < now() - interval '5 minutes' or v_quando > now() + interval '75 days' then
        raise exception 'data_invalida' using errcode = '22023';
    end if;
    begin
        insert into public.instagram_publications (confeitaria_id, marketing_post_id, formato, legenda, imagem_path,
                                                   agendado_para, idempotency_key)
        values (v_conf, v_post.id, v_post.formato, case when v_post.formato = 'story' then '' else v_post.legenda end,
                v_post.imagem_path, greatest(v_quando, now()), p_idempotency_key)
        returning id into v_id;
    exception when unique_violation then
        -- outro toque com a mesma chave ganhou a corrida: devolve o dele
        select id into v_id from public.instagram_publications
         where confeitaria_id = v_conf and idempotency_key = p_idempotency_key;
        if v_id is null then
            raise exception 'publicacao_ja_agendada' using errcode = '23505';
        end if;
        return query select * from public.instagram_publications where id = v_id;
        return;
    end;
    perform public.instagram_log(v_id, 'agendado', 'para ' || to_char((greatest(v_quando, now()) at time zone 'UTC') - interval '3 hours', 'DD/MM/YYYY HH24:MI') || ' (Brasília)');
    return query select * from public.instagram_publications where id = v_id;
end;
$$;
revoke all on function public.agendar_publicacao_instagram(uuid, timestamptz, text) from public, anon;
grant execute on function public.agendar_publicacao_instagram(uuid, timestamptz, text) to authenticated;

create or replace function public.cancelar_publicacao_instagram(p_id uuid)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_conf uuid := public._instagram_admin_conf();
    v_status text;
begin
    select status into v_status from public.instagram_publications
     where id = p_id and confeitaria_id = v_conf for update;
    if v_conf is null or v_status is null then
        raise exception 'publicacao_nao_encontrada' using errcode = '42501';
    end if;
    if v_status = 'publicando' then
        raise exception 'publicacao_em_andamento' using errcode = '22023';
    end if;
    if v_status <> 'agendado' then
        raise exception 'publicacao_nao_cancelavel' using errcode = '22023';
    end if;
    update public.instagram_publications set status = 'cancelado', proxima_tentativa_em = null where id = p_id;
    perform public.instagram_log(p_id, 'cancelado', 'pela confeitaria');
end;
$$;
revoke all on function public.cancelar_publicacao_instagram(uuid) from public, anon;
grant execute on function public.cancelar_publicacao_instagram(uuid) to authenticated;

create or replace function public.tentar_publicacao_instagram_novamente(p_id uuid)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_conf uuid := public._instagram_admin_conf();
    v_pub public.instagram_publications%rowtype;
begin
    select * into v_pub from public.instagram_publications where id = p_id and confeitaria_id = v_conf for update;
    if v_conf is null or not found then
        raise exception 'publicacao_nao_encontrada' using errcode = '42501';
    end if;
    if v_pub.status <> 'falhou' then
        raise exception 'publicacao_nao_falhou' using errcode = '22023';
    end if;
    if exists (select 1 from public.instagram_publications
                where marketing_post_id = v_pub.marketing_post_id and status in ('agendado', 'publicando')) then
        raise exception 'publicacao_ja_agendada' using errcode = '23505';
    end if;
    update public.instagram_publications
       set status = 'agendado', tentativas = 0, proxima_tentativa_em = null, agendado_para = now(),
           erro_codigo = null, erro_mensagem = null, ig_container_id = null
     where id = p_id;
    perform public.instagram_log(p_id, 'nova_tentativa', 'pedida pela confeitaria');
end;
$$;
revoke all on function public.tentar_publicacao_instagram_novamente(uuid) from public, anon;
grant execute on function public.tentar_publicacao_instagram_novamente(uuid) to authenticated;

create or replace function public.desconectar_instagram()
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_conf uuid := public._instagram_admin_conf();
    v_secret uuid;
begin
    if v_conf is null then
        raise exception 'sem_permissao' using errcode = '42501';
    end if;
    select token_vault_id into v_secret from public.instagram_accounts where confeitaria_id = v_conf for update;
    update public.instagram_accounts
       set status = 'desconectado', token_vault_id = null, token_expira_em = null, ultimo_erro = null
     where confeitaria_id = v_conf;
    if v_secret is not null then
        delete from vault.secrets where id = v_secret;
    end if;
    -- sem conta, o que estava agendado não pode sair: cancela com registro
    with c as (
        update public.instagram_publications set status = 'cancelado', erro_mensagem = 'Instagram desconectado'
         where confeitaria_id = v_conf and status = 'agendado' returning id
    )
    insert into public.instagram_publication_logs (publication_id, confeitaria_id, evento, detalhe)
    select id, v_conf, 'cancelado', 'Instagram desconectado' from c;
end;
$$;
revoke all on function public.desconectar_instagram() from public, anon;
grant execute on function public.desconectar_instagram() to authenticated;

-- ================================================================ funções do SERVIÇO (servidor)
-- Executadas só pelo serviço do Instagram, com a conexão de banco do servidor. anon e
-- authenticated NÃO podem executá-las (revoke abaixo).

create or replace function public.instagram_criar_estado(p_nonce_hash text, p_conf uuid, p_user uuid, p_ttl interval)
returns void language sql security definer set search_path = public, pg_temp as $$
    delete from public.instagram_oauth_states where expira_em < now() - interval '1 day';
    insert into public.instagram_oauth_states (nonce_hash, confeitaria_id, user_id, expira_em)
    values (p_nonce_hash, p_conf, p_user, now() + p_ttl);
$$;

-- Uso único: devolve a confeitaria só na primeira vez, e só antes de vencer.
create or replace function public.instagram_consumir_estado(p_nonce_hash text)
returns table (confeitaria_id uuid, user_id uuid)
language sql security definer set search_path = public, pg_temp as $$
    update public.instagram_oauth_states s set usado_em = now()
     where s.nonce_hash = p_nonce_hash and s.usado_em is null and s.expira_em > now()
    returning s.confeitaria_id, s.user_id
$$;

create or replace function public.instagram_salvar_conexao(
    p_conf uuid, p_ig_user_id text, p_username text, p_account_type text, p_token text, p_expira_em timestamptz)
returns void
language plpgsql security definer set search_path = public, pg_temp as $$
declare
    v_secret uuid;
begin
    if p_token is null or char_length(p_token) < 20 then
        raise exception 'token_invalido' using errcode = '22023';
    end if;
    select token_vault_id into v_secret from public.instagram_accounts where confeitaria_id = p_conf for update;
    if v_secret is null then
        v_secret := vault.create_secret(p_token, 'instagram_token_' || p_conf::text, 'Token do Instagram (DoceFlow)');
    else
        perform vault.update_secret(v_secret, p_token);
    end if;
    insert into public.instagram_accounts (confeitaria_id, username, ig_user_id, status, token_vault_id,
                                           token_expira_em, account_type, conectado_em, ultimo_erro)
    values (p_conf, p_username, p_ig_user_id, 'conectado', v_secret, p_expira_em, p_account_type, now(), null)
    on conflict (confeitaria_id) do update
        set username = excluded.username, ig_user_id = excluded.ig_user_id, status = 'conectado',
            token_vault_id = excluded.token_vault_id, token_expira_em = excluded.token_expira_em,
            account_type = excluded.account_type, conectado_em = now(), ultimo_erro = null;
end;
$$;

create or replace function public.instagram_token(p_conf uuid)
returns table (ig_user_id text, token text, expira_em timestamptz)
language sql stable security definer set search_path = public, pg_temp as $$
    select a.ig_user_id, s.decrypted_secret, a.token_expira_em
      from public.instagram_accounts a join vault.decrypted_secrets s on s.id = a.token_vault_id
     where a.confeitaria_id = p_conf and a.status = 'conectado'
$$;

create or replace function public.instagram_contas_para_renovar(p_antes interval)
returns table (confeitaria_id uuid)
language sql stable security definer set search_path = public, pg_temp as $$
    select a.confeitaria_id from public.instagram_accounts a
     where a.status = 'conectado' and a.token_vault_id is not null
       and a.token_expira_em is not null and a.token_expira_em < now() + p_antes
$$;

create or replace function public.instagram_marcar_conta_erro(p_conf uuid, p_mensagem text)
returns void language sql security definer set search_path = public, pg_temp as $$
    update public.instagram_accounts set status = 'erro', ultimo_erro = left(p_mensagem, 300) where confeitaria_id = p_conf
$$;

-- Reserva itens prontos para publicar. SKIP LOCKED: duas cópias do serviço nunca pegam o mesmo item.
-- Itens "publicando" parados há muito tempo (serviço caiu) voltam para o serviço retomar com cuidado.
create or replace function public.instagram_reservar_publicacoes(p_worker text, p_limite integer default 5,
                                                                 p_travado interval default interval '15 minutes')
returns setof public.instagram_publications
language plpgsql security definer set search_path = public, pg_temp as $$
begin
    return query
    with alvo as (
        select p.id from public.instagram_publications p
         where (p.status = 'agendado' and p.agendado_para <= now()
                and coalesce(p.proxima_tentativa_em, p.agendado_para) <= now())
            or (p.status = 'publicando' and p.bloqueado_em < now() - p_travado)
         order by p.agendado_para
         limit greatest(1, least(p_limite, 50))
         for update skip locked
    )
    update public.instagram_publications p
       set status = 'publicando', bloqueado_em = now(), bloqueado_por = left(p_worker, 60),
           tentativas = p.tentativas + 1
      from alvo where p.id = alvo.id
    returning p.*;
end;
$$;

create or replace function public.instagram_salvar_container(p_id uuid, p_container text)
returns void language sql security definer set search_path = public, pg_temp as $$
    update public.instagram_publications set ig_container_id = p_container where id = p_id and status = 'publicando';
    select public.instagram_log(p_id, 'container_criado', p_container);
$$;

create or replace function public.instagram_concluir_publicacao(p_id uuid, p_media_id text, p_permalink text)
returns void
language plpgsql security definer set search_path = public, pg_temp as $$
begin
    if p_media_id is null or btrim(p_media_id) = '' then
        raise exception 'media_id_obrigatorio' using errcode = '22023';
    end if;
    update public.instagram_publications
       set status = 'publicado', ig_media_id = p_media_id, permalink = p_permalink, publicado_em = now(),
           bloqueado_em = null, erro_codigo = null, erro_mensagem = null, proxima_tentativa_em = null
     where id = p_id and status in ('publicando', 'verificar');
    if not found then
        raise exception 'publicacao_nao_reservada' using errcode = '22023';
    end if;
    perform public.instagram_log(p_id, 'publicado', p_media_id);
end;
$$;

-- Falha: temporária (rede, limite da Meta, mídia ainda processando) volta para a fila com espera,
-- até o limite de tentativas; permanente (ou sem tentativas) vira "falhou" com a mensagem.
create or replace function public.instagram_registrar_falha(
    p_id uuid, p_codigo text, p_mensagem text, p_temporaria boolean, p_espera interval default interval '5 minutes')
returns text
language plpgsql security definer set search_path = public, pg_temp as $$
declare
    v_pub public.instagram_publications%rowtype;
    v_status text;
begin
    select * into v_pub from public.instagram_publications where id = p_id for update;
    if not found or v_pub.status <> 'publicando' then
        raise exception 'publicacao_nao_reservada' using errcode = '22023';
    end if;
    v_status := case when p_temporaria and v_pub.tentativas < v_pub.max_tentativas then 'agendado' else 'falhou' end;
    update public.instagram_publications
       set status = v_status, erro_codigo = left(p_codigo, 60), erro_mensagem = left(p_mensagem, 500),
           bloqueado_em = null,
           proxima_tentativa_em = case when v_status = 'agendado' then now() + p_espera else null end
     where id = p_id;
    perform public.instagram_log(p_id, case when v_status = 'agendado' then 'nova_tentativa_agendada' else 'falhou' end,
                                 left(coalesce(p_codigo, '') || ': ' || coalesce(p_mensagem, ''), 500));
    return v_status;
end;
$$;

-- Não dá para saber se a Meta publicou (ex.: serviço caiu depois de pedir a publicação):
-- marca para conferência manual em vez de publicar de novo.
create or replace function public.instagram_marcar_verificar(p_id uuid, p_mensagem text)
returns void language sql security definer set search_path = public, pg_temp as $$
    update public.instagram_publications
       set status = 'verificar', erro_codigo = 'confirmacao_pendente', erro_mensagem = left(p_mensagem, 500),
           bloqueado_em = null
     where id = p_id and status = 'publicando';
    select public.instagram_log(p_id, 'verificar', left(p_mensagem, 500));
$$;

do $$
declare
    f text;
begin
    foreach f in array array[
        'instagram_criar_estado(text, uuid, uuid, interval)',
        'instagram_consumir_estado(text)',
        'instagram_salvar_conexao(uuid, text, text, text, text, timestamptz)',
        'instagram_token(uuid)',
        'instagram_contas_para_renovar(interval)',
        'instagram_marcar_conta_erro(uuid, text)',
        'instagram_reservar_publicacoes(text, integer, interval)',
        'instagram_salvar_container(uuid, text)',
        'instagram_concluir_publicacao(uuid, text, text)',
        'instagram_registrar_falha(uuid, text, text, boolean, interval)',
        'instagram_marcar_verificar(uuid, text)'
    ] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
end $$;
