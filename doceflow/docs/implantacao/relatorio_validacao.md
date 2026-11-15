# Relatório de validação: demonstração e teste comercial

**Data:** 2026-11-14 · **Versão:** branch `dev` (depois da revisão de QA, rodada 2)

> **Regra deste relatório:** só está marcado como ✅ o que tem evidência verificável. O que depende de publicação, de pessoas reais ou de acesso que a equipe não tem está marcado como ⏳ **pendente**, sem resultado inventado.

## 1. Situação das atividades

| # | Atividade | Situação | Evidência / o que falta |
|---|---|---|---|
| 1 | Testes críticos aprovados | ✅ | 420 testes passando. Revisão de QA com 14 de 14 itens aprovados no ambiente de QA (`etapa_05/revisao_2/relatorio_qa.md`) |
| 2 | Projeto pronto para hospedagem | ✅ | `requirements.txt` com as versões mínimas testadas, modelo `.streamlit/secrets.toml.example`, passo a passo em `README_IMPLANTACAO.md` |
| 3 | Dependências e variáveis | ✅ preparadas · ⏳ conferir no Cloud | Os Secrets ficam no painel do Streamlit Cloud. A equipe precisa confirmar que estão no formato do modelo |
| 4 | Conexão com o Supabase | ✅ | Leitura em produção pela chave publishable: 27 produtos. Migrações 001 a 010 presentes. Falha de conexão mostra aviso em ~5 s (QA2-04) |
| 5 | WhatsApp verdadeiro | ✅ configurado · ⏳ **confirmar com a Kika** | O número do cardápio oficial (`5511…5065`) está no banco. Ainda não há confirmação explícita de que é o número de atendimento que ela quer usar |
| 6 | Produtos, fotos, preços e disponibilidade | ✅ produtos e preços · ❌ **fotos** · ⏳ destaques | 27 produtos reais publicados e com preço. **0 fotos reais** e 0 destaques: depende da Kika (guia rápido, seção "Produtos e fotos") |
| 7 | Autenticação e acesso aos dados | ✅ acesso · ⚠️ cadastro aberto · ⏳ login real | Visitante recusado em 7 tabelas privadas e em `cadastrar_admin` (produção). **O cadastro público do Supabase Auth está aberto** e deve ser fechado (passo 2.1 do README). O login da dona não foi testado, porque a equipe não deve ter a senha dela |
| 8 | Publicação | ⏳ **não verificada** | Não encontrei a URL do app publicado no repositório nem no histórico. O navegador não tem sessão no Streamlit Cloud. **Não afirmo que está publicado** |
| 9 | Teste da URL pública no celular | ⏳ **não realizado, por decisão da equipe** (14/11) | Fica para a sessão com a Kika (seção 5, passo 4). O mesmo teste foi feito no ambiente de QA, em celular emulado |
| 10 | Demonstração de 3 minutos | ✅ roteiro pronto | `roteiro_demo_3min.md` |

## 2. Validação com a confeiteira: ⏳ não realizada

Ainda **não houve sessão com a Kika**. O protocolo abaixo deve ser aplicado com ela usando o próprio celular ou computador, sem ajuda, enquanto alguém anota.

| # | Tarefa (falar só o objetivo, sem dizer onde clicar) | Concluiu? (sim / com ajuda / não) | Tempo | Dificuldades e erros | Comentário dela |
|---|---|---|---|---|---|
| C1 | "Cadastre um produto novo, com foto." | | | | |
| C2 | "Tem um orçamento novo. Encontre quem pediu e o quê." | | | | |
| C3 | "Fale com essa cliente pelo WhatsApp." | | | | |
| C4 | "Quais clientes você ainda precisa responder?" | | | | |
| C5 | "Essa cliente fechou. Registre a venda." | | | | |
| C6 | "Confirme o pedido novo e coloque o valor final." | | | | |

**Pergunta final (escala de 1 a 5 e por quê):**
- "Comparado a como você atende hoje, isto é mais rápido?"
- "Você usaria isto na próxima semana?"

**Referência para comparar:** antes da sessão, anote quanto tempo ela leva hoje, pelo WhatsApp e pelo direct, para responder um pedido de orçamento do início ao fim.

## 3. Validação com potenciais clientes: ⏳ não realizada

Teste com **5 pessoas** (o suficiente para achar a maioria dos problemas de uso), cada uma no próprio celular, com o link público.

| # | Tarefa | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|---|
| V1 | "Encontre um bolo para 20 pessoas." (encontrou? tempo) | | | | | |
| V2 | "Quanto vai custar, mais ou menos?" (entendeu que é "a partir de"?) | | | | | |
| V3 | "Peça um orçamento para o dia 20." (sem ajuda? tempo) | | | | | |
| V4 | "Avise a confeitaria." (o WhatsApp abriu com a mensagem certa?) | | | | | |
| V5 | "Agora faça um pedido com 2 produtos." (entendeu o resumo?) | | | | | |

**Anotar:** onde a pessoa hesitou, o que tocou errado, o que perguntou e o que disse espontaneamente.

**Ao final:** marcar os registros de teste como **Perdido** ou **Cancelado** no painel.

## 4. O que já foi validado no ambiente de QA (evidência verificável)

Esta seção não substitui o teste com pessoas reais. Ela mostra que os fluxos funcionam tecnicamente.

| Pergunta | Resultado no QA | Evidência |
|---|---|---|
| Consegue cadastrar um produto? | ✅ cadastro, edição, fotos e exclusão (47 testes). Preço editado pelo painel refletiu na vitrine | Etapa 3 e QA rodada 2, item 11 |
| Consegue ver um orçamento novo? | ✅ o Painel mostra "Leads novos" e a lista "Aguardando atendimento" | QA rodada 2, captura 14 |
| Consegue contatar o cliente? | ✅ botão de WhatsApp com mensagem pronta (Orçamentos e Pedidos) | Capturas 16 e 17 |
| Identifica as oportunidades pendentes? | ✅ indicadores de leads novos e de pedidos aguardando confirmação, com avisos | Captura 14 |
| Atualiza o status de uma venda? | ✅ com confirmação obrigatória para "Venda concluída" | QA rodada 2, item 10 |
| É mais rápido que o atendimento anterior? | ⏳ **só a Kika pode responder** | Seção 2 |
| A cliente encontra o produto? | ✅ tecnicamente (27 produtos, 7 categorias, filtros). ⏳ com pessoas | Captura 01 |
| Entende preços e condições? | ✅ aviso de preço "a partir de" em todo o fluxo. ⏳ com pessoas | Capturas 05 e 11 |
| Solicita orçamento sem ajuda? | ⏳ com pessoas. O fluxo foi feito no celular emulado | Capturas 03 a 07 |
| O WhatsApp abre com a mensagem certa? | ✅ o link foi conferido (número e texto). ⏳ abrir o aplicativo num celular real | QA rodada 2, item 6 |

## 5. Próximos passos para concluir a validação

1. A equipe publica (ou confirma) o app e registra a **URL pública** aqui.
2. Fechar o cadastro público no Supabase Auth.
3. A Kika confirma o número de WhatsApp e envia as fotos dos 5 produtos principais.
4. Teste de fumaça no celular (`README_IMPLANTACAO.md`, seção 5) e registro do resultado aqui.
5. Sessão com a Kika (seção 2) e com 5 clientes (seção 3), preenchendo as tabelas.
