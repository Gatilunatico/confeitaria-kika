# Revisão independente do MVP DoceFlow — etapa 05

> Atualização posterior: consulte [supabase_integracao.md](supabase_integracao.md). A versão integrada teve os conflitos corrigidos e passou em 116 testes; autenticação administrativa foi simulada nos testes conforme orientação do usuário. Este relatório preserva o diagnóstico inicial.


**Data:** 07/11/2026. **Resultado: REPROVADO para o fluxo completo.**

O fluxo público catálogo → formulário → banco → link de WhatsApp funciona no ambiente SQLite de teste. A passagem para o painel administrativo falha após o login. Status comerciais, indicadores e manutenção de produtos não podem ser aprovados nesta versão integrada. O critério de ponta a ponta não foi atendido.

O escopo é o MVP: não foram exigidos recursos decorativos, contas corporativas ou integrações além das já presentes. As reprovações impedem funções expressamente pedidas.

## Ambiente e método

- Checkout da branch `dev` aberto no VS Code, com alterações locais já preparadas no índice antes desta revisão. Nenhum commit, push ou banco remoto foi alterado.
- Python 3.12, pytest 8.4.2, Streamlit 1.67.0, Pandas 2.3.3; Chrome instalado, controlado com Playwright 1.64.1.
- Aplicação realmente iniciada em porta local 8515. Segunda instância em 8516 para falha real de acesso ao SQLite.
- Bancos temporários próprios de QA e dados sintéticos. Não foi usado o banco operacional da confeitaria. A senha do servidor de QA é temporária e não corresponde a credencial real.
- Testes de serviço, Streamlit AppTest, navegação real, inspeção direta do SQLite e inspeção visual das capturas.
- Telas em 1366 × 900, 390 × 844 e 360 × 844. Não houve envio de mensagem, contato com cliente ou submissão externa pelo WhatsApp.

## Matriz de funcionalidades

| # | Funcionalidade | Resultado | Evidência e limite |
|---|---|---|---|
| 1 | Inicialização | Aprovada após correções limitadas | Vitrine iniciou e respondeu no navegador. Antes da revisão havia marcadores de conflito em arquivos executáveis. |
| 2 | Carregamento de produtos | Aprovada — SQLite | Catálogo com seis produtos, cinco botões de solicitação e um produto indisponível. Captura 01 e resultado JSON do navegador. |
| 3 | Seleção e registro de orçamento | Aprovada — fluxo público | Selecionado bolo de festa, nome/contato/dados sintéticos preenchidos; registro encontrado no SQLite antes do link. Captura 03. |
| 4 | Campos obrigatórios | Aprovada | Envio vazio mostra nome, WhatsApp, data e consentimento ausentes. Captura 02 e testes existentes. |
| 5 | Persistência e recuperação | Parcial | Repositório público recupera registros em nova instância; navegador e outro processo leram o mesmo arquivo. Recuperação pelo painel falha. Não foi validado reinício de uma implantação de produção. |
| 6 | Link de WhatsApp | Aprovada — geração | Destino `/5511912345678`; mensagem contém protocolo, produto, quantidade e nome do registro gravado. O usuário ainda precisa enviar no WhatsApp. Abertura de app nativo e entrega da mensagem não testadas. |
| 7 | Submissões duplicadas | Aprovada | Repetição exibiu aviso e conservou um único registro para o pedido sintético verificado. Captura 04 e JSON. |
| 8 | Autenticação administrativa | Parcial | Login local renderiza, rejeita senha errada e aceita a correta. Em seguida o painel falha. Troca de confeitaria não invalida a sessão. Supabase Auth real não testado. |
| 9 | Bloqueio não autorizado | Parcial | Sem senha configurada, acesso bloqueado nos testes; visitante sem login não vê dados de clientes; senha errada rejeitada também no navegador. Isolamento da consulta pública foi testado. Não se aprova isolamento administrativo completo, em razão da sessão e da integração defeituosas. |
| 10 | Status comerciais e indicadores | Reprovada / bloqueada | Erro ao carregar leads interrompe a execução antes de usar status e indicadores. Não há validação positiva de persistência de venda nesta revisão. |
| 11 | Cadastro e edição de produtos | Reprovada / bloqueada | A execução para na aba de atendimento antes da manutenção de produtos. O repositório antigo também usa `_SAMPLE_PRODUCTS` e tabela `products`, enquanto a vitrine atual usa `SEED_PRODUCTS` e `produtos`. |
| 12 | Falhas de banco | Parcial | Vitrine com caminho SQLite inválido mostra indisponibilidade sem sucesso falso nem traceback. Falhas de gravação também passaram em AppTest. O admin não trata sua falha de leitura e exibe erro técnico. |
| 13 | Experiência móvel | Parcialmente aprovada | Catálogo e formulário inspecionados em 360 e 390 pixels, sem overflow horizontal. Campos exigem rolagem vertical normal. Não houve teste em telefone físico, teclado virtual, envio móvel completo ou uso móvel do painel funcional. |
| 14 | Segredos expostos | Aprovada no escopo inspecionado | Nenhum `.env`/`secrets.toml` versionado nem padrões conhecidos de chave privada, OpenAI, Supabase secret ou JWT encontrados no código atual. Não comprova ausência absoluta: histórico Git, configuração de produção e contas externas não foram auditados. |

## Defeitos, gravidade e correções

| ID | Gravidade | Problema | Situação |
|---|---|---|---|
| QA-01 | Crítica | Marcadores `<<<<<<<`, `=======` e `>>>>>>>` da integração estavam em app, admin, catálogo, banco, leads e README. Arquivos executáveis não podiam ser interpretados corretamente. | Corrigido de forma limitada: conflitos removidos, preservando a implementação pública atual. Isso não resolve a incompatibilidade semântica entre as etapas 03 e 04. A comprovação dos erros iniciais está em `conflitos_iniciais.json`. |
| QA-02 | Crítica | Painel e testes da etapa 04 importam `services.quotes`, removido/renomeado na etapa 03. O repositório administrativo espera `leads(tenant, payload, ...)`, enquanto o banco público usa `leads(confeitaria_id, cliente_nome, ...)`. Também há dois modelos de produtos. | **Aberto.** `ModuleNotFoundError` reproduzido em pytest e no navegador após login correto. Adicionar apenas um alias de importação não corrige o esquema divergente. |
| QA-03 | Alta | A sessão usa `STORE_ID` para vincular a confeitaria, mas a configuração efetiva do repositório público usa `STORE_SLUG`. Mudar `store_slug` mantém o mesmo token. | **Aberto.** Novo teste independente reproduz a falha. É uma invalidação de sessão incorreta; não foi demonstrado vazamento efetivo de dados de outra loja. |
| QA-04 | Alta | A suíte completa para durante a coleta de `test_etapa04.py`, impedindo aprovação da regressão completa. | **Aberto.** Não se excluiu permanentemente nem se marcou como sucesso o teste incompatível. A exclusão foi usada apenas para diagnosticar os demais cenários. |
| QA-05 | Média | Falha de leitura administrativa não é capturada; o admin expõe traceback/caminhos técnicos depois de autenticar. | **Aberto.** Captura 07. Não foram observados valores de credenciais nesse erro. |
| QA-06 | Alta | Após resolver os conflitos, o admin chamava `logging.getLogger` sem importar `logging`, impedindo até o login. | Corrigido adicionando a importação. Reteste: login/bloqueio básicos passaram; permaneceu QA-02 após autenticação. |

## Ciclos e resultados reais

1. **Diagnóstico inicial:** identificados conflitos de integração. A primeira tentativa de pytest partiu da raiz do repositório com configuração de importação inadequada e falhou na coleta (`ciclo_01_pytest.txt`); esse arquivo não é contabilizado como teste funcional. A análise das cópias originais confirma três arquivos Python com erro de sintaxe. Removidos os marcadores, a execução na pasta correta expôs a importação incompatível da etapa 04.
2. **Após resolver conflitos:** suíte completa bloqueada por `services.quotes` (`ciclo_02_pytest.txt`). Execução diagnóstica dos demais testes: **69 passaram, 4 falharam, 1 módulo foi ignorado** (`ciclo_02_testes_isolados.txt`). As falhas administrativas identificaram a importação ausente de `logging`.
3. **Após corrigir a importação de logging:** testes anteriores isolados: **72 passaram, 1 falhou, 1 módulo foi ignorado**. Criados dois testes independentes para a integração pública/admin e troca de confeitaria; ambos falharam. Resultado diagnóstico final, incluindo-os: **72 passaram, 3 falharam, 1 módulo foi ignorado** em 19,03 s (`resultado_final_isolado.txt`). A suíte completa permanece com **1 erro de coleta e 1 módulo ignorado** (`ciclo_03_pytest_completo.txt`). Compilação passou, mas não substitui esses resultados funcionais.

Os testes PostgreSQL reais foram ignorados por indisponibilidade de `pgserver`/`psycopg` no ambiente. Os mocks do SDK Supabase que passaram não equivalem a validação de RLS em produção.

**Bloqueio de correção:** a revisão automática rejeitou uma proposta que reescrevia o repositório/autenticação e criava uma migração de permissões de produtos no Supabase. O motivo informado foi ultrapassar correções pontuais de QA e potencialmente alterar controles de acesso sem autorização explícita para esse efeito. Essa proposta não foi executada. Não houve migração, mudança de permissões ou contorno da rejeição. A integração ampla permanece pendente de aprovação; os testes e as evidências independentes foram concluídos.

## Evidências

- [Catálogo desktop](01_catalogo_desktop.png)
- [Erros dos campos obrigatórios](02_campos_obrigatorios.png)
- [Solicitação registrada e link](03_solicitacao_registrada.png)
- [Duplicidade bloqueada](04_duplicidade_bloqueada.png)
- [Login administrativo](05_admin_login.png)
- [Senha incorreta](06_senha_incorreta.png)
- [Erro real do painel após login](07_admin_bloqueio_integracao.png)
- [Catálogo móvel 360](08_catalogo_mobile_360.png) e [390](08_catalogo_mobile_390.png)
- [Formulário móvel 360](09_formulario_mobile_360.png) e [390](09_formulario_mobile_390.png)
- [Banco indisponível](10_banco_indisponivel.png)
- Resultados estruturados: `navegador_resultados.json`, `admin_navegador_resultados.json`, `mobile_falha_banco.json` e `segredos_verificacao.json`.
- Regressões novas: `tests/test_etapa05.py`; saída: `regressoes_independentes.txt`.

As capturas são do navegador real. Algumas representam apenas a região visível: a página Streamlit e o diálogo possuem rolagem interna. Houve ajustes no roteiro de automação para fechar o calendário, clicar no rótulo estilizado de consentimento e aguardar componentes carregarem; isso não alterou o produto nem contou como correção funcional. Timeouts intermitentes de navegação foram repetidos e não foram classificados isoladamente como defeito confirmado da aplicação.

## Próximo passo mínimo para aprovar o MVP

Integrar o admin ao mesmo repositório e esquema da vitrine, preservar a autenticação adequada de cada backend, vincular sessão à confeitaria efetiva e tratar falhas administrativas. Depois executar novamente a suíte completa e provar no navegador: criar lead → localizar no painel → alterar status com confirmação manual de venda → reiniciar/recuperar → editar produto e observar a vitrine. Sem essa prova, não se aprova o MVP completo.
