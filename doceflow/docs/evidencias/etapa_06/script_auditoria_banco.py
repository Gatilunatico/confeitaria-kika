"""Auditoria SOMENTE LEITURA do Supabase de produção: RLS, permissões, funções e Storage."""
import sys

# `connect()` abre uma conexão psycopg com SUPABASE_DB_URL (só no computador da equipe, nunca no Cloud)
# e devolve (conexão, segredo) sem imprimir a senha. Todas as consultas abaixo são somente leitura.
from sbconn import connect  # noqa: E402

c, _ = connect()
with c.transaction():
    c.execute("set transaction read only")
    q = lambda s, p=(): c.execute(s, p).fetchall()  # noqa: E731

    print("== RLS por tabela (schema public) ==")
    for name, rls, forced in q("""select c.relname, c.relrowsecurity, c.relforcerowsecurity from pg_class c
                                  where c.relnamespace = 'public'::regnamespace and c.relkind = 'r' order by 1"""):
        print(f"  {name:22} RLS={'sim' if rls else 'NÃO'}")
    print("  storage.objects       RLS=", q("select relrowsecurity from pg_class where oid='storage.objects'::regclass")[0][0])

    for role in ("anon", "authenticated"):
        print(f"\n== Permissões de tabela: {role} ==")
        rows = q("""select table_name, string_agg(privilege_type, ',' order by privilege_type)
                    from information_schema.role_table_grants
                    where grantee = %s and table_schema = 'public' group by 1 order by 1""", (role,))
        for t, privs in rows:
            print(f"  {t:22} {privs}")
        cols = q("""select table_name, privilege_type, string_agg(column_name, ',' order by column_name)
                    from information_schema.column_privileges
                    where grantee = %s and table_schema = 'public' and privilege_type in ('UPDATE','INSERT')
                      and (table_name, privilege_type) not in (
                          select table_name, privilege_type from information_schema.role_table_grants
                          where grantee = %s and table_schema = 'public')
                    group by 1, 2 order by 1, 2""", (role, role))
        for t, p, cs in cols:
            print(f"  {t:22} {p} só nas colunas: {cs}")

    print("\n== Funções do schema public executáveis por anon ==")
    for name, args, definer in q("""select p.proname, pg_get_function_identity_arguments(p.oid), p.prosecdef
                                    from pg_proc p where p.pronamespace = 'public'::regnamespace
                                      and has_function_privilege('anon', p.oid, 'execute') order by 1"""):
        print(f"  {name}({args[:60]}{'…' if len(args) > 60 else ''}) {'SECURITY DEFINER' if definer else 'invoker'}")
    print("\n== Funções SECURITY DEFINER NÃO executáveis por anon ==")
    for name, auth in q("""select p.proname, has_function_privilege('authenticated', p.oid, 'execute')
                           from pg_proc p where p.pronamespace = 'public'::regnamespace and p.prosecdef
                             and not has_function_privilege('anon', p.oid, 'execute') order by 1"""):
        print(f"  {name} (authenticated pode executar: {auth})")

    print("\n== Políticas (public) ==")
    for t, pol, cmd, roles in q("""select tablename, policyname, cmd, array_to_string(roles, ',') from pg_policies
                                   where schemaname = 'public' order by 1, 2"""):
        print(f"  {t:20} {cmd:7} {roles:22} {pol}")
    print("\n== Políticas (storage.objects) ==")
    for pol, cmd, roles in q("""select policyname, cmd, array_to_string(roles, ',') from pg_policies
                                where schemaname = 'storage' and tablename = 'objects' order by 1"""):
        print(f"  {cmd:7} {roles:15} {pol}")
    print("\n== Buckets ==")
    for b in q("select id, public, file_size_limit, allowed_mime_types from storage.buckets order by 1"):
        print("  ", b)
    print("  objetos por bucket:", q("select bucket_id, count(*) from storage.objects group by 1"))

    print("\n== Instagram / Vault ==")
    print("  contas:", q("select count(*), count(token_vault_id) from public.instagram_accounts"))
    print("  token_vault_id legível por authenticated:",
          q("select has_column_privilege('authenticated', 'public.instagram_accounts', 'token_vault_id', 'select')")[0][0],
          "| por anon:", q("select has_column_privilege('anon', 'public.instagram_accounts', 'token_vault_id', 'select')")[0][0])
    print("  extensão vault instalada:", q("select count(*) > 0 from pg_extension where extname = 'supabase_vault'")[0][0])

    print("\n== Auth ==")
    print("  usuários / com perfil admin:", q("""select (select count(*) from auth.users),
                                                  (select count(*) from public.admin_profiles where ativo)"""))
