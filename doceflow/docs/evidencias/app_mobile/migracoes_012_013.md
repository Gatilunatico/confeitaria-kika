# Migrações 012 e 013 em produção (21/11/2026)

Aplicadas com autorização da equipe ("Sim, pode aplicar"), numa única transação, pelo pooler de transações (porta 6543), com `set transaction read write`.

## Antes (consulta somente leitura)

| Verificação | Resultado |
|---|---|
| PostgreSQL | 17.11 |
| Objetos novos já existentes | nenhum |
| Pedidos com o mesmo `lead_id` (bloquearia o índice único) | 0 |
| Linhas em orders / leads / produtos | 0 / 3 / 27 |
| Publicação `supabase_realtime` | existe, sem tabelas do `public` |
| Gatilhos em `produtos` | `produtos_updated_at` |

## Aplicação

`012_app_mobile.sql` e `013_dispositivos_app.sql` foram aplicadas na mesma transação: **COMMIT ok**.

## Depois

| Verificação | Resultado |
|---|---|
| `painel_indicadores`, `clientes_resumo`, `converter_orcamento_em_pedido`, `admin_devices`, `orders_lead_unico_idx`, `registrar_dispositivo` | todos criados |
| EXECUTE para o visitante (`anon`) nas 4 funções novas | **não** |
| EXECUTE para `authenticated` | sim (o gatilho `produtos_slug_automatico`, para ninguém) |
| `clientes_resumo` | `security_invoker=true`; visitante não lê; ninguém insere |
| `admin_devices` | RLS ligado; visitante não lê; ninguém insere direto (só pela função) |
| Realtime | `leads` e `orders` |
| Gatilhos em `produtos` | `produtos_slug_automatico` e `produtos_updated_at` |
| Dados | orders / leads / produtos continuam 0 / 3 / 27 |
| Indicadores lidos como a dona (transação somente leitura) | 3 orçamentos e 0 pedidos, iguais às tabelas |
| Clientes visíveis para a dona | 2 (os 3 orçamentos são de 2 números de WhatsApp) |
| Reexecução das duas migrações (desfeita no fim) | sem erro: são idempotentes |
| Visitante pela API pública: RPCs `painel_indicadores`, `registrar_dispositivo` e `converter_orcamento_em_pedido` | HTTP 401, código 42501 |
| Visitante lê `clientes_resumo` e `admin_devices` | HTTP 401 |
| Vitrine continua lendo `produtos` | HTTP 200 |
