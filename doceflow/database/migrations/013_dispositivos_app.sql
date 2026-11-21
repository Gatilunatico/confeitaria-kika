-- DoceFlow · 013 · Celulares da confeiteira para notificações (push)
-- Rodar depois da 012. Idempotente e NÃO destrutiva (só cria a tabela nova e uma função).
--
-- O app registra o token do Firebase Cloud Messaging (FCM) do celular depois do login. A futura
-- Edge Function de "pedido novo" lê esta tabela NO SERVIDOR do Supabase para avisar a dona.
--
-- Regras:
-- * Só quem tem perfil administrativo ativo registra um celular, e sempre na própria confeitaria.
-- * Cada pessoa vê e remove só os próprios celulares. Visitante não tem acesso nenhum.
-- * O mesmo celular (token) pode trocar de conta (ex.: reinstalação): o registro passa para a
--   conta que entrou por último. Por isso a gravação é feita por função, e não direto na tabela.

create table if not exists public.admin_devices (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    confeitaria_id  uuid not null references public.confeitarias (id) on delete cascade,
    token           text not null unique check (char_length(token) between 20 and 4096),
    plataforma      text not null default 'android' check (plataforma in ('android', 'ios')),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index if not exists admin_devices_confeitaria_idx on public.admin_devices (confeitaria_id);
create index if not exists admin_devices_user_idx on public.admin_devices (user_id);

drop trigger if exists admin_devices_updated_at on public.admin_devices;
create trigger admin_devices_updated_at before update on public.admin_devices
    for each row execute function public.set_updated_at();

alter table public.admin_devices enable row level security;
revoke all on public.admin_devices from public, anon, authenticated;
grant select, delete on public.admin_devices to authenticated;   -- gravar: só pela função abaixo

drop policy if exists admin_devices_self_read on public.admin_devices;
create policy admin_devices_self_read on public.admin_devices
    for select to authenticated using (user_id = auth.uid());
drop policy if exists admin_devices_self_delete on public.admin_devices;
create policy admin_devices_self_delete on public.admin_devices
    for delete to authenticated using (user_id = auth.uid());

create or replace function public.registrar_dispositivo(p_token text, p_plataforma text default 'android')
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_conf uuid;
    v_id   uuid;
    v_tok  text := btrim(coalesce(p_token, ''));
begin
    select a.confeitaria_id into v_conf
      from public.admin_profiles a
     where a.user_id = auth.uid() and a.ativo
     limit 1;
    if v_conf is null or not public.is_store_admin(v_conf) then
        raise exception 'sem_permissao' using errcode = '42501';
    end if;
    if char_length(v_tok) < 20 or char_length(v_tok) > 4096 or v_tok ~ '\s' then
        raise exception 'token_invalido' using errcode = '22023';
    end if;
    if p_plataforma is null or p_plataforma not in ('android', 'ios') then
        raise exception 'plataforma_invalida' using errcode = '22023';
    end if;
    insert into public.admin_devices (user_id, confeitaria_id, token, plataforma)
    values (auth.uid(), v_conf, v_tok, p_plataforma)
    on conflict (token) do update
        set user_id = excluded.user_id, confeitaria_id = excluded.confeitaria_id,
            plataforma = excluded.plataforma, updated_at = now()
    returning admin_devices.id into v_id;
    return v_id;
end;
$$;
revoke all on function public.registrar_dispositivo(text, text) from public, anon;
grant execute on function public.registrar_dispositivo(text, text) to authenticated;
