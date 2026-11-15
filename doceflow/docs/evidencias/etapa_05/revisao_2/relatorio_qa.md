# Etapa 05: revisão de QA independente (rodada 2)

**Data:** 2026-11-14 · **Branch:** `dev` · **Commit revisado:** `f2f3555` (depois das etapas 1 a 4: arquitetura, segurança, produtos e pedidos)

**Ambientes:**
- Instância de QA isolada (SQLite) em `localhost:8506`.
- Instância com **banco fora do ar** em `localhost:8507`.
- Leituras no **Supabase de produção** só com a chave publishable, **sem gravar nada**.

**Navegador automatizado:**
- Celular emulado (375 × 812, Android): fluxos públicos.
- Desktop (1280 × 900): painel.

A rodada anterior (07/11) continua em `../relatorio_qa.md`. Ela foi feita antes das etapas 1 a 4 e foi mantida como histórico.

## 1. Resultado por verificação

| # | Verificação | Resultado | Evidência |
|---|---|---|---|
| 1 | **Inicialização** | ✅ Aprovado | As duas instâncias sobem. A vitrine carrega em ~4 s |
| 2 | **Carregamento de produtos** | ✅ Aprovado | 27 produtos e 28 imagens (com o logo), nenhuma quebrada. 7 categorias na ordem do cardápio. No **Supabase real**, 27 produtos lidos pela chave publishable. Capturas 01 e 02 |
| 3 | **Seleção e envio de orçamento** | ✅ Aprovado | Bem Casado, 50 unidades, retirada em 20/11/2026: protocolo `DF-261114-2556E2`. Captura 05 |
| 4 | **Campos obrigatórios** | ✅ Aprovado | Vazio: nome, WhatsApp, data e consentimento são apontados. Inválido: WhatsApp sem DDD e quantidade abaixo do mínimo (10 < 25). Capturas 03 e 04. No pedido, o endereço é obrigatório só na entrega |
| 5 | **Persistência e recuperação** | ✅ Aprovado | O banco tem **1** lead com os dados exatos e 3 pedidos com valor e endereço. O painel mostra os mesmos registros. A mudança de status persiste com data e hora |
| 6 | **Link do WhatsApp** | ✅ Aprovado | `wa.me/5511979855065` (número oficial). A mensagem decodificada corresponde ao registro gravado: protocolo, produto, quantidade e data. No pedido, leva o protocolo e os itens, **sem o endereço** (dado pessoal fora da URL) |
| 7 | **Envio duplicado** | ✅ Aprovado | O mesmo orçamento enviado de novo devolveu o **mesmo protocolo** e "Não criamos uma solicitação repetida". Continua 1 lead no banco. Captura 07 |
| 8 | **Autenticação administrativa** | ✅ Aprovado no modo local · ⚠️ Supabase Auth não testado de ponta a ponta | A senha errada mostra "Senha incorreta" (captura 13), e a certa abre o Painel. O bloqueio após 5 tentativas e o login pelo Supabase Auth estão cobertos pelo pytest (cliente simulado e banco real), mas não com a conta real da dona |
| 9 | **Bloqueio de acesso não autorizado** | ✅ Aprovado | Sem login, `/painel`, `/pedidos`, `/orcamentos`, `/produtos` e `/marketing` levam ao login, sem nenhum dado, indicador ou menu. No banco: 100 testes de acesso e RLS em PostgreSQL real (visitante, usuário sem perfil e dona de outra loja) |
| 10 | **Status comerciais** | ✅ Aprovado (depois da correção QA2-03) | "Venda concluída" **exige confirmação**: sem marcar, a tela pede a confirmação. Testados Novo → Venda concluída → Em atendimento. No pedido, Aguardando → Confirmado, com histórico. Capturas 16 e 17 |
| 11 | **Cadastro e edição de produtos** | ✅ Aprovado | O preço do Bolo Tradicional foi de R$ 90 para R$ 95 no painel, e a vitrine mostrou R$ 95,00 para um visitante novo. O cadastro, as fotos e a exclusão estão cobertos por 47 testes (etapa 3) |
| 12 | **Falhas no banco** | ✅ Aprovado (depois da correção QA2-04) | Com o banco fora do ar: a vitrine mostra "catálogo indisponível" em **5,7 s** (antes, 20 s), e a página de pedido mostra "pedidos indisponíveis" **sem exibir o formulário**. Não aparece traceback nem chave. A falha durante a gravação está coberta pelo pytest. Captura 18 |
| 13 | **Telas móveis** | ✅ Aprovado (depois de QA2-01 e QA2-02) | Sem rolagem horizontal em 375 px (`scrollWidth = 375`) na vitrine e no pedido. O calendário está em português e bloqueia datas passadas (captura 06). Diálogos legíveis (capturas 05, 11 e 12) |
| 14 | **Segredos expostos** | ✅ Aprovado | **Todo o histórico do Git**: 0 `sb_secret_`, 0 JWT, 0 URL de banco com senha e 0 `SUPABASE_DB_URL` preenchida. As 15 menções a `service_role` são avisos para **não** usá-la, e o único `ADMIN_PASSWORD` é um exemplo de documentação. Nenhum `.env` ou `secrets.toml` versionado (o `.gitignore` cobre os dois). A página com o banco fora do ar não mostra a chave |

**Critério final (catálogo → formulário → banco → WhatsApp → painel):** ✅ **funciona de ponta a ponta no ambiente de QA (SQLite)**, nos dois fluxos:
- **Orçamento:** `DF-261114-2556E2` foi da vitrine para o banco, gerou o link correto e apareceu no painel, onde o status foi atualizado.
- **Pedido:** `PD-261114-FA4DB0` passou pelo formulário e pelo resumo, foi para o banco com o protocolo e gerou o link do WhatsApp. No painel, foi confirmado com histórico, e os indicadores somaram R$ 870,00 = 480 + 150 + 240.

No **Supabase de produção**, o fluxo **não** foi percorrido com gravação. Veja a seção 4.

## 2. Defeitos encontrados e corrigidos

| ID | Gravidade | Defeito | Correção | Reteste |
|---|---|---|---|---|
| **QA2-02** | **Alta** (celular) | Depois de "Confirmar pedido", a página continuava rolada no fim do formulário. A cliente via **o formulário vazio**, e a confirmação com o protocolo e o botão do WhatsApp ficava fora da tela (medido: `confirmationVisible = false`). Ela podia achar que o pedido falhou e enviar de novo. É o mesmo problema que a rodada 1 corrigiu no orçamento (QA-01) e que voltou na página nova de pedidos | A confirmação aparece **dentro do diálogo**, na frente da cliente, com "Fechar". Depois de fechar, continua no topo da página | ✅ Navegador: confirmação e botão visíveis (captura 12 × 10) e teste `test_QA2_02_…` |
| **QA2-04** | Média | **Banco fora do ar = espera longa.** O SDK do Supabase espera até **120 s** e repete as tentativas sozinho. Com a conexão recusada, a vitrine ficou **20 s** sem nada. Com o servidor sem resposta, a espera pode chegar a **minutos** | Tempo limite de 10 s (5 s para conectar) e **sem novas tentativas automáticas**, o que também impede repetir gravações às cegas (`services/supabase_client.py`) | ✅ A chamada falha em 2,2 s (antes, 15,4 s), e a página mostra o aviso em 5,7 s. O catálogo real continua carregando (27 produtos). Teste `test_QA2_04_…` |
| **QA2-01** | Média | No resumo do pedido, a **tabela de itens aparecia em branco** no celular (tabela desenhada em canvas). A cliente via só o total, sem saber quais produtos estava confirmando. Canvas também não é lido por leitores de tela | Os itens viraram uma lista de texto: produto, quantidade, preço "a partir de" e subtotal estimado | ✅ Navegador (captura 11 × 09) e teste `test_QA2_01_…` |
| **QA2-03** | Baixa | Depois de salvar um status, o seletor "Lead" (e "Pedido") **continuava mostrando o status antigo** ("· Novo"), enquanto a lista e o banco já diziam "Venda concluída". Isso podia confundir a dona | O status saiu do rótulo do seletor e aparece numa linha própria, "Status atual: …", redesenhada a cada atualização. Corrigido em Orçamentos e Pedidos | ✅ Navegador (captura 16 × 15) e testes `test_QA2_03_…` (2) |

### Observações (não corrigidas; não bloqueiam)

| ID | Observação | Sugestão |
|---|---|---|
| OBS-1 | No campo de data, digitar os números direto na parte do **dia** aceita 8 dígitos sem passar para o mês. É comportamento do componente de data do Streamlit, não do DoceFlow. Pelo **calendário** (o caminho natural no celular) funciona sem problema | Nenhuma ação no código. Se as clientes reclamarem, trocar por três campos simples |
| OBS-2 | No celular, o logo ocupa quase metade da primeira tela, e o catálogo começa abaixo dela | Reduzir o logo no celular |
| OBS-3 | O link "🛒 Fazer um pedido" é discreto (parece texto) | Transformar em botão rosa, como "Ver catálogo e pedir orçamento" |

## 3. Ciclos de teste

| Ciclo | O que rodou | Resultado |
|---|---|---|
| 1 | `pytest` completo + navegador (vitrine, orçamento, pedido, painel) | `415 passed, 1 skipped` (`ciclo_01_pytest.txt`). **4 defeitos** encontrados no navegador (QA2-01 a 04): o pytest passava, mas a experiência real falhava |
| 2 | Correções + reteste no navegador de cada defeito | QA2-01, 02 e 03 ✅ no navegador. QA2-04 medido (15,4 s → 2,2 s) |
| 3 | `pytest` completo + reteste do banco fora do ar no navegador | `420 passed, 1 skipped` (`ciclo_03_pytest.txt`): os 415 anteriores + 5 regressões novas. O único teste pulado é o de `leads_antiga`, uma tabela que só existe em produção |

## 4. Não testado (declarado, sem afirmar que funciona)

1. **Gravação no Supabase de produção:** não enviei orçamento nem pedido de verdade para não misturar dados de teste com os reais. Em produção foram verificados:
   - a leitura do catálogo;
   - a recusa de um pedido inválido sem gravar (etapa 4);
   - o RLS pelo app.

   **Para fechar:** fazer 1 orçamento e 1 pedido reais pelo site publicado e conferir no painel.
2. **Login com a conta real da dona (Supabase Auth):** não tenho a senha dela, e não devo ter. A lógica de login foi testada pelo pytest.
3. **Envio de fotos para o Storage de produção:** depende do login da dona (veja a etapa 3).
4. **Celular de verdade:** foram feitos testes com celular emulado no navegador. Não abri em iPhone nem Android físicos.
5. **Abertura real do WhatsApp:** só o link foi conferido (número e texto). Não abri o aplicativo.
6. **Limite de envios (5 por hora por WhatsApp):** só existe no Supabase. Coberto pelo pytest em PostgreSQL real, não pelo navegador.
7. **Estúdio de Marketing e Instagram:** fora da lista desta revisão.

## 5. Arquivos

- `capturas/`: 18 capturas numeradas. As de defeitos têm o par ANTES/DEPOIS: 09/11 (QA2-01), 10/12 (QA2-02) e 15/16 (QA2-03).
- `ciclo_01_pytest.txt` e `ciclo_03_pytest.txt`: saída completa do pytest.
- **Código alterado:**
  - `pages/public/order.py` (QA2-01, QA2-02)
  - `pages/admin/quotes.py` e `pages/admin/orders.py` (QA2-03)
  - `services/supabase_client.py` (QA2-04)
- **Testes novos:**
  - `tests/test_pedidos.py` (3)
  - `tests/test_etapa04.py` (1)
  - `tests/test_seguranca_app.py` (1)
