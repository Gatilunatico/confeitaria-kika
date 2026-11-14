-- DoceFlow · 008 · Conta do Instagram por confeitaria (estrutura para integração futura)
-- Rodar depois da 007. Idempotente e não destrutiva.
--
-- Guarda só METADADOS da conta. O token de acesso da Meta NUNCA fica nesta tabela nem no
-- navegador: deve ficar no Supabase Vault (ou nos secrets de uma Edge Function), e aqui só a
-- referência token_vault_id, que nem a própria administradora consegue ler pela API.

create table if not exists public.instagram_accounts (
    id               uuid primary key default gen_random_uuid(),
    confeitaria_id   uuid not null unique references public.confeitarias (id) on delete cascade,
    username         text check (username is null or username ~ '^[A-Za-z0-9._]{1,30}$'),
    ig_user_id       text,
    status           text not null default 'desconectado' check (status in ('desconectado', 'conectado', 'erro')),
    token_vault_id   uuid,
    token_expira_em  timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

drop trigger if exists instagram_accounts_updated_at on public.instagram_accounts;
create trigger instagram_accounts_updated_at before update on public.instagram_accounts
    for each row execute function public.set_updated_at();

alter table public.instagram_accounts enable row level security;
revoke all on public.instagram_accounts from anon, authenticated;
-- sem token_vault_id nas permissões de coluna: não é legível nem gravável pelo app
grant select (id, confeitaria_id, username, ig_user_id, status, token_expira_em, created_at, updated_at)
    on public.instagram_accounts to authenticated;
grant insert (confeitaria_id, username) on public.instagram_accounts to authenticated;
grant update (username) on public.instagram_accounts to authenticated;

drop policy if exists instagram_admin_read on public.instagram_accounts;
create policy instagram_admin_read on public.instagram_accounts
    for select to authenticated using (public.is_store_admin(confeitaria_id));
drop policy if exists instagram_admin_insert on public.instagram_accounts;
create policy instagram_admin_insert on public.instagram_accounts
    for insert to authenticated with check (public.is_store_admin(confeitaria_id));
drop policy if exists instagram_admin_update on public.instagram_accounts;
create policy instagram_admin_update on public.instagram_accounts
    for update to authenticated
    using (public.is_store_admin(confeitaria_id)) with check (public.is_store_admin(confeitaria_id));
