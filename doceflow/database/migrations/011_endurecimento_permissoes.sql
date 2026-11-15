-- DoceFlow · 011 · Endurecimento de permissões (Etapa 6: auditoria de segurança)
-- Rodar depois da 010. Idempotente e NÃO destrutiva: só retira permissões, não apaga dados.
--
-- Achados da auditoria somente leitura em produção (docs/evidencias/etapa_06):
-- 1. public.leads_antiga (tabela legada, vazia, só existe em produção) tinha TODAS as permissões
--    padrão do Supabase para anon e authenticated, inclusive TRUNCATE e TRIGGER. O RLS bloqueia
--    SELECT/INSERT/UPDATE/DELETE pela API, mas TRUNCATE não passa pelo RLS. A tabela continua
--    existindo (apagá-la depende de decisão da equipe); só o acesso público é retirado.
-- 2. Funções de gatilho (set_updated_at, set_status_atualizado_em, product_images_limite) estavam
--    executáveis por anon. Gatilhos não dependem de EXECUTE para disparar; a permissão é
--    desnecessária e é retirada (privilégio mínimo).

do $$
begin
    if to_regclass('public.leads_antiga') is not null then
        execute 'revoke all on public.leads_antiga from anon, authenticated';
    end if;
end $$;

revoke execute on function public.set_updated_at() from public, anon, authenticated;
revoke execute on function public.set_status_atualizado_em() from public, anon, authenticated;
revoke execute on function public.product_images_limite() from public, anon, authenticated;
