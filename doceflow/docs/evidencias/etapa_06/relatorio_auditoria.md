# Etapa 6: limpeza da interface, separação de acessos e auditoria de segurança

**Data:** 2026-11-14 · **Branch:** `dev` · **Commit base:** `b05cb03`

**Método:**
- Navegador automatizado (celular 375 px).
- `pytest` com PostgreSQL 16 real.
- Auditoria **somente leitura** do Supabase de produção.
- Varredura da árvore, de **todo o histórico do Git** e dos logs.

**Resultado:** `461 passed, 1 skipped`. São 41 testes novos nesta etapa.

## 1. Resumo dos achados por criticidade

| ID | Criticidade | Achado | Situação |
|---|---|---|---|
| E6-01 | **Média** | Com o banco fora do ar, a vitrine mostrava **"Detalhes técnicos (para a equipe)"**: `DB_BACKEND`, se os Secrets foram lidos, nomes de variáveis e o tipo e a mensagem do erro | ✅ Corrigido: o diagnóstico vai só para o log (`services/diagnostics.py`) |
| E6-02 | **Média** | `client.showErrorDetails = false` foi descontinuado no Streamlit 1.67 e **passou a significar "stacktrace"**. Um erro não tratado mostraria código e caminhos internos para a cliente | ✅ Corrigido: `"none"` e `showErrorLinks = false` |
| E6-03 | **Média** | Barra do topo com botões da plataforma (ícone do GitHub, "Fork", menu ⋮ e "Deploy" no Streamlit Cloud) e faixa e indicador de desenvolvimento | ✅ Corrigido: `components/app_chrome.py` nos dois apps. Limitação na seção 7 |
| E6-04 | **Média** | Um único app: o login do painel ficava no mesmo endereço da vitrine (`/admin`) | ✅ Código pronto: `public_app.py` + `admin_app.py`. ⏳ **Trocar a publicação** (seção 7) |
| E6-05 | **Média** | Produção: a tabela legada `leads_antiga` tinha **todas** as permissões para `anon` e `authenticated`, inclusive `TRUNCATE` e `TRIGGER` (o `TRUNCATE` não passa pelo RLS) | ✅ Corrigido: migração `011` **aplicada em produção**. Nenhum dado apagado |
| E6-06 | **Média** | O cadastro público do Supabase Auth está aberto. Quem se cadastra não vê dados (testado), mas pode gerar contas e e-mails em massa | ⏳ **Manual:** desativar "Allow new users to sign up" |
| E6-07 | **Média** | Limite de envios: 5 por hora por WhatsApp e 30 por minuto por loja. Variando números, alguém consegue **lotar o limite da loja** por alguns minutos e bloquear clientes reais (negação de serviço). Não há limite por IP | ⏳ Recomendação: Edge Function com limite por IP e captcha (seção 7) |
| E6-08 | Baixa | Funções de gatilho executáveis por visitantes (inofensivo: o Postgres recusa a chamada direta) | ✅ Corrigido na `011` |
| E6-09 | Baixa | Mensagem de desenvolvedor no login local ("defina ADMIN_PASSWORD no .env") | ✅ Trocada por uma mensagem neutra. O detalhe vai para o log |
| E6-10 | Baixa | Endereço inexistente mostra o aviso padrão do Streamlit **"Page not found"** (em inglês). Sem dados | Aceito: não é configurável no Streamlit 1.67 |
| E6-11 | Baixa | A tentativa de login bloqueia depois de 5 erros **por sessão do navegador**. Uma sessão nova recomeça a contagem | Aceito: no Supabase vale também o limite de tentativas do próprio Supabase Auth |
| — | **Crítica / Alta** | **Nenhum achado** | — |

## 2. Elementos visuais removidos (vitrine e painel)

| Elemento | Onde aparecia | Agora |
|---|---|---|
| Quadro "Detalhes técnicos (para a equipe)" | Catálogo, com o banco indisponível (captura `00_ANTES…`) | Só a mensagem amigável. Detalhes no log |
| Traceback de erro não tratado | Qualquer página (configuração antiga) | Desligado (`showErrorDetails = "none"`) |
| Links "pesquisar este erro" | Mensagens de erro | Desligados (`showErrorLinks = false`) |
| Barra de ações: GitHub, Fork e menu ⋮ | Topo, no Streamlit Cloud | Escondida (CSS por `data-testid`) |
| Botão "Deploy", faixa colorida e indicador "Running…" | Topo | Escondidos |
| Login do painel no domínio da vitrine | `/admin` do app combinado | No app público, a página não existe (captura `02`) |
| Texto "defina ADMIN_PASSWORD no .env" | Login (modo local) | Mensagem neutra |

**Mantido, sem nenhuma remoção comercial:**
- identidade visual, logo, catálogo, categorias e destaques;
- botões de orçamento, pedido e WhatsApp;
- aviso de privacidade;
- rodapé "Vitrine digital por DoceFlow" (marca do produto, não ferramenta de desenvolvimento).

**Verificação no navegador**, com o app público em 375 px (captura `01`):
- barra de ferramentas, menu, Deploy, faixa e indicador: **0 visíveis**;
- links da página: só `pedido` e `privacidade`;
- palavras técnicas (supabase, sqlite, streamlit, github, DB_BACKEND, traceback, secrets, python): **0**;
- 27 botões "Solicitar orçamento" e nenhuma rolagem para os lados.

## 3. Separação das aplicações

| Arquivo | Conteúdo |
|---|---|
| `public_app.py` | Catálogo (`/`), pedido (`/pedido`) e privacidade (`/privacidade`). Sem login, sem menu lateral |
| `admin_app.py` | Login (raiz), Painel, Pedidos, Orçamentos, Produtos e Estúdio de Marketing. Cada página chama `require_admin()` |
| `app.py` | **Legado.** O app combinado é mantido só para não derrubar a publicação atual até a troca |
| Compartilhados | `services/` (dados: o RLS decide o que cada um pode), `components/`, `config.py`, `database/` |

**Comprovado por teste (`test_etapa06_apps.py`):**
- O grafo de importações da vitrine **não inclui** `services.auth_service`, `marketing`, nem os componentes do painel (`image_manager`, `product_form`, `navigation`, `dashboard_metrics`, `data_table`).
- O app público registra só as 3 páginas públicas, e o administrativo só as 6 do painel.

**Navegador:**
- No app público, `/admin` e `/painel` voltam ao catálogo, sem dados e sem login.
- No app administrativo, `/painel` e `/pedidos` sem login levam ao login.
- Depois do login, aparece o menu só do painel e o botão do menu lateral continua funcionando.
- "Sair" volta ao login.

**Novo `PUBLIC_APP_URL`:** no painel, preenche automaticamente o link da vitrine no Estúdio de Marketing, já que os apps têm endereços diferentes.

## 4. Credenciais e segredos

Busca na árvore versionada (Python, Markdown, JSON, TOML, SQL, TXT e evidências), em **todas as linhas adicionadas em todos os commits** e nos 28 logs de servidor desta sessão.

Padrões procurados:
- `sb_secret_`, JWT (com verificação do `role`) e `SUPABASE_SERVICE_ROLE_KEY=…`;
- URL de banco com senha e URL com usuário e senha;
- tokens da Meta (`EAA…`) e do Instagram (`IGQV…`, `IGAA…`);
- chaves privadas, tokens do GitHub;
- atribuições de senha, token ou secret.

| Resultado | Detalhe |
|---|---|
| Credencial real exposta | **Nenhuma**, na árvore, no histórico e nos logs |
| Atribuições de senha encontradas | Só valores **sintéticos de teste** (`senha-…-teste`, `synthetic-…`), no código de teste e em 2 saídas antigas do pytest |
| `.env` e `secrets.toml` | Nunca versionados (`.gitignore`). O `.env` local tem 3 variáveis sensíveis, incluindo a URL do banco usada só para migrações, e fica só no computador da equipe |
| Menções a `service_role` | Só avisos para **não** usá-la |
| Chave publishable | Não é tratada como vazamento por si só. **Não aparece** na página nem nas respostas da vitrine (teste 8, com uma chave-canário, com o banco no ar e fora do ar) |
| Histórico anterior | Na etapa de configuração, a senha do banco foi colada no chat e **já foi trocada** (registrado na revisão de QA de 07/11). Não aparece no Git |

**Procedimento se uma credencial vazar no futuro:**
1. Revogar ou rotacionar no provedor (Supabase → Settings → API ou Database → Reset password).
2. Atualizar os Secrets do Streamlit Cloud.
3. Procurar no histórico com o script de auditoria.
4. Se estiver no Git, reescrever o histórico e avisar quem tem cópias. A rotação é obrigatória mesmo assim.

## 5. Banco e Storage (produção, somente leitura: `auditoria_banco_producao*.txt`)

| Verificação | Resultado |
|---|---|
| RLS | ✅ Ativo nas 11 tabelas do schema `public` e em `storage.objects` |
| Permissões do visitante (`anon`), **depois da 011** | ✅ Exatamente: SELECT em `confeitarias`, `produtos` e `product_images`. Nenhuma tabela privada |
| Funções que o visitante executa | ✅ Exatamente `criar_lead`, `criar_pedido` (validação + limite de envios + retorno mínimo) e os auxiliares `is_store_admin` e `storage_folder_admin` (devolvem só verdadeiro ou falso) |
| Funções administrativas | ✅ `cadastrar_admin`, `registrar_historico_pedido` e `verificar_limite_envios`: nem visitante nem usuário logado executam |
| Usuário logado **sem perfil** | ✅ Tem permissões de tabela (necessárias para a dona), mas o RLS barra tudo. Testado: ler leads, pedidos e histórico; alterar produtos, status e WhatsApp; apagar marketing |
| Colunas editáveis pela dona | ✅ Só as previstas (status, valor final, data e observações internas do pedido; campos do produto; nome e WhatsApp da loja) |
| Buckets | ✅ `product-images`: público para leitura, 5 MB, JPG, PNG e WEBP. `marketing`: **privado**, 5 MB, PNG |
| Políticas do Storage | ✅ Inserir, alterar, apagar e listar só para `authenticated` **e** dona da pasta da confeitaria. Nenhuma política para `anon`. Hoje há 0 arquivos |
| Visitante envia ou apaga arquivo | ✅ Recusado nos dois buckets (PostgreSQL real com o Storage emulado) |
| Pedidos e orçamentos | Funções controladas no banco (SECURITY DEFINER), não Edge Functions. Recomendação na seção 7 |

## 6. Integrações

| Integração | Situação |
|---|---|
| Instagram / Meta | **Ainda não implementada.** Não há token, conta conectada (0 linhas) nem worker. A estrutura está pronta: o token fica no **Supabase Vault** (extensão instalada) e a coluna `token_vault_id` **não é legível** por `anon` nem `authenticated` (testado em produção e no PostgreSQL). Nenhum módulo lê variáveis de token da Meta ou do Instagram (teste 11) |
| Worker de publicação | **Não existe ainda.** Requisitos para quando for criado: processo separado dos apps; segredos próprios no ambiente de execução (nunca nos Secrets dos apps Streamlit); leitura do token só pelo Vault com papel de serviço; renovação do token de longa duração antes de expirar (~60 dias, conforme a API da Meta); nenhum endpoint exposto ao navegador |
| WhatsApp | Só links `wa.me` (sem API e sem credenciais). Número da loja no banco (`confeitarias.whatsapp`), editável só pela dona |
| Supabase | Os apps usam **só** a chave publishable. A URL do banco com senha nunca vai para os apps |

## 7. Pendências que exigem intervenção manual

1. **Publicação em dois apps (E6-04).** No Streamlit Cloud:
   - trocar o Main file path do app atual para `doceflow/public_app.py`;
   - criar um segundo app com `doceflow/admin_app.py`;
   - preencher `PUBLIC_APP_URL` nos dois.

   Passo a passo em `docs/implantacao/README_IMPLANTACAO.md`, seção 3.
2. **Fechar o cadastro público (E6-06):** Supabase → Authentication → Sign In / Providers → Email → desativar "Allow new users to sign up". Em seguida, revisar a conta extra (2 usuários, 1 perfil).
3. **Limite por IP para orçamentos e pedidos (E6-07):** criar uma Edge Function na frente de `criar_lead` e `criar_pedido`, com limite por IP e captcha (ex.: Cloudflare Turnstile). Ela exige o Supabase CLI e credenciais de deploy da equipe. Enquanto isso, as funções atuais continuam validando tudo no servidor.
4. **Limitação da plataforma:** o selo "Hosted with Streamlit" e o botão "Manage app" (este só para quem administra o app) ficam **fora** do app, na página do Streamlit Cloud, e não podem ser removidos pelo código. Para uma vitrine sem nenhuma marca da plataforma, é preciso hospedagem própria ou um domínio com proxy.
5. **Decisão da equipe:** apagar `leads_antiga` (vazia, hoje sem acesso).

## 8. Testes desta etapa (os 12 obrigatórios)

| # | Teste | Onde |
|---|---|---|
| 1 | Cliente não acessa o painel | `test_1_6_admin_pages_without_login_go_to_login` (5 páginas); app público sem páginas admin (`test_10_*`); navegador |
| 2 | Cliente não consulta pedidos | `test_visitor_cannot_read_private_data_or_change_catalog` (orders, order_items, order_history); produção |
| 3 | Cliente não consulta leads | Idem (leads, admin_profiles); produção |
| 4 | Cliente não altera produtos | Idem (update e delete em produtos e fotos, update da loja) |
| 5 | Cliente não envia fotos | `test_visitor_cannot_upload_overwrite_or_delete_files` (2 buckets) |
| 6 | Proprietária não acessa sem login | `test_1_6_*`, `test_wrong_password_then_login_and_logout` |
| 7 | Sem autorização não opera | Sessão forjada, sessão **expirada**, sessão de **outro usuário**, usuário **sem perfil**; `test_logged_user_without_profile_has_no_write_power_in_practice` (10 operações) |
| 8 | Tokens fora da página e das respostas | `test_8_public_pages_never_show_keys_or_infrastructure`: chave-canário com o banco no ar e fora do ar, nas 3 páginas, inspecionando **tudo** o que o servidor envia ao navegador. Mais configuração de erro e CSS da barra |
| 9 | Chaves privilegiadas fora dos arquivos distribuídos | `test_9_no_privileged_keys_in_versioned_files` (`git ls-files`, 7 padrões) |
| 10 | App público sem operações admin | `test_10_*`: grafo de importações e páginas registradas |
| 11 | Worker não expõe credenciais | `test_11_no_code_reads_meta_or_instagram_tokens` e `test_instagram_token_column_is_not_readable_by_app_roles`. O worker ainda não existe (seção 6) |
| 12 | RLS bloqueia de fato | **Lista exata** de permissões e funções do visitante (falha se aparecer qualquer permissão nova), RLS em todas as tabelas e a 011 sem apagar dados |

Os testes de banco rodam num **PostgreSQL 16 real**, com as migrações 001 a 011 aplicadas duas vezes. Não basta uma busca textual: as permissões são consultadas no catálogo do banco e as operações são tentadas de verdade com cada papel.

## 9. Arquivos

**Novos:**
- `public_app.py`, `admin_app.py`
- `components/app_chrome.py`, `services/diagnostics.py`
- `database/migrations/011_endurecimento_permissoes.sql`
- `tests/test_etapa06_apps.py` (21), `tests/test_etapa06_postgres.py` (20)
- este relatório, capturas e auditorias do banco

**Alterados:**
- `.streamlit/config.toml`, `app.py` (legado), `config.py` (`PUBLIC_APP_URL`)
- `pages/public/catalog.py`, `pages/admin/login.py`, `pages/admin/marketing.py`, `services/auth_service.py`
- `.env.example`, `.streamlit/secrets.toml.example`
- `database/schema_reference.md`, `docs/implantacao/README_IMPLANTACAO.md`, `docs/implantacao/guia_rapido_confeiteira.md`
- 3 testes antigos (a mensagem do login local mudou)

## 10. Avaliação de prontidão para produção

- **Não há vulnerabilidade crítica nem alta em aberto.** A proteção dos dados está no banco (RLS + permissões mínimas, conferidas em produção), não nas telas.
- **Ainda não está pronto para produção.** Há 3 achados **médios** que dependem de ação manual:
  - **E6-04:** trocar a publicação para dois apps;
  - **E6-06:** fechar o cadastro público;
  - **E6-07:** limite por IP, recomendado antes de divulgar o link amplamente.
- Com E6-04 e E6-06 resolvidos, o DoceFlow fica **apto para o teste comercial controlado** (link enviado a clientes conhecidas). A E6-07 deve vir antes de uma divulgação aberta, por exemplo um anúncio no Instagram.
