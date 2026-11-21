-- Emula o mínimo do ambiente Supabase num PostgreSQL puro, só para os testes:
-- papéis anon/authenticated, schema auth, auth.users e auth.uid().
do $$ begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
end $$;

create schema if not exists auth;
create table if not exists auth.users (id uuid primary key, email text);

create or replace function auth.uid() returns uuid
language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

grant usage on schema public, auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;

-- Storage (mínimo para testar buckets e políticas em storage.objects, como no Supabase)
create schema if not exists storage;
create table if not exists storage.buckets (
    id text primary key, name text not null, public boolean not null default false,
    file_size_limit bigint, allowed_mime_types text[], created_at timestamptz default now()
);
create table if not exists storage.objects (
    id uuid primary key default gen_random_uuid(),
    bucket_id text references storage.buckets (id),
    name text not null,
    owner uuid default auth.uid(),
    created_at timestamptz default now(),
    unique (bucket_id, name)
);
alter table storage.objects enable row level security;
grant usage on schema storage to anon, authenticated;
grant select on storage.buckets to anon, authenticated;
grant select, insert, update, delete on storage.objects to anon, authenticated;
-- Igual à função do Supabase: pastas do caminho (sem o nome do arquivo)
create or replace function storage.foldername(name text) returns text[]
language sql immutable as $$
    select (string_to_array(name, '/'))[1:array_length(string_to_array(name, '/'), 1) - 1]
$$;
grant execute on function storage.foldername(text) to anon, authenticated;

-- Vault (mínimo, como no Supabase): segredos guardados fora das tabelas do app.
-- No Supabase real os segredos são cifrados; aqui só emulamos a interface usada pela migração 014.
create schema if not exists vault;
create table if not exists vault.secrets (
    id uuid primary key default gen_random_uuid(),
    name text unique,
    description text not null default '',
    secret text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create or replace function vault.create_secret(new_secret text, new_name text default null,
                                               new_description text default '', new_key_id uuid default null)
returns uuid language sql as $$
    insert into vault.secrets (secret, name, description) values (new_secret, new_name, new_description) returning id
$$;
create or replace function vault.update_secret(secret_id uuid, new_secret text default null, new_name text default null,
                                               new_description text default null, new_key_id uuid default null)
returns void language sql as $$
    update vault.secrets set secret = coalesce(new_secret, secret), name = coalesce(new_name, name),
           description = coalesce(new_description, description), updated_at = now() where id = secret_id
$$;
create or replace view vault.decrypted_secrets as
    select id, name, description, secret, secret as decrypted_secret, created_at, updated_at from vault.secrets;
revoke all on schema vault from public, anon, authenticated;
