# DoceFlow

MVP comercial para confeitarias artesanais: catálogo digital, solicitação de orçamentos e acompanhamento de oportunidades. O primeiro cliente é a Kika Cakes.

**Stack:** Python 3.12 · Streamlit · Supabase (PostgreSQL) · Pandas · WhatsApp via links `wa.me`

## Estrutura

```
doceflow/
├── app.py                 # interface: página inicial / catálogo público
├── pages/admin.py         # interface: painel administrativo (senha provisória)
├── services/whatsapp.py   # serviço: links wa.me
├── database.py            # banco: Supabase (produção) ou SQLite (testes locais)
├── config.py              # configuração: st.secrets > variáveis de ambiente > padrão
├── .streamlit/config.toml # tema com a paleta da marca (sem segredos)
├── assets/images/         # logo e imagens
├── tests/                 # testes automatizados (pytest)
├── docs/evidencias/       # evidências de cada etapa
├── .env.example           # modelo de configuração (copie para .env)
└── requirements.txt
```

## Como executar localmente (Windows)

Pré-requisito: Python 3.12.

```bash
cd doceflow
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

O app abre em http://localhost:8501. Sem nenhuma configuração, ele usa o SQLite local (`data/doceflow_dev.db`).

No macOS ou Linux, use `python3.12 -m venv .venv`, depois `source .venv/bin/activate` e `cp .env.example .env`.

## Configuração

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DB_BACKEND` | não (padrão `sqlite`) | `sqlite` para testes locais, `supabase` para uso real |
| `SQLITE_PATH` | não | caminho do banco local |
| `SUPABASE_URL` | se `supabase` | URL do projeto (Project Settings → API) |
| `SUPABASE_KEY` | se `supabase` | chave **anon/publishable**, nunca a `service_role` |
| `WHATSAPP_NUMBER` | não | número da confeitaria, só dígitos com DDI e DDD |
| `ADMIN_PASSWORD` | para usar o admin | senha provisória do painel |

As variáveis podem ficar no `.env` (uso local) ou em `.streamlit/secrets.toml` / nos Secrets do Streamlit Cloud (deploy). Os dois arquivos estão no `.gitignore`.

## Testes

```bash
python -m pytest
```

## Segurança

- Nunca faça commit de `.env` ou `.streamlit/secrets.toml`.
- Use apenas a chave anon do Supabase, com **Row Level Security** ativa em todas as tabelas.
- O painel admin usa senha provisória. É preciso implementar autenticação real antes de receber dados de clientes reais.
- Veja os riscos completos em `docs/evidencias/etapa_01.md`.
