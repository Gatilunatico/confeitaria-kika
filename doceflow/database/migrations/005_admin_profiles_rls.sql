-- DoceFlow · 005 · Perfis administrativos e autorização centralizada no banco
-- Rodar depois de 001–004. Idempotente e NÃO destrutiva (não apaga tabelas nem dados).
--
-- O que muda:
-- 1. Nova tabela admin_profiles (usuário do Supabase Auth -> confeitaria + papel).
--    O usuário só LÊ o próprio perfil: não pode criar, trocar papel nem mudar de confeitaria.
-- 2. Função is_store_admin(confeitaria_id): única regra de autorização usada pelas políticas.
-- 3. Donas atuais (confeitarias.owner_user_id) viram perfis 'proprietaria' (coluna mantida).
-- 4. produtos ganha "publicado" (o que aparece na vitrine) e chave (id, confeitaria_id)
--    para relações consistentes por confeitaria (multi-tenant).
-- 5. Políticas de confeitarias, produtos, leads, marketing_posts e Storage passam a usar
--    is_store_admin. A dona pode editar nome e WhatsApp da própria confeitaria.
-- 6. cadastrar_admin(): procedimento seguro para o primeiro administrador (só no SQL Editor).

-- ---------------------------------------------------------------- admin_profiles
create table if not exists public.admin_profiles (
    user_id        uuid primary key references auth.users (id) on delete cascade,
    confeitaria_id uuid not null references public.confeitarias (id) on delete cascade,
    papel          text not null default 'proprietaria' check (papel in ('proprietaria', 'equipe')),
    ativo          boolean not null default true,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
create index if not exists admin_profiles_confeitaria_idx on public.admin_profiles (confeitaria_id);

drop trigger if exists admin_profiles_updated_at on public.admin_profiles;
create trigger admin_profiles_updated_at before update on public.admin_profiles
    for each row execute function public.set_updated_at();

alter table public.admin_profiles enable row level security;
revoke all on public.admin_profiles from anon, authenticated;
grant select on public.admin_profiles to authenticated;   -- sem insert/update/delete: ninguém altera o próprio papel

drop policy if exists admin_profiles_self_read on public.admin_profiles;
create policy admin_profiles_self_read on public.admin_profiles
    for select to authenticated using (user_id = auth.uid());

-- Donas já cadastradas na coluna antiga viram perfis (sem duplicar)
insert into public.admin_profiles (user_id, confeitaria_id, papel)
select c.owner_user_id, c.id, 'proprietaria'
  from public.confeitarias c
 where c.owner_user_id is not null
on conflict (user_id) do nothing;

-- ---------------------------------------------------------------- autorização
create or replace function public.is_store_admin(p_confeitaria_id uuid) returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1
          from public.admin_profiles a
          join public.confeitarias c on c.id = a.confeitaria_id
         where a.user_id = auth.uid()
           and a.confeitaria_id = p_confeitaria_id
           and a.ativo
           and c.ativo
    )
$$;
revoke all on function public.is_store_admin(uuid) from public;
grant execute on function public.is_store_admin(uuid) to anon, authenticated;

-- Primeiro administrador: rodar no SQL Editor (papel postgres). Não pode ser chamado pelo app.
--   select public.cadastrar_admin('email@da.dona', 'kika-cakes');
create or replace function public.cadastrar_admin(p_email text, p_confeitaria_slug text,
                                                  p_papel text default 'proprietaria')
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_user uuid;
    v_conf uuid;
    v_atual uuid;
begin
    select u.id into v_user from auth.users u where lower(u.email) = lower(btrim(p_email));
    if v_user is null then
        raise exception 'usuario_nao_encontrado: crie o usuário em Authentication > Users primeiro';
    end if;
    select c.id into v_conf from public.confeitarias c where c.slug = p_confeitaria_slug;
    if v_conf is null then
        raise exception 'confeitaria_nao_encontrada';
    end if;
    select a.confeitaria_id into v_atual from public.admin_profiles a where a.user_id = v_user;
    if v_atual is not null and v_atual <> v_conf then
        raise exception 'usuario_ja_administra_outra_confeitaria';
    end if;
    insert into public.admin_profiles (user_id, confeitaria_id, papel, ativo)
    values (v_user, v_conf, p_papel, true)
    on conflict (user_id) do update set papel = excluded.papel, ativo = true;
    return v_user;
end;
$$;
revoke all on function public.cadastrar_admin(text, text, text) from public, anon, authenticated;

-- ---------------------------------------------------------------- consistência multi-tenant
alter table public.produtos add column if not exists publicado boolean not null default true;
create unique index if not exists produtos_id_confeitaria_uidx on public.produtos (id, confeitaria_id);
create unique index if not exists leads_id_confeitaria_uidx on public.leads (id, confeitaria_id);

do $$ begin
    if not exists (select 1 from pg_constraint where conname = 'leads_produto_mesma_confeitaria_fk') then
        alter table public.leads add constraint leads_produto_mesma_confeitaria_fk
            foreign key (produto_id, confeitaria_id) references public.produtos (id, confeitaria_id) not valid;
        alter table public.leads validate constraint leads_produto_mesma_confeitaria_fk;
    end if;
end $$;

-- ---------------------------------------------------------------- confeitarias
grant update (nome, whatsapp) on public.confeitarias to authenticated;   -- slug, dona e ativo: só SQL Editor
drop policy if exists confeitarias_admin_update on public.confeitarias;
create policy confeitarias_admin_update on public.confeitarias
    for update to authenticated
    using (public.is_store_admin(id)) with check (public.is_store_admin(id));

-- ---------------------------------------------------------------- produtos
drop policy if exists produtos_public_read on public.produtos;
create policy produtos_public_read on public.produtos
    for select to anon, authenticated
    using (publicado and exists (select 1 from public.confeitarias c where c.id = confeitaria_id and c.ativo));

drop policy if exists produtos_admin_read on public.produtos;
create policy produtos_admin_read on public.produtos
    for select to authenticated using (public.is_store_admin(confeitaria_id));

grant insert on public.produtos to authenticated;
grant update (nome, categoria, descricao, unidade, preco, tipo_preco, disponivel, publicado, imagem,
              qtd_min, qtd_max, ordem) on public.produtos to authenticated;

drop policy if exists produtos_owner_insert on public.produtos;
drop policy if exists produtos_admin_insert on public.produtos;
create policy produtos_admin_insert on public.produtos
    for insert to authenticated with check (public.is_store_admin(confeitaria_id));

drop policy if exists produtos_owner_update on public.produtos;
drop policy if exists produtos_admin_update on public.produtos;
create policy produtos_admin_update on public.produtos
    for update to authenticated
    using (public.is_store_admin(confeitaria_id)) with check (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- leads
drop policy if exists leads_owner_read on public.leads;
drop policy if exists leads_admin_read on public.leads;
create policy leads_admin_read on public.leads
    for select to authenticated using (public.is_store_admin(confeitaria_id));

drop policy if exists leads_owner_update on public.leads;
drop policy if exists leads_admin_update on public.leads;
create policy leads_admin_update on public.leads
    for update to authenticated
    using (public.is_store_admin(confeitaria_id)) with check (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- marketing_posts (criada na 004)
drop policy if exists marketing_owner_all on public.marketing_posts;
drop policy if exists marketing_admin_all on public.marketing_posts;
create policy marketing_admin_all on public.marketing_posts
    for all to authenticated
    using (public.is_store_admin(confeitaria_id)) with check (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- Storage: bucket privado "marketing"
create or replace function public.storage_folder_admin(p_name text) returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1 from public.confeitarias c
         where c.id::text = split_part(p_name, '/', 1) and public.is_store_admin(c.id)
    )
$$;
revoke all on function public.storage_folder_admin(text) from public;
grant execute on function public.storage_folder_admin(text) to anon, authenticated;

drop policy if exists marketing_storage_owner_select on storage.objects;
drop policy if exists marketing_storage_owner_insert on storage.objects;
drop policy if exists marketing_storage_owner_update on storage.objects;
drop policy if exists marketing_storage_owner_delete on storage.objects;
drop policy if exists marketing_storage_admin_select on storage.objects;
drop policy if exists marketing_storage_admin_insert on storage.objects;
drop policy if exists marketing_storage_admin_update on storage.objects;
drop policy if exists marketing_storage_admin_delete on storage.objects;
create policy marketing_storage_admin_select on storage.objects for select to authenticated
    using (bucket_id = 'marketing' and public.storage_folder_admin(name));
create policy marketing_storage_admin_insert on storage.objects for insert to authenticated
    with check (bucket_id = 'marketing' and public.storage_folder_admin(name));
create policy marketing_storage_admin_update on storage.objects for update to authenticated
    using (bucket_id = 'marketing' and public.storage_folder_admin(name))
    with check (bucket_id = 'marketing' and public.storage_folder_admin(name));
create policy marketing_storage_admin_delete on storage.objects for delete to authenticated
    using (bucket_id = 'marketing' and public.storage_folder_admin(name));
