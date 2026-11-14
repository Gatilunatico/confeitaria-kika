-- DoceFlow · 004 · Estúdio de Marketing (posts do Instagram) + Supabase Storage
-- Rodar no SQL Editor depois das migrations 001–003. Idempotente.
--
-- Acesso: SOMENTE a dona logada (authenticated, owner_user_id da confeitaria)
-- lê, cria, altera e apaga posts e imagens da própria confeitaria.
-- Visitantes (anon) não têm acesso à tabela nem ao bucket (bucket PRIVADO).

create table if not exists public.marketing_posts (
    id              uuid primary key default gen_random_uuid(),
    confeitaria_id  uuid not null references public.confeitarias (id) on delete cascade,
    produto_id      uuid references public.produtos (id) on delete set null,
    produto_nome    text not null check (char_length(produto_nome) between 1 and 120),
    template        text not null check (template in ('produto', 'promocao', 'novidade')),
    formato         text not null check (formato in ('feed', 'story')),
    titulo          text not null default '' check (char_length(titulo) <= 120),
    preco_texto     text not null default '' check (char_length(preco_texto) <= 80),
    cta             text not null default '' check (char_length(cta) <= 60),
    tom             text not null check (tom in ('amigavel', 'promocional', 'elegante')),
    legenda         text not null default '' check (char_length(legenda) <= 2200),
    imagem_path     text check (imagem_path ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}\.png$'),
    status          text not null default 'Rascunho'
                    check (status in ('Rascunho', 'Pronto', 'Publicado manualmente')),
    created_by      uuid default auth.uid(),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists marketing_posts_conf_created_idx
    on public.marketing_posts (confeitaria_id, created_at desc);

drop trigger if exists marketing_posts_updated_at on public.marketing_posts;
create trigger marketing_posts_updated_at before update on public.marketing_posts
    for each row execute function public.set_updated_at();

alter table public.marketing_posts enable row level security;
revoke all on public.marketing_posts from anon, authenticated;
grant select, insert, update, delete on public.marketing_posts to authenticated;

drop policy if exists marketing_owner_all on public.marketing_posts;
create policy marketing_owner_all on public.marketing_posts
    for all to authenticated
    using (exists (select 1 from public.confeitarias c
                   where c.id = confeitaria_id and c.owner_user_id = auth.uid()))
    with check (exists (select 1 from public.confeitarias c
                        where c.id = confeitaria_id and c.owner_user_id = auth.uid()));

-- ---------------------------------------------------------------- Storage
-- Bucket privado, só PNG, até 5 MB. Caminho: <confeitaria_id>/<post_id>.png
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('marketing', 'marketing', false, 5242880, array['image/png'])
on conflict (id) do update
    set public = false, file_size_limit = 5242880, allowed_mime_types = array['image/png'];

drop policy if exists marketing_storage_owner_select on storage.objects;
create policy marketing_storage_owner_select on storage.objects
    for select to authenticated
    using (bucket_id = 'marketing' and exists (
        select 1 from public.confeitarias c
        where c.owner_user_id = auth.uid() and c.id::text = (storage.foldername(name))[1]));

drop policy if exists marketing_storage_owner_insert on storage.objects;
create policy marketing_storage_owner_insert on storage.objects
    for insert to authenticated
    with check (bucket_id = 'marketing' and exists (
        select 1 from public.confeitarias c
        where c.owner_user_id = auth.uid() and c.id::text = (storage.foldername(name))[1]));

drop policy if exists marketing_storage_owner_update on storage.objects;
create policy marketing_storage_owner_update on storage.objects
    for update to authenticated
    using (bucket_id = 'marketing' and exists (
        select 1 from public.confeitarias c
        where c.owner_user_id = auth.uid() and c.id::text = (storage.foldername(name))[1]));

drop policy if exists marketing_storage_owner_delete on storage.objects;
create policy marketing_storage_owner_delete on storage.objects
    for delete to authenticated
    using (bucket_id = 'marketing' and exists (
        select 1 from public.confeitarias c
        where c.owner_user_id = auth.uid() and c.id::text = (storage.foldername(name))[1]));
