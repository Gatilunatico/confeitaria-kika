-- DoceFlow · 006 · Fotos de produtos (tabela + Supabase Storage)
-- Rodar depois da 005. Idempotente e não destrutiva.
--
-- Fotos de produto são informação comercial PÚBLICA: o bucket "product-images" é de
-- leitura pública (URL pública), mas só administradores da confeitaria enviam,
-- trocam ou apagam arquivos, e só na pasta da própria confeitaria:
--   product-images/<confeitaria_id>/<produto_id>/<foto_id>.(jpg|png|webp)
-- Arquivos privados (artes de marketing) ficam no bucket PRIVADO "marketing" (004/005).

create table if not exists public.product_images (
    id             uuid primary key default gen_random_uuid(),
    confeitaria_id uuid not null references public.confeitarias (id) on delete cascade,
    produto_id     uuid not null,
    storage_path   text not null unique,
    alt_text       text not null default '' check (char_length(alt_text) <= 200),
    principal      boolean not null default false,
    ordem          integer not null default 0,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    foreign key (produto_id, confeitaria_id) references public.produtos (id, confeitaria_id) on delete cascade,
    -- o caminho no Storage precisa estar na pasta da própria confeitaria e do próprio produto
    check (storage_path ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f-]{36}\.(jpg|png|webp)$'
           and split_part(storage_path, '/', 1) = confeitaria_id::text
           and split_part(storage_path, '/', 2) = produto_id::text)
);
create index if not exists product_images_produto_idx on public.product_images (produto_id, ordem);
create unique index if not exists product_images_uma_principal_uidx
    on public.product_images (produto_id) where principal;

drop trigger if exists product_images_updated_at on public.product_images;
create trigger product_images_updated_at before update on public.product_images
    for each row execute function public.set_updated_at();

alter table public.product_images enable row level security;
revoke all on public.product_images from anon, authenticated;
grant select on public.product_images to anon, authenticated;
grant insert, delete on public.product_images to authenticated;
grant update (alt_text, principal, ordem) on public.product_images to authenticated;

drop policy if exists product_images_public_read on public.product_images;
create policy product_images_public_read on public.product_images
    for select to anon, authenticated
    using (exists (select 1 from public.produtos p join public.confeitarias c on c.id = p.confeitaria_id
                   where p.id = produto_id and p.publicado and c.ativo));

drop policy if exists product_images_admin_all on public.product_images;
create policy product_images_admin_all on public.product_images
    for all to authenticated
    using (public.is_store_admin(confeitaria_id)) with check (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- Storage
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('product-images', 'product-images', true, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update
    set public = true, file_size_limit = 5242880, allowed_mime_types = array['image/jpeg', 'image/png', 'image/webp'];

drop policy if exists product_images_storage_admin_select on storage.objects;
drop policy if exists product_images_storage_admin_insert on storage.objects;
drop policy if exists product_images_storage_admin_update on storage.objects;
drop policy if exists product_images_storage_admin_delete on storage.objects;
-- leitura pública acontece pela URL pública do bucket; listagem pela API só para administradores
create policy product_images_storage_admin_select on storage.objects for select to authenticated
    using (bucket_id = 'product-images' and public.storage_folder_admin(name));
create policy product_images_storage_admin_insert on storage.objects for insert to authenticated
    with check (bucket_id = 'product-images' and public.storage_folder_admin(name));
create policy product_images_storage_admin_update on storage.objects for update to authenticated
    using (bucket_id = 'product-images' and public.storage_folder_admin(name))
    with check (bucket_id = 'product-images' and public.storage_folder_admin(name));
create policy product_images_storage_admin_delete on storage.objects for delete to authenticated
    using (bucket_id = 'product-images' and public.storage_folder_admin(name));
