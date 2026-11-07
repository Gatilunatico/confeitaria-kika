# Etapa 01: diagnóstico e base do projeto

**Data:** 2026-11-07 · **Branch:** `dev` · **Commit base:** `39a2dfc`

## 1. Diagnóstico inicial

| Item | Estado encontrado |
|---|---|
| `app.py`, `database.py`, `pages/admin.py`, `services/whatsapp.py` | vazios (0 bytes) |
| `requirements.txt` | vazio |
| `.gitignore` | existia (Python, venv, `.env`, `secrets.toml`, `*.db`) |
| `.env.example`, README, testes | ausentes |
| Ambiente | `.venv` com Python 3.12.8, só pip e setuptools |

Não havia código funcional para preservar. Por isso, todos os módulos foram criados do zero, com o mínimo para a aplicação executar.

### Funcionalidades

| Funcionalidade | Situação após a etapa 01 |
|---|---|
| Configuração por `.env` / `st.secrets` | **implementada** |
| Conexão Supabase (cliente + checagem) | **implementada**, mas sem credenciais reais (não testada contra o Supabase) |
| SQLite para testes locais | **implementado** |
| Link de WhatsApp (`wa.me`) | **implementado** |
| Painel admin com senha provisória | **implementado** (provisório) |
| Catálogo de produtos | **ausente** |
| Formulário de solicitação de orçamento | **ausente** |
| Acompanhamento de oportunidades (funil) | **ausente** |
| Schema das tabelas no Supabase + RLS | **ausente** |
| Autenticação real do admin | **ausente** |
| Consentimento LGPD no formulário | **ausente** |

## 2. Organização das responsabilidades

| Camada | Arquivo |
|---|---|
| Interface | `app.py`, `pages/admin.py`, `.streamlit/config.toml` (tema da marca) |
| Serviços | `services/whatsapp.py` |
| Banco de dados | `database.py` |
| Configuração | `config.py`, `.env.example` |

## 3. Arquivos alterados

**Criados:** `config.py`, `.env.example`, `.streamlit/config.toml`, `README.md`, `pytest.ini`, `tests/test_etapa01.py`, `assets/images/logo-kika-cakes.png` (copiado de `branding/`), `docs/evidencias/etapa_01.md`

**Preenchidos (antes vazios):** `app.py`, `database.py`, `pages/admin.py`, `services/whatsapp.py`, `requirements.txt`

**Alterados:** `.gitignore` (passa a ignorar `data/` e `.pytest_cache/`)

**Removido:** `assets/images/.gitkeep`, que deixou de ser necessário porque a pasta agora tem o logo

**Fora do doceflow:** `.vscode/settings.json` na raiz do repositório, criado na configuração do Python e ainda não commitado.

## 4. Comandos executados

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m streamlit run app.py --server.headless true --server.port 8599
curl http://localhost:8599/_stcore/health
curl http://localhost:8599/
curl http://localhost:8599/admin
```

## 5. Resultados

**Dependências instaladas:** streamlit 1.67.0, pandas 2.3.3, supabase 2.34.1, python-dotenv 1.2.4, pytest 8.4.2

**Testes:** `8 passed in 6.75s`
- normalização de telefone e montagem do link `wa.me` com a mensagem codificada
- rejeição de telefone inválido
- conexão com o SQLite
- Supabase sem credenciais falha de forma segura, com mensagem sem segredos
- `app.py` renderiza sem exceção (Streamlit AppTest)
- admin bloqueado quando `ADMIN_PASSWORD` não está definido
- login do admin rejeita a senha errada e aceita a correta

**Servidor local:** `/_stcore/health` → `ok` · `/` → 200 · `/admin` → 200

## 6. Riscos de segurança e dados pessoais

| # | Risco | Severidade | Situação / mitigação |
|---|---|---|---|
| 1 | Painel admin com senha única compartilhada, sem usuários, sem bloqueio de tentativas | **Alta** | Provisório. Substituir por Supabase Auth antes de receber dados reais |
| 2 | Uso da chave `service_role` do Supabase daria acesso total ao banco | **Alta** | `.env.example` e README orientam usar só a chave anon, com RLS |
| 3 | Tabelas sem Row Level Security permitiriam que qualquer pessoa com a chave anon lesse os orçamentos | **Alta** | Pendente: criar as políticas RLS junto com o schema |
| 4 | Dados pessoais de clientes (nome, telefone, endereço, data do evento), sujeitos à LGPD | **Média** | Pendente: aviso de privacidade e consentimento no formulário, coletar o mínimo, definir prazo de retenção |
| 5 | Mensagem do `wa.me` vai na URL e fica no histórico do navegador | **Baixa** | Documentado no código: não colocar dados sensíveis na mensagem |
| 6 | Streamlit escuta em todas as interfaces da rede (apareceu "Network URL" e "External URL" no log) | **Média** em rede compartilhada | Para uso local, rodar com `--server.address localhost` |
| 7 | Vazamento de `.env` / `secrets.toml` no Git | **Alta** | Os dois estão no `.gitignore`. `showErrorDetails = false` evita traceback na tela |

## 7. Pendências e erros

- **Nenhum erro pendente** nos testes nem na execução local.
- **Não testado:** a conexão real com o Supabase, porque não há credenciais. Isso depende de um projeto Supabase criado pela equipe.
- **Próximas etapas sugeridas:** schema e RLS no Supabase, catálogo de produtos, formulário de orçamento, painel de oportunidades e autenticação do admin.
