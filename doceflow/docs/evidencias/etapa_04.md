# Etapa 04: painel administrativo

**Data:** 2026-11-07 · **Branch:** `dev` · **Commit base:** `a94e33d`

## 1. O que foi implementado

| Requisito | Implementação |
|---|---|
| 1. Autenticação obrigatória | Nada do painel é renderizado antes do login. **Supabase:** e-mail e senha pelo Supabase Auth, e o usuário precisa ser `owner_user_id` de uma confeitaria ativa (senão aparece "não está vinculado"). **SQLite:** `ADMIN_PASSWORD`. Bloqueio de 5 min após 5 tentativas erradas. Botão "Sair" encerra a sessão |
| 2. Listagem de leads | Tabela com Status, Recebido em (horário de Brasília), Cliente, WhatsApp, Produto (com quantidade), Data desejada (com retirada ou entrega), Observações, Origem, Protocolo e Conversa. **Novos primeiro**, depois os mais recentes |
| 3. Filtros | Status (múltipla escolha) e período (7, 30, 90 dias, todo o período ou intervalo personalizado) pela data de registro |
| 4. Atualização de status | Seleção do lead e do novo status (Novo, Em atendimento, Orçamento enviado, Venda concluída, Perdido), mais "Salvar status". O status fica gravado no banco e `status_atualizado_em` registra quando mudou |
| 5. Botão do WhatsApp | "Abrir conversa no WhatsApp" do lead selecionado, mais a coluna "Conversa" na tabela. O `wa.me` vai para o número da **cliente**, com uma mensagem pronta citando o protocolo |
| 6. Produtos | Aba Produtos com a tabela de produtos, o formulário de edição (nome, categoria, descrição, tipo de preço, preço, unidade, quantidade mínima e máxima, ordem, imagem, disponibilidade) e "Cadastrar novo produto". Validação nos campos e no banco |
| 7. Indicadores | Total de leads, Leads novos, Orçamentos enviados, Vendas concluídas e Taxa de conversão (vendas ÷ total, com "—" quando não há leads). Calculados sobre o período escolhido |

### Regras de negócio

- **Venda só com confirmação manual.** "Venda concluída" exige marcar "Confirmo que a venda foi fechada com a cliente". Nenhum status muda sozinho: nem ao abrir o WhatsApp, nem com o passar do tempo.
- **Solicitação registrada ≠ mensagem enviada.** O indicador se chama "Total de leads", e a legenda explica que são solicitações registradas pela vitrine, não mensagens do WhatsApp. O botão do WhatsApp avisa que "não envia nada sozinho e não muda o status".
- **Sem acesso sem login.** Há um teste que garante a ausência de indicadores, tabelas e nomes de clientes antes do login e depois de "Sair".
- **Sem dados de outra confeitaria.**
  - No Supabase, o RLS filtra leads e produtos pela dona logada, e a escrita em produtos só vale para a própria confeitaria. A dona não consegue mudar `slug` nem `confeitaria_id`.
  - No SQLite, toda consulta e alteração filtra pela confeitaria configurada.
- **Sem decoração.** Não há gráficos. Só indicadores, tabela, filtros e ações.

## 2. Banco de dados: migração `002_painel_admin.sql`

- Troca o CHECK de status para o novo funil e converte os status antigos: `Em contato` → `Em atendimento`, `Fechado` → `Venda concluída`.
- Adiciona `leads.status_atualizado_em` e o trigger que preenche essa coluna quando o status muda.
- Permite à dona (`authenticated`) **INSERT** e **UPDATE** em `produtos`, só nas colunas editáveis e só na própria confeitaria (políticas `produtos_owner_insert` e `produtos_owner_update`).
- É idempotente: rodar duas vezes não causa erro.

O SQLite local migra sozinho um banco da etapa 03: a tabela `leads` é recriada com os novos status, sem perder dados.

## 3. Arquivos alterados

**Criados:** `services/dashboard.py`, `supabase/migrations/002_painel_admin.sql`, `tests/test_etapa04.py`, `tests/test_etapa04_postgres.py`, `docs/evidencias/etapa_04.md`, `docs/evidencias/img/etapa04_*.jpg`

**Alterados:**
- `pages/admin.py`: reescrito (login, leads, status, indicadores, produtos)
- `database.py`: atualização de status, cadastro e edição de produtos, `SupabaseRepository.for_owner`, migração do SQLite
- `services/leads.py`: constantes do funil
- `services/catalog.py`: `validate_product`, `slugify`, `available_images`
- `README.md`
- `tests/test_etapa01.py`: o login agora mostra o título do painel

## 4. Comandos executados

```bash
python -m pytest -q
# demonstração local com dados fictícios (SQLite isolado):
DB_BACKEND=sqlite SQLITE_PATH=<scratchpad>/demo_painel.db ADMIN_PASSWORD=<senha de teste> \
  streamlit run app.py --server.address localhost --server.port 8502
```

## 5. Resultados

### Testes automatizados: `143 passed`

| Arquivo | Testes | Cobre |
|---|---|---|
| `test_etapa04.py` | 38 | indicadores e conversão, "—" sem leads, venda só por status manual, filtros por status e período, data em horário de Brasília, validação de produto (9 casos de erro, duplicidade, sob consulta), status persistido após reinício, status inválido ou lead inexistente, **isolamento entre confeitarias** (leads e produtos), produto criado ou editado chega à vitrine, migração do SQLite antigo, Supabase sem confeitaria vinculada é negado, update filtrado pelo RLS não conta como sucesso, **painel sem login não mostra dados**, admin sem senha configurada, bloqueio após 5 tentativas, indicadores refletindo os dados, novos primeiro, aviso de leads novos, filtro de status, filtro de período, atualização de status pela tela e persistência, venda exige confirmação, botão do WhatsApp para a cliente sem dizer que enviou, edição de produto pela tela refletindo na vitrine, cadastro de produto, produto inválido não salva, logout esconde dados |
| `test_etapa04_postgres.py` | 13 | **PostgreSQL 16 real**: status antigos convertidos, dona aplica os 5 status, status antigo ou inválido é recusado, `status_atualizado_em` é preenchido, dona cria e edita produtos, dona não muda `slug` nem confeitaria, dona de outra confeitaria não escreve produtos nem altera leads, visitante não escreve produtos |
| etapas 01–03 | 92 | continuam passando |

### Validação manual (navegador, painel em http://localhost:8502/admin, dados fictícios)

Base de demonstração com 5 leads: 2 Novo, 1 Em atendimento, 1 Orçamento enviado e 1 Venda concluída.

- Antes do login, só aparece o campo de senha.
- Depois do login: **Total 5 · Novos 2 · Orçamentos enviados 1 · Vendas concluídas 1 · Conversão 20,0%**, que confere com a base.
- Aparece o aviso "Você tem 2 lead(s) novo(s) aguardando atendimento", e a tabela começa pelos leads **Novo**.
- A aba Produtos lista os 6 produtos com preço da vitrine e disponibilidade.
- Capturas: `img/etapa04_painel_leads_indicadores.jpg` e `img/etapa04_painel_produtos.jpg`.

## 6. Pendências

| Item | Situação |
|---|---|
| **Aplicar a 002 no Supabase real** | **Concluído** (PostgreSQL 17.11, depois da troca da senha do banco). Verificado no Supabase com testes desfeitos ao final (rollback): o CHECK tem os 5 novos status; existe a coluna `status_atualizado_em`; existem as políticas `produtos_owner_insert` e `produtos_owner_update`; a dona aplica os 5 status e edita produto; a dona não muda o `slug`; outra usuária vê 0 leads. O teste de ponta a ponta da vitrine (chave publishable) continuou passando, e o lead de teste foi removido |
| **Usuária dona no Supabase** | Ainda não foi criada. Sem ela, o painel no modo Supabase mostra "E-mail ou senha inválidos" ou "não está vinculado" |
| **WhatsApp oficial da Kika** | Ainda não foi informado. Isso afeta o botão da vitrine, não o painel, que abre a conversa com a cliente |
| **Senha de demonstração** | A senha do painel local existe só no comando de demonstração. Não está no repositório |
