# Etapa 2: banco, autenticação e controle de acesso

**Data:** 2026-11-14 · **Branch:** `dev` · **Commit base:** `ed908c9`

## 1. Auditoria do schema antes das mudanças

Diagnóstico feito no Supabase real, só com leitura (detalhes em `database/schema_reference.md`):
- Existiam `confeitarias`, `produtos` (27), `leads` (3, reais) e `leads_antiga` (vazia).
- A autorização era feita **por uma coluna única**, `confeitarias.owner_user_id`. Ela não permite equipe, e o vínculo ficava na mesma tabela pública da loja.
- A migração 004 (marketing) não estava aplicada. Não havia pedidos, fotos nem tabela do Instagram.

## 2. Entregáveis

| # | Entregável | Onde |
|---|---|---|
| 1 | Migrações SQL numeradas | `database/migrations/005` a `008` (idempotentes e não destrutivas) |
| 2 | Políticas RLS | todas as tabelas, usando `is_store_admin()` (seção 3 do schema) |
| 3 | Configuração do Supabase Auth | seção 4 deste relatório |
| 4 | Login e logout | `pages/admin/login.py` e `services/auth_service.py` (Supabase Auth; `sign_out` ao sair) |
| 5 | Camada de autorização | **no banco:** RLS, permissões por coluna e funções SECURITY DEFINER. **No servidor do app:** `require_admin()` em toda página admin, revalidando o usuário no Supabase Auth e o perfil ativo em `admin_profiles` a cada carregamento |
| 6 | Storage | buckets `product-images` (leitura pública, escrita só da dona na própria pasta) e `marketing` (privado) |
| 7 | Documentação do schema | `database/schema_reference.md` |
| 8 | Relatório dos testes | seção 5 |

**Mudanças no app:**
- Busca da confeitaria pela tabela `admin_profiles`.
- Campo **"Publicado na vitrine"** no cadastro de produtos, e a vitrine mostra só os publicados.
- `services/order_service.py` (validação de pedidos) e métodos de pedidos no repositório Supabase (`create_order` pela função `criar_pedido`, `list_orders`, `update_order`).
- `services/image_service.py`: valida o conteúdo real da foto, grava na pasta da própria confeitaria e apaga o arquivo se o registro falhar.
- Mensagens novas para limite de envios e itens inválidos.

## 3. Regras de segurança atendidas

| Regra pedida | Como foi garantida |
|---|---|
| 1. Supabase Auth na administração | login por e-mail e senha no Supabase Auth, com a chave publishable |
| 2. RLS nas tabelas | RLS ativa em **todas** as tabelas `public` e em `storage.objects` |
| 3. Visitante sem leads ou pedidos | `anon` não tem nenhuma permissão nessas tabelas. Grava só pelas funções, que devolvem apenas o próprio registro |
| 4. Usuário não muda o próprio papel nem a confeitaria | `admin_profiles` só permite leitura do próprio perfil. Não há permissão de escrita, e `owner_user_id`, `slug` e `ativo` não são editáveis |
| 5. Operações restritas à confeitaria autorizada | todas as políticas usam `is_store_admin(confeitaria_id)`, e as FKs compostas impedem misturar confeitarias |
| 6. Storage protegido | políticas de insert, update, delete e select por pasta da confeitaria. O bucket de marketing é privado |
| 7. `st.session_state` não é a única barreira | o banco recusa mesmo com a sessão forjada (testado). O app revalida o usuário e o perfil no servidor |
| 8. Sem `service_role` | o app usa só a chave publishable. `SUPABASE_DB_URL` é só local, e o token do Instagram fica no Vault |
| Fluxos públicos | `criar_lead` e `criar_pedido` (SECURITY DEFINER): validam dados, limitam abusos e usam o slug configurado no servidor |
| Multi-tenant | `confeitaria_id` em todas as entidades, FKs compostas e testes com 2 confeitarias |

## 4. Configuração do Supabase Auth (feita no painel)

1. **Authentication → Sign In / Providers:** deixar **Email** ativo e **desativar "Allow new users to sign up"**. Só quem você criar consegue entrar.
2. **Authentication → Users:** criar a dona com **Auto Confirm**, e depois rodar `select public.cadastrar_admin('email', 'kika-cakes');` no SQL Editor.
3. **Senha:** em Authentication → Policies (ou Password), mínimo de 10 caracteres.
4. **Chaves:** o app e o Streamlit Cloud usam **só** a publishable. Nunca coloque a `service_role` ou `secret` em `.env` de deploy, nos Secrets do Streamlit ou no repositório.
5. **Revisar usuários:** hoje existem **2 usuários** no Auth. Depois da migração 005, só a dona vinculada vira perfil. O outro usuário **consegue fazer login, mas não acessa nada**. Se não for necessário, remova-o em Authentication → Users.

## 5. Testes de segurança

**Resultado:** `316 passed, 1 skipped`.
- **57 testes no PostgreSQL 16 real**, com as migrações 001 a 008 aplicadas **duas vezes** (idempotência), papéis `anon` e `authenticated`, `auth.uid()` e Storage emulados.
- O cenário tem **2 confeitarias**, 2 donas, um usuário logado **sem perfil** e o visitante.
- Mais 26 testes da camada do app.
- O único teste pulado é o de `leads_antiga`, uma tabela que só existe em produção.

| Teste obrigatório | Testes | Resultado |
|---|---|---|
| Visitante não abre o painel administrativo | `test_visitor_cannot_open_admin_pages` (4 páginas), sessão forjada | ✅ |
| Visitante não consulta pedidos | `test_visitor_cannot_read_private_tables[orders/order_items]` | ✅ |
| Visitante não consulta leads | `...[leads/admin_profiles/marketing_posts/instagram_accounts]` | ✅ |
| Proprietária vê seus produtos | `test_owner_sees_own_products_including_unpublished` | ✅ |
| Proprietária cadastra e edita produtos | `test_owner_creates_and_edits_products`, `test_owner_toggles_published_in_product_form` | ✅ |
| Proprietária consulta pedidos da sua confeitaria | `test_owner_reads_and_updates_own_orders` | ✅ |
| Admin de outra confeitaria não consulta esses registros | `test_other_store_admin_cannot_read_records` (orders, items, leads), `..._cannot_modify_records` (4), `..._cannot_insert_into_other_store` | ✅ |
| Não autenticado não executa operações admin | `test_unauthenticated_cannot_run_admin_operations` (8 operações, inclusive `cadastrar_admin`) | ✅ |
| Arquivos privados não são acessados indevidamente | `test_private_marketing_files_are_protected`, `test_product_photos_only_admin_writes_own_folder`, `test_buckets_configuration` | ✅ |

**Testes extras:**
- **Papel e vínculo:** a usuária não muda papel nem confeitaria, não insere ou apaga perfil e não se torna dona (6 testes). Perfil inativo perde o acesso.
- **Bootstrap:** `cadastrar_admin` recusa usuário de outra confeitaria e e-mail inexistente.
- **Pedido público:** funciona e não duplica. Tem 10 validações, inclusive **produto de outra confeitaria** e mais de 20 itens.
- **Limite de envios:** pedidos e orçamentos somam juntos.
- **Produto despublicado:** não aparece na vitrine nem aceita pedido ou orçamento, mesmo contornando a página.
- **Consistência:** `order_items` não mistura confeitarias (FK composta), e a foto só pode ficar na pasta da própria confeitaria e do próprio produto.
- **Instagram:** o token não é legível nem gravável pelo app.
- **Upload:** valida o conteúdo real (recusa HTML disfarçado e GIF), bloqueia path traversal e apaga o arquivo se o registro falhar.

## 6. Pendências e limitações

1. **Migrações 004 a 008 aplicadas em produção em 14/11**, numa transação única. A verificação depois, só de leitura, confirmou:
   - RLS ativa em todas as tabelas, e as 6 tabelas novas existem.
   - Os 3 leads e os 27 produtos foram mantidos, todos publicados.
   - A dona virou perfil `proprietaria` ativo da `kika-cakes`.
   - Buckets: `marketing` privado e `product-images` público, ambos com limite de 5 MB.
   - O visitante não executa `cadastrar_admin`. Pela chave publishable, a vitrine carrega os 27 produtos, e `leads`, `orders` e `admin_profiles` são recusados.
2. **Telas** de pedidos (painel), de fotos de produtos e do Instagram ainda não existem. Esta etapa entregou a estrutura, a autorização e os serviços.
3. **Pedidos no SQLite local:** não emulados. A mensagem informa que exigem o Supabase.
4. **Limite de envios** por WhatsApp e por confeitaria, e não por IP: o banco não recebe o IP do visitante. Para limite por IP seria preciso uma Edge Function ou um captcha.
5. **`leads_antiga` e o segundo usuário do Auth:** não mexi. Precisam da sua decisão.
