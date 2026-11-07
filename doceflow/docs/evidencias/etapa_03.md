# Etapa 03: persistência de leads e integração com WhatsApp

**Data:** 2026-11-07 · **Branch:** `dev` · **Commit base:** `a0aa5dc`

## 1. Resumo

Cada solicitação válida agora vira um **lead gravado no banco** (status `Novo`, com origem e protocolo) **antes** de o link do WhatsApp aparecer. A mensagem do WhatsApp é montada a partir do registro gravado. Repetir o envio não duplica o lead. Uma falha no banco nunca mostra sucesso. Os leads não são acessíveis publicamente.

## 2. Banco de dados

### Tabelas

As três tabelas existem no Supabase/PostgreSQL (`supabase/migrations/001_schema_leads.sql`) e no SQLite local, com o mesmo modelo:

| Tabela | Chave | Chaves estrangeiras | Destaques |
|---|---|---|---|
| `confeitarias` | `id uuid` | `owner_user_id → auth.users` | `slug` único, `whatsapp`, `ativo` |
| `produtos` | `id uuid` | `confeitaria_id → confeitarias` | `unique(confeitaria_id, slug)`, tipo de preço, `qtd_min`/`qtd_max` |
| `leads` | `id uuid` + `protocolo` único | `confeitaria_id`, `produto_id` | `status` com padrão **`Novo`**, `origem`, `consentimento_em`, `unique(confeitaria_id, fingerprint)` |

As três têm `created_at` e `updated_at` (atualizado por trigger) e `CHECK` nos campos: telefone `^55\d{10,11}$`, tamanhos de texto, modalidade, status e quantidade maior que zero.

### Requisitos

| Requisito | Implementação |
|---|---|
| Status inicial "Novo" | `default 'Novo'` na coluna e verificado nos testes |
| Origem da solicitação | `?origem=` ou `?utm_source=` na URL, normalizado (`a-z0-9_-`, até 40 caracteres). Sem parâmetro, fica `site` |
| Tratamento de erros | `LeadValidationError`: a mensagem amigável vai para a tela. `LeadPersistenceError` e qualquer outra exceção: mensagem genérica, sem detalhes técnicos |
| Validação | Feita em três camadas: formulário (UX), repositório e banco (`CHECK`s + função `criar_lead`) |
| Operações seguras | SQLite só com parâmetros `?`. Supabase só via SDK (`table().select()` e `rpc()`), sem SQL montado com texto |
| Acesso por confeitaria | RLS: a dona só vê e altera os leads da confeitaria em que é `owner_user_id`. No SQLite, toda consulta filtra pelo `STORE_SLUG` |

### Modelo de acesso (RLS)

- **Visitante (`anon`):** lê confeitarias ativas e produtos. Não tem `SELECT`, `INSERT`, `UPDATE` nem `DELETE` em `leads`. Cria leads **apenas** pela função `criar_lead` (`SECURITY DEFINER`), que valida tudo, é idempotente e devolve só o próprio pedido.
- **Dona (`authenticated`):** `SELECT` nos leads da sua confeitaria e `UPDATE` somente da coluna `status`.
- **`service_role`:** nunca é usada pelo app.

## 3. WhatsApp

| Requisito | Implementação |
|---|---|
| Mensagem com nome, produto, quantidade, data e observações | `build_lead_message(lead)` |
| Identificador do pedido | linha `Pedido: DF-AAMMDD-XXXXXX` |
| `https://wa.me/` com codificação | `quote(message, safe='')`: `&`, `#`, `?`, quebras de linha e emojis são codificados |
| Salvar antes de redirecionar | O botão "Abrir conversa no WhatsApp" só existe na tela de confirmação, que só aparece depois de `create_lead` retornar com sucesso |
| Não afirmar envio | O texto diz que o botão "abre o WhatsApp com a mensagem já escrita" e que a confeitaria "só recebe depois que você tocar em enviar". Há um teste que garante que "foi enviada" não aparece |
| Sem duplicar | Repetir a ação reaproveita o lead (mesmo protocolo) e mostra "Este mesmo pedido já estava registrado" |

## 4. Segurança e privacidade

- **Credenciais administrativas:** nenhuma. A `.env.example` e o README proíbem a `service_role`. No modo Supabase, o painel usa o login do Supabase Auth, e no modo SQLite usa uma senha local, agora dentro de `st.form`.
- **Consulta pública de leads:** bloqueada pelo RLS e testada no PostgreSQL real. A vitrine não exibe dados de outros leads.
- **Logs:** registram só `protocolo` e o tipo de erro. No teste manual, o log do servidor teve 0 ocorrências do nome ou do telefone.
- **Privacidade:** a página `pages/privacidade.py` traz o aviso completo. O formulário tem a seção "Como usamos seus dados", o consentimento é obrigatório e a data do consentimento é registrada (`consentimento_em`). Coleta mínima: sem endereço, CPF ou e-mail.
- **Imagens vindas do banco:** `image_path` não aceita caminhos fora de `assets/images/produtos`.

## 5. Arquivos alterados

**Criados:** `supabase/migrations/001_schema_leads.sql`, `supabase/seed.sql`, `pages/privacidade.py`, `requirements-dev.txt`, `tests/test_etapa03.py`, `tests/test_etapa03_postgres.py`, `tests/sql/supabase_shim.sql`, `docs/evidencias/etapa_03.md`, `docs/evidencias/img/etapa03_admin_lead_apos_reinicio.jpg`

**Renomeado:** `services/quotes.py` → `services/leads.py` (validação + modelos `LeadRequest`/`Lead`)

**Alterados:**
- `database.py`: repositórios SQLite e Supabase, `get_repository`
- `app.py`: catálogo lido do banco, gravação antes do link, tratamento de falhas, origem e privacidade
- `pages/admin.py`: lista os leads. No modo Supabase usa o Supabase Auth, no modo SQLite a senha em formulário
- `services/catalog.py`: `Product` com `id`/`slug` e seed
- `services/whatsapp.py`: mensagem e link a partir do lead
- `config.py` e `.env.example`: `STORE_SLUG`
- `requirements.txt`: só as dependências da aplicação
- `README.md`
- `tests/test_etapa02.py`: adaptado à nova API

## 6. Comandos executados

```bash
pip install pgserver "psycopg[binary]"          # PostgreSQL 16 embutido para testes
python -m pytest -q
streamlit run app.py --server.address localhost  # com SQLITE_PATH isolado, WHATSAPP_NUMBER e ADMIN_PASSWORD de teste
# parar o servidor e subir de novo no mesmo SQLITE_PATH
```

## 7. Resultados

### Testes automatizados: `92 passed`

| Arquivo | Testes | Cobre |
|---|---|---|
| `test_etapa01.py` | 8 | configuração, conexão, WhatsApp básico, admin |
| `test_etapa02.py` | 35 | vitrine, validações, fluxo do formulário |
| `test_etapa03.py` | 30 | persistência, status Novo, origem, reinício, duplicidade, validação no servidor, isolamento por confeitaria, injeção de SQL, logs sem dados pessoais, mensagem igual ao registro, codificação da URL, repositório Supabase (cliente falso: RPC parametrizado e tradução de erros), falha no banco sem sucesso, catálogo indisponível, admin protegido, aviso de privacidade |
| `test_etapa03_postgres.py` | 19 | **PostgreSQL 16 real**: migração idempotente, `criar_lead` como `anon`, idempotência, 9 validações no servidor, origem inválida vira `site`, anon sem SELECT/INSERT/UPDATE/DELETE em `leads`, anon lê o catálogo, dona lê e muda só o `status`, dona de outra confeitaria não vê nem altera nada |

### Fluxo manual no navegador (celular 375 × 812)

1. Abri `/?origem=instagram`, cliquei em Brigadeiros gourmet e preenchi o formulário.
2. Ao enviar, o diálogo fechou. **Depois** disso surgiu um único link `wa.me`:
   `https://wa.me/5511912345678?text=Ol%C3%A1%2C%20Kika%20Cakes%21...%0APedido%3A%20DF-261107-821D32%0ANome%3A%20Carla%20Teste%0AProduto%3A%20Brigadeiros%20gourmet%0AQuantidade%3A%201%20%28cento%29%0AData%20desejada%3A%2015%2F12%2F2026%20%28retirada%29%0AObserva%C3%A7%C3%B5es%3A%20-`
3. No SQLite, o registro gravado foi `DF-261107-821D32`, `Novo`, `instagram`, Carla Teste, Brigadeiros gourmet, 1 cento, 2026-12-15, Retirada, sem observações. **Bate com a mensagem.**
4. Log do servidor: `Lead criado protocolo=DF-261107-821D32`. Nome e telefone aparecem 0 vezes.
5. **Reiniciei o servidor** com o mesmo arquivo de banco. Em `/admin`, depois do login, apareceu **Leads (1)** com o protocolo `DF-261107-821D32` (captura: `img/etapa03_admin_lead_apos_reinicio.jpg`).

Observação: nesse teste, os meus cliques automatizados em "Entrega" e em observações não registraram, por isso o lead ficou com Retirada e sem observações. O conteúdo com `&` e `#` está coberto nos testes automatizados de codificação.

## 8. Problemas encontrados e corrigidos

| Problema | Correção |
|---|---|
| O PostgreSQL embutido não tem a base de fusos horários (`America/Sao_Paulo`) | A função usa `UTC - 3 horas` (Brasília não tem horário de verão desde 2019). Funciona no Supabase e em qualquer Postgres |
| No login local, clicar em "Entrar" logo depois de digitar podia enviar o campo antes de ele ser confirmado ("Senha incorreta") | O login local agora é um `st.form` |
| `st.page_link("app.py")` falhava quando a página de privacidade era aberta direto | Troquei por um link Markdown para `/` |

## 9. Pendências

| Item | Situação |
|---|---|
| **Supabase real** | A migração e o RLS foram validados num PostgreSQL 16 local, emulando `auth.uid()` e os papéis `anon`/`authenticated`. **Ainda não foram executados num projeto Supabase de verdade**, porque não há credenciais. Falta criar o projeto, rodar os dois SQL, criar a usuária e preencher o `.env` |
| **Login do admin com Supabase Auth** | O código está pronto, mas não foi testado ao vivo (depende do item acima) |
| **WhatsApp oficial da Kika** | Ainda não foi informado. No Supabase, vai na coluna `confeitarias.whatsapp` |
| **Limite de requisições** | A função `criar_lead` é pública por natureza (anon). Contra spam, avaliar um captcha ou limite por IP numa próxima etapa |
| **Retenção de dados** | O aviso de privacidade fala em "tempo necessário". O prazo concreto precisa ser definido pela confeitaria |
| **Funil / status no admin** | O admin lista os leads, mas ainda não muda o status. O banco já está pronto para isso (UPDATE só do `status`) |
