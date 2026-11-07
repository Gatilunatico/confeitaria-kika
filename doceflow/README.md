# DoceFlow

MVP comercial para confeitarias artesanais: catálogo digital, solicitação de orçamentos (leads) e acompanhamento de oportunidades. O primeiro cliente é a Kika Cakes.

**Stack:** Python 3.12 · Streamlit · Supabase (PostgreSQL) · Pandas · WhatsApp via links `wa.me`

## Estrutura

```
doceflow/
├── app.py                     # interface: vitrine pública (catálogo + orçamento)
├── pages/admin.py             # interface: painel com os leads (login)
├── pages/privacidade.py       # interface: aviso de privacidade (LGPD)
├── services/catalog.py        # modelo de produto + dados de exemplo (seed)
├── services/leads.py          # validação e modelos de lead
├── services/whatsapp.py       # mensagem e link wa.me
├── database.py                # repositórios Supabase (produção) e SQLite (testes locais)
├── config.py                  # configuração: st.secrets > variáveis de ambiente > padrão
├── supabase/migrations/       # schema, RLS e função criar_lead
├── supabase/seed.sql          # confeitaria e produtos iniciais
├── .streamlit/config.toml     # tema com a paleta da marca (sem segredos)
├── assets/images/             # logo e ilustrações dos produtos
├── tests/                     # pytest (inclui testes num PostgreSQL real)
├── docs/evidencias/           # evidências de cada etapa
├── .env.example               # modelo de configuração (copie para .env)
├── requirements.txt           # dependências da aplicação
└── requirements-dev.txt       # + dependências de teste
```

## Como executar localmente (Windows)

Pré-requisito: Python 3.12.

```bash
cd doceflow
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
streamlit run app.py --server.address localhost
```

O app abre em http://localhost:8501. Sem nenhuma configuração, ele usa o SQLite local (`data/doceflow_dev.db`), que é criado com a Kika Cakes e os produtos de exemplo. O painel fica em http://localhost:8501/admin e usa `ADMIN_PASSWORD` no modo SQLite.

No macOS ou Linux, use `python3.12 -m venv .venv`, depois `source .venv/bin/activate` e `cp .env.example .env`.

## Configurar o Supabase

1. Crie um projeto em supabase.com.
2. No **SQL Editor**, rode nesta ordem: `supabase/migrations/001_schema_leads.sql`, `supabase/migrations/002_painel_admin.sql` e `supabase/seed.sql`. Os três podem ser rodados de novo sem duplicar nada.
3. Em **Authentication → Users**, crie o usuário da dona da confeitaria.
4. Vincule esse usuário e o WhatsApp oficial à confeitaria (SQL Editor):
   ```sql
   update public.confeitarias
      set owner_user_id = '<uuid do usuário>', whatsapp = '55DDDNUMERO'
    where slug = 'kika-cakes';
   ```
5. No `.env` (ou nos Secrets do Streamlit Cloud): `DB_BACKEND=supabase`, `SUPABASE_URL` e `SUPABASE_KEY` com a chave **anon/publishable**.

Com isso, o painel admin passa a pedir o e-mail e a senha do usuário criado no passo 3.

### Modelo de acesso (RLS)

| Quem | confeitarias / produtos | leads |
|---|---|---|
| Visitante (`anon`) | leitura das confeitarias ativas | **sem acesso**. Só cria leads pela função `criar_lead`, que valida os dados e devolve apenas o próprio pedido |
| Dona logada (`authenticated`) | leitura; cadastra e edita produtos **só da sua confeitaria** (sem mudar `slug` nem confeitaria) | lê e altera o `status` **somente** dos leads da sua confeitaria |
| `service_role` | não é usada pelo app | não é usada pelo app |

## Painel administrativo (`/admin`)

- **Login obrigatório.** No modo Supabase, entra a dona vinculada à confeitaria. No modo SQLite, entra quem tiver a `ADMIN_PASSWORD`. Depois de 5 tentativas erradas, o login fica bloqueado por 5 minutos.
- **Aba Leads:**
  - Indicadores do período: total, novos, orçamentos enviados, vendas concluídas e conversão.
  - Filtros por status e período.
  - Lista com os novos primeiro.
  - Atualização de status: Novo → Em atendimento → Orçamento enviado → Venda concluída / Perdido. A venda exige uma confirmação manual.
  - Botão para abrir a conversa no WhatsApp da cliente.
- **Aba Produtos:** cadastro e edição de nome, categoria, preço, tipo de preço, unidade, quantidades, imagem e disponibilidade, sem mexer no código.

## Configuração

| Variável | Obrigatória | Descrição |
|---|---|---|
| `STORE_NAME` | não (padrão `Kika Cakes`) | nome exibido na vitrine |
| `STORE_SLUG` | não (padrão `kika-cakes`) | identificador da confeitaria no banco |
| `DB_BACKEND` | não (padrão `sqlite`) | `sqlite` para testes locais, `supabase` para uso real |
| `SQLITE_PATH` | não | caminho do banco local |
| `SUPABASE_URL` | se `supabase` | URL do projeto (Project Settings → API) |
| `SUPABASE_KEY` | se `supabase` | chave **anon/publishable**, nunca a `service_role` |
| `WHATSAPP_NUMBER` | só SQLite | número da confeitaria. No Supabase, use a coluna `confeitarias.whatsapp` |
| `ADMIN_PASSWORD` | só SQLite | senha do painel local |

Links com origem: `https://seu-app/?origem=instagram` ou `?utm_source=instagram`. Sem isso, o lead fica com a origem `site`.

## Testes

```bash
python -m pytest
```

Os testes de `tests/test_etapa03_postgres.py` sobem um PostgreSQL 16 embutido (`pgserver`), aplicam a migração e verificam o RLS. Eles são pulados se o `requirements-dev.txt` não estiver instalado.

## Segurança

- Nunca faça commit de `.env` ou `.streamlit/secrets.toml`.
- Use apenas a chave anon do Supabase. O RLS bloqueia a leitura pública dos leads.
- Os logs registram só o protocolo e o tipo de erro, nunca nome ou telefone.
- Para uso local em rede compartilhada, rode com `--server.address localhost`.
