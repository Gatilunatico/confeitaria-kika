-- DoceFlow · Etapa 04 · Painel administrativo
-- Rodar depois de 001_schema_leads.sql. Idempotente (pode rodar de novo).
--
-- 1. Novo funil de status: Novo, Em atendimento, Orçamento enviado, Venda concluída, Perdido.
-- 2. Registro de quando o status mudou (status_atualizado_em).
-- 3. A dona (authenticated) pode cadastrar e editar produtos SOMENTE da sua confeitaria.

-- ---------------------------------------------------------------- status dos leads
alter table public.leads drop constraint if exists leads_status_check;

update public.leads
   set status = case status
                    when 'Em contato' then 'Em atendimento'
                    when 'Fechado'    then 'Venda concluída'
                    else status
                end
 where status in ('Em contato', 'Fechado');

alter table public.leads add constraint leads_status_check
    check (status in ('Novo', 'Em atendimento', 'Orçamento enviado', 'Venda concluída', 'Perdido'));

alter table public.leads add column if not exists status_atualizado_em timestamptz;

create or replace function public.set_status_atualizado_em() returns trigger
language plpgsql as $$
begin
    if new.status is distinct from old.status then
        new.status_atualizado_em := now();
    end if;
    return new;
end;
$$;

drop trigger if exists leads_status_atualizado_em on public.leads;
create trigger leads_status_atualizado_em before update of status on public.leads
    for each row execute function public.set_status_atualizado_em();

-- ---------------------------------------------------------------- produtos: escrita da dona
grant insert on public.produtos to authenticated;
grant update (nome, categoria, descricao, unidade, preco, tipo_preco, disponivel, imagem,
              qtd_min, qtd_max, ordem) on public.produtos to authenticated;
-- slug e confeitaria_id não podem ser alterados depois de criados (não estão no GRANT de update).

drop policy if exists produtos_owner_insert on public.produtos;
create policy produtos_owner_insert on public.produtos
    for insert to authenticated
    with check (exists (select 1 from public.confeitarias c
                        where c.id = confeitaria_id and c.owner_user_id = auth.uid()));

drop policy if exists produtos_owner_update on public.produtos;
create policy produtos_owner_update on public.produtos
    for update to authenticated
    using (exists (select 1 from public.confeitarias c
                   where c.id = confeitaria_id and c.owner_user_id = auth.uid()))
    with check (exists (select 1 from public.confeitarias c
                        where c.id = confeitaria_id and c.owner_user_id = auth.uid()));
