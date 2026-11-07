# DoceFlow

MVP comercial para confeitarias artesanais: catálogo digital, solicitação de orçamentos (leads) e acompanhamento de oportunidades. O primeiro cliente é a Kika Cakes.

**Stack:** Python 3.12 · Streamlit · Supabase (PostgreSQL) · Pandas · WhatsApp via links `wa.me`

## Estrutura

```
doceflow/
<<<<<<< Updated upstream
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
=======
├── app.py                 # interface: página inicial / catálogo público
├── pages/admin.py         # interface: painel administrativo autenticado
├── services/catalog.py    # serviço: catálogo persistente com carga inicial de exemplos
├── services/quotes.py     # serviço: validação e registro de orçamentos
├── services/whatsapp.py   # serviço: links wa.me
├── database.py            # banco: Supabase (produção) ou SQLite (testes locais)
├── config.py              # configuração: st.secrets > variáveis de ambiente > padrão
├── .streamlit/config.toml # tema com a paleta da marca (sem segredos)
├── assets/images/         # logo e imagens
├── tests/                 # testes automatizados (pytest)
├── docs/evidencias/       # evidências de cada etapa
├── .env.example           # modelo de configuração (copie para .env)
└── requirements.txt
>>>>>>> Stashed changes
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
2. No **SQL Editor**, rode `supabase/migrations/001_schema_leads.sql` e depois `supabase/seed.sql`.
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
| Dona logada (`authenticated`) | leitura | lê e altera o `status` **somente** dos leads da sua confeitaria |
| `service_role` | não é usada pelo app | não é usada pelo app |

## Configuração

| Variável | Obrigatória | Descrição |
|---|---|---|
<<<<<<< Updated upstream
| `STORE_NAME` | não (padrão `Kika Cakes`) | nome exibido na vitrine |
| `STORE_SLUG` | não (padrão `kika-cakes`) | identificador da confeitaria no banco |
| `DB_BACKEND` | não (padrão `sqlite`) | `sqlite` para testes locais, `supabase` para uso real |
| `SQLITE_PATH` | não | caminho do banco local |
| `SUPABASE_URL` | se `supabase` | URL do projeto (Project Settings → API) |
| `SUPABASE_KEY` | se `supabase` | chave **anon/publishable**, nunca a `service_role` |
| `WHATSAPP_NUMBER` | só SQLite | número da confeitaria. No Supabase, use a coluna `confeitarias.whatsapp` |
| `ADMIN_PASSWORD` | só SQLite | senha do painel local |
=======
| `STORE_NAME` | não (padrão `Kika Cakes`) | nome da confeitaria exibido na vitrine |
| `DB_BACKEND` | não (padrão `sqlite`) | `sqlite` para testes locais, `supabase` reservado à integração futura |
| `SQLITE_PATH` | não | caminho do banco local |
| `SUPABASE_URL` | se `supabase` | URL do projeto (Project Settings → API) |
| `SUPABASE_KEY` | se `supabase` | chave **anon/publishable**, nunca a `service_role` |
| `WHATSAPP_NUMBER` | não | número da confeitaria, só dígitos com DDI e DDD |
| `ADMIN_PASSWORD` | para usar o admin | senha privada do painel administrativo |
>>>>>>> Stashed changes

Links com origem: `https://seu-app/?origem=instagram` ou `?utm_source=instagram`. Sem isso, o lead fica com a origem `site`.

## Testes

```bash
python -m pytest
```

Os testes de `tests/test_etapa03_postgres.py` sobem um PostgreSQL 16 embutido (`pgserver`), aplicam a migração e verificam o RLS. Eles são pulados se o `requirements-dev.txt` não estiver instalado.

## Segurança

- Nunca faça commit de `.env` ou `.streamlit/secrets.toml`.
<<<<<<< Updated upstream
- Use apenas a chave anon do Supabase. O RLS bloqueia a leitura pública dos leads.
- Os logs registram só o protocolo e o tipo de erro, nunca nome ou telefone.
- Para uso local em rede compartilhada, rode com `--server.address localhost`.
=======
- Use apenas a chave anon do Supabase, com **Row Level Security** ativa em todas as tabelas.
- O painel exige ADMIN_PASSWORD antes de consultar dados. Sessões são invalidadas ao trocar senha, banco ou STORE_ID. Cada instalação atende uma confeitaria definida pelo servidor.
- Veja os riscos completos em `docs/evidencias/etapa_01.md`.


## Painel administrativo (etapa 04)

Abra a página **admin** na navegação do Streamlit e informe `ADMIN_PASSWORD`.
Defina uma senha longa e exclusiva nos segredos do servidor. O botão Sair encerra a sessão.
`STORE_ID` é o identificador fixo da confeitaria (padrão `kika-cakes`); não o altere para renomear a loja.
Use uma implantação e uma senha por confeitaria. Todas as consultas e alterações incluem esse identificador.

O armazenamento desta etapa é SQLite (`DB_BACKEND=sqlite`), com arquivo em `SQLITE_PATH`.
Mantenha esse arquivo em volume persistente e faça backup. Reiniciar a aplicação preserva leads,
status e produtos; apagar o arquivo ou usar hospedagem com disco efêmero não preserva dados.
Supabase ainda não possui repositório de negócio nesta branch: esse modo é bloqueado,
sem fallback ou promessa de persistência remota.

A vitrine passa a registrar solicitações no banco, inclusive entre sessões de navegador.
Solicitações antigas que existiam apenas na memória não podem ser recuperadas após seu encerramento.
Os produtos de exemplo são inseridos na primeira utilização; preços e disponibilidade passam a ser
editáveis no painel, sem mudar o código. Novos produtos usam uma ilustração padrão.

O filtro de período considera a **data de registro**, incluindo os dois extremos. A data desejada
aparece separadamente. Indicadores usam os filtros ativos e o status atual; conversão é
vendas concluídas / total de leads do filtro × 100 (zero quando não há leads).
“Orçamentos enviados” é uma contagem do status registrado manualmente, não uma confirmação da API do WhatsApp.
O link apenas abre uma conversa com o contato; não envia nem verifica mensagens.
Marcar Venda concluída exige selecionar o status, confirmar a venda e salvar.
>>>>>>> Stashed changes
