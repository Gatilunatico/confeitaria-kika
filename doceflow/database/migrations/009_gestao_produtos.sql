-- DoceFlow · 009 · Gestão de produtos (Etapa 3)
-- Rodar depois da 008. Idempotente e não destrutiva.
--
-- 1. produtos ganha "destaque" (vitrine) e "prazo_producao_dias" (tempo estimado de produção).
-- 2. A administradora pode EXCLUIR produtos da própria confeitaria (RLS). Produtos com
--    orçamentos ou pedidos registrados não podem ser excluídos (FKs sem cascade): o
--    histórico é preservado e a orientação é despublicar.
-- 3. Limite de fotos por produto, garantido no banco (não só na tela).
-- 4. definir_foto_principal(): troca a foto principal numa única transação, com o RLS
--    da própria administradora (SECURITY INVOKER).

-- ---------------------------------------------------------------- produtos
alter table public.produtos add column if not exists destaque boolean not null default false;
alter table public.produtos add column if not exists prazo_producao_dias smallint;

do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'produtos_prazo_producao_check') then
        alter table public.produtos add constraint produtos_prazo_producao_check
            check (prazo_producao_dias is null or prazo_producao_dias between 0 and 90);
    end if;
end $$;

grant update (destaque, prazo_producao_dias) on public.produtos to authenticated;
grant delete on public.produtos to authenticated;

drop policy if exists produtos_admin_delete on public.produtos;
create policy produtos_admin_delete on public.produtos
    for delete to authenticated using (public.is_store_admin(confeitaria_id));

-- ---------------------------------------------------------------- limite de fotos
create or replace function public.product_images_limite()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    -- serializa inserções do mesmo produto para a contagem ser confiável
    perform 1 from public.produtos where id = new.produto_id for update;
    if (select count(*) from public.product_images where produto_id = new.produto_id) >= 10 then
        raise exception 'limite_fotos' using errcode = '22023';
    end if;
    return new;
end;
$$;

drop trigger if exists product_images_limite on public.product_images;
create trigger product_images_limite before insert on public.product_images
    for each row execute function public.product_images_limite();

-- ---------------------------------------------------------------- foto principal
create or replace function public.definir_foto_principal(p_image_id uuid)
returns void
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_produto uuid;
    v_conf    uuid;
begin
    select produto_id, confeitaria_id into v_produto, v_conf
      from public.product_images where id = p_image_id;
    if v_produto is null or not public.is_store_admin(v_conf) then
        raise exception 'foto_invalida' using errcode = '22023';
    end if;
    update public.product_images set principal = false where produto_id = v_produto and principal;
    update public.product_images set principal = true where id = p_image_id;
end;
$$;

revoke all on function public.definir_foto_principal(uuid) from public, anon;
grant execute on function public.definir_foto_principal(uuid) to authenticated;
