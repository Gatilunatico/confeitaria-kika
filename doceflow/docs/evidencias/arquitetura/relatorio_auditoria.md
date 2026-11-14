# Etapa 1: auditoria e reorganização da arquitetura

**Data:** 2026-11-14 · **Branch:** `dev` · **Commit base:** `79989dc`

## 1. Auditoria do estado anterior

### Inventário

- **Raiz:** 37 arquivos de código e configuração.
- **Interface:** `app.py` (vitrine, 302 linhas), `pages/admin.py` (453 linhas, misturando login, leads, indicadores e produtos), `pages/marketing.py` e `pages/privacidade.py`.
- **Regras e dados:** `database.py` (567 linhas, repositórios SQLite e Supabase) e `supabase_client.py` na raiz, e 11 módulos em `services/`, entre eles regras de negócio, marketing e marca.
- **Banco:** `supabase/migrations` 001 a 004 e `seed.sql`. Templates JSON soltos na raiz em `templates/`.
- **Assets:** `assets/logos`, `assets/images/produtos` e `assets/fonts`.

### Funcionalidades e estado

| Funcionalidade | Estado encontrado |
|---|---|
| Catálogo público (27 produtos reais) | ✅ funcionando |
| Solicitação de orçamento + validação + LGPD | ✅ funcionando |
| WhatsApp (cliente → confeitaria, painel → cliente) | ✅ funcionando |
| Dashboard comercial (indicadores, período) | ✅ funcionando, mas misturado com a lista de leads |
| Gestão de leads (filtros, status, venda com confirmação) | ✅ funcionando |
| Gestão de produtos (cadastro e edição) | ✅ funcionando, escolhendo imagem só entre os arquivos do repositório |
| Estúdio de Marketing (artes, legendas, histórico) | ✅ funcionando localmente. ⚠️ No Supabase, o histórico depende da migração 004, **não aplicada** |
| **"Automação de posts"** | ❌ **não existe**. Há geração de arte e legenda, mas **nenhum agendamento ou publicação automática**. Isso nunca foi implementado, porque a publicação pela API da Meta ficou fora do escopo |
| Upload de fotos, gestão de pedidos | ❌ não existem (são novas) |

### Dependências e integrações

- **Supabase:** Auth (login da dona), PostgREST (tabelas e RPC `criar_lead`) e Storage (previsto na 004, ainda não criado).
- **WhatsApp:** links `wa.me`, sem API.
- **Bibliotecas:** Streamlit, Pandas, Pillow, supabase-py e python-dotenv. Para testes: pytest, pgserver e psycopg.
- **Tabelas:** ver `database/schema_reference.md` (diagnóstico feito no banco real, só com leitura).

## 2. Problemas encontrados

| # | Problema | Gravidade | Situação |
|---|---|---|---|
| 1 | `pages/` plano: público e admin misturados. O Streamlit listaria tudo no mesmo menu (escondido por configuração) | Média | ✅ Resolvido: `pages/public` + `pages/admin` com `st.navigation`. O menu só aparece após o login |
| 2 | `pages/admin.py` com 453 linhas e 4 responsabilidades | Média | ✅ Dividido em login, painel, orçamentos e produtos, mais componentes |
| 3 | Comunicação com o banco espalhada na raiz (`database.py`, `supabase_client.py`) | Baixa | ✅ Movida para `services/repository.py` e `services/supabase_client.py`, que é o único ponto de criação do cliente |
| 4 | Regra de login duplicada entre o painel e o marketing | Média | ✅ Centralizada em `services/auth_service.py` (`require_admin`) |
| 5 | Migração 004 (marketing) não aplicada no Supabase | **Alta** para o marketing em produção | ⏳ Pendente: precisa rodar no SQL Editor |
| 6 | Tabela `leads_antiga` sobrando no Supabase | Baixa | ⏳ Pendente: não apaguei (regra de não fazer migrações destrutivas) |
| 7 | 2 usuários no Auth, e o painel deveria ter só a dona | Média | ⏳ Conferir em Authentication → Users se o segundo usuário é esperado |
| 8 | "Automação de posts" citada como existente, mas não implementada | Informativo | Registrado (seção 1) |
| 9 | Fontes da marca ausentes em `assets/fonts` | Baixa | ⏳ Pendente (os posts usam fontes do sistema) |
| 10 | Testes organizados por etapa, não por domínio | Baixa | Mantidos. Renomear não traria ganho funcional |
| 11 | O bloqueio de DLL do Windows (pyarrow/psycopg) de 12/11 | Ambiente | Hoje não ocorreu. A alternativa de tabela HTML foi mantida |

## 3. O que foi modificado

### Estrutura final

```
doceflow/
├── app.py                      # navegação: público sempre, admin só com sessão
├── config.py
├── pages/public/   catalog.py, privacy.py
├── pages/admin/    login.py, dashboard.py, quotes.py, products.py, marketing.py
├── components/     product_card.py, quote_dialog.py, product_form.py,
│                   dashboard_metrics.py, data_table.py, navigation.py
├── services/       supabase_client.py, repository.py, auth_service.py, product_service.py,
│                   catalog_data.py, quote_service.py, dashboard_service.py, whatsapp_service.py
├── marketing/      post_generator.py, caption_generator.py, store.py, brand.py, templates/*.json
├── database/       migrations/001–004, seed.sql, schema_reference.md
├── assets/         logo/, fonts/, default_images/
└── tests/
```

### Mapa da movimentação (todas com `git mv`, mantendo o histórico)

| Antes | Depois |
|---|---|
| `app.py` (vitrine) | `pages/public/catalog.py` + `components/product_card.py` + `components/quote_dialog.py` |
| (novo) | `app.py` com a navegação |
| `pages/privacidade.py` | `pages/public/privacy.py` |
| `pages/admin.py` | `pages/admin/login.py`, `dashboard.py`, `quotes.py` e `products.py` + `components/dashboard_metrics.py`, `product_form.py`, `data_table.py` e `navigation.py` + `services/auth_service.py` |
| `pages/marketing.py` | `pages/admin/marketing.py` |
| `database.py` | `services/repository.py` |
| `supabase_client.py` | `services/supabase_client.py` |
| `services/auth.py` | `services/auth_service.py` (com a lógica de login centralizada) |
| `services/catalog.py` / `catalogo_kika.py` | `services/product_service.py` / `services/catalog_data.py` |
| `services/leads.py` / `whatsapp.py` / `dashboard.py` | `services/quote_service.py` / `whatsapp_service.py` / `dashboard_service.py` |
| `services/post_generator.py`, `caption_generator.py`, `marketing_store.py`, `brand.py` | `marketing/post_generator.py`, `caption_generator.py`, `store.py`, `brand.py` |
| `templates/*.json` | `marketing/templates/*.json` |
| `supabase/migrations/*`, `supabase/seed.sql` | `database/migrations/*`, `database/seed.sql` |
| `assets/logos/`, `assets/images/produtos/` | `assets/logo/`, `assets/default_images/` |

**Arquivos novos com conteúdo:** `app.py` (navegação), os 6 componentes, `pages/admin/login.py`, `dashboard.py`, `quotes.py` e `products.py`, `database/schema_reference.md` e este relatório.

**Não criados de propósito**, porque seriam arquivos vazios para funções que ainda não existem: `product_details.py`, `request_quote.py`, `order_confirmation.py`, `orders.py`, `settings.py`, `image_uploader.py`, `order_form.py`, `status_badge.py`, `image_service.py`, `order_service.py`, `instagram_service.py`, `scheduler.py`, `instagram_publisher.py`, `templates.py` e as migrações 002 a 005 da especificação. O pedido de orçamento continua como **diálogo** dentro do catálogo, e não como página separada, para não piorar a experiência que já foi validada no celular.

### Outros ajustes

- **URLs mantidas:** `/` (catálogo), `/privacidade`, `/admin` (login) e `/marketing`. As **novas** são `/painel`, `/orcamentos` e `/produtos`.
- **Menu:** `.streamlit/config.toml` não esconde mais o menu por configuração. O `app.py` decide: escondido para visitantes e visível depois do login.
- **Dependências:** `requirements.txt` agora exige Streamlit 1.50 ou mais novo (necessário para `st.navigation` com páginas ocultas).
- **README:** atualizado com a nova estrutura e as URLs.
- **Testes:** atualizados para a navegação real. Ganharam auxiliares em `tests/conftest.py` (`open_page` e `admin_login`) e um teste novo para o painel.
- **Identidade visual:** mantida. Mesmo tema, mesmas cores, mesmo logo e mesmo CSS da vitrine.

## 4. Funcionalidades preservadas (com teste de regressão)

Catálogo público, filtro por categoria, card de produto com foto, solicitação de orçamento com validação (telefone, data, quantidade mínima, consentimento), proteção contra duplicidade, confirmação no diálogo, link do WhatsApp gravado antes de liberar, falha no banco sem falso sucesso, aviso de privacidade, login (local e Supabase), bloqueio após 5 tentativas, logout, painel com indicadores, gestão de orçamentos (filtros, status, venda com confirmação, WhatsApp da cliente), gestão de produtos (cadastro, edição, validação), Estúdio de Marketing (3 templates, Feed e Story, legendas em 3 tons, histórico) e as regras de acesso do banco (RLS testado num PostgreSQL real).

## 5. Validação da reorganização

- **pytest:** `234 passed`, sem nenhum teste pulado, inclusive os de PostgreSQL real e de tabela (hoje o Windows não bloqueou o pyarrow nem o psycopg).
- **Teste com o app completo (AppTest):**
  - Catálogo com 27 produtos.
  - Cada página admin sem login leva ao login.
  - O login leva ao painel.
  - Orçamentos, produtos e marketing abrem logados.
  - O login, já logado, leva ao painel.
  - "Sair" volta ao login e bloqueia de novo.
- **Navegador (`localhost:8502`, SQLite de teste):**
  - Visitante sem menu, com 27 cards.
  - `/marketing` sem login redireciona para `/admin`.
  - Depois do login, abre `/painel` com o menu (Catálogo, Aviso de privacidade, Painel, Orçamentos, Produtos, Estúdio de Marketing), com "Entrar" oculto.
  - Captura: `painel_apos_login_com_menu.jpg`.
- **Supabase:** só diagnóstico de leitura. Nenhuma migração foi executada e nenhum dado foi alterado.

## 6. Configurações necessárias

| Variável | Uso |
|---|---|
| `DB_BACKEND` | `supabase` em produção (padrão) e `sqlite` só em testes isolados |
| `SUPABASE_URL`, `SUPABASE_KEY` | URL da API e **chave publishable**. Nunca use a `service_role` nem a `secret` |
| `STORE_NAME`, `STORE_SLUG` | Kika Cakes / `kika-cakes` |
| `WHATSAPP_NUMBER` | só no SQLite. No Supabase vale a coluna `confeitarias.whatsapp` |
| `ADMIN_PASSWORD`, `SQLITE_PATH` | só para testes locais |
| `SUPABASE_DB_URL` | **só local**, para migrações e diagnóstico. Nunca vai para o app nem para o Streamlit Cloud |

**No Streamlit Cloud, o arquivo principal continua sendo `doceflow/app.py`.** Não é preciso mudar nada no deploy.

## 7. O que ainda precisa ser implementado (próximas etapas)

1. **Aplicar `004_marketing.sql`** no Supabase, para o histórico do Estúdio funcionar em produção.
2. **Upload de fotos de produtos:** bucket de Storage, coluna em `produtos` e componente de upload no cadastro.
3. **Gestão de pedidos:** tabela `pedidos` ligada ao lead, página `pages/admin/orders.py` e serviço `order_service.py`.
4. **Integração com Instagram, agendamento e publicação:** não existem hoje. Dependem da API da Meta e de credenciais guardadas com segurança.
5. **Limpezas no Supabase,** com a sua aprovação: `leads_antiga` e o segundo usuário do Auth, se não for esperado.
6. **Fontes da marca** em `assets/fonts`.
