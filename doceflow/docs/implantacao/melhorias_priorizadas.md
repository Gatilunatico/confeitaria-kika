# Melhorias priorizadas (14/11/2026)

**Prioridades:**
- **P0:** bloqueia o teste comercial.
- **P1:** fazer na primeira semana.
- **P2:** depois de ouvir a Kika e as clientes.

O esforço é estimado (P = horas, M = 1 a 2 dias, G = mais de 3 dias).

## P0: antes de mostrar para clientes

| # | Melhoria | Por quê | Quem | Esforço |
|---|---|---|---|---|
| 1 | **Publicar ou confirmar o app no Streamlit Cloud** (branch `dev`, Secrets do modelo) e registrar a URL | Sem URL pública não há teste real | Equipe | P |
| 2 | **Fechar o cadastro público** no Supabase Auth | Hoje qualquer pessoa cria conta. Ela não acessa dados, mas o cadastro não deve ficar aberto | Equipe | P |
| 3 | **Confirmar o WhatsApp** de atendimento com a Kika | Todo orçamento e pedido manda a cliente para esse número | Kika + equipe | P |
| 4 | **Fotos reais** dos 5 a 10 produtos principais | A vitrine usa ilustrações. Foto é o principal fator de decisão em confeitaria | Kika | M |
| 5 | **Teste de fumaça no celular** na URL pública | Nunca foi feito no endereço publicado | Equipe | P |

## P1: primeira semana de uso

| # | Melhoria | Por quê | Esforço |
|---|---|---|---|
| 6 | Botão **"Fazer um pedido"** em destaque na vitrine (hoje é um link discreto) | QA OBS-3: o caminho do pedido é pouco visível | P |
| 7 | **Logo menor no celular** | QA OBS-2: o catálogo começa abaixo da primeira tela | P |
| 8 | Marcar **2 a 4 destaques** | A seção Destaques está vazia | P (Kika) |
| 9 | **Aviso de pedido novo** para a Kika (e-mail ou contagem no topo do painel) | Hoje ela precisa abrir o painel para saber. Risco de demora na resposta | M |
| 10 | Apagar a tabela vazia `leads_antiga` e a conta extra do Auth (com confirmação da equipe) | Limpeza. Hoje não afetam o uso | P |
| 11 | Mover o app para a branch `main`, com `dev` só para desenvolvimento | Cada push na `dev` vai direto para o ar. Com clientes reais, convém revisar antes | P |

## P2: depois do teste com pessoas

| # | Melhoria | Por quê | Esforço |
|---|---|---|---|
| 12 | Botão **"Registrar pedido a partir deste orçamento"** | Hoje orçamento fechado e pedido são registros separados | M |
| 13 | Campo de data mais simples (3 campos ou só calendário) | QA OBS-1: digitar a data na parte do dia aceita números demais (componente do Streamlit) | M |
| 14 | Registro de **pagamento** (sinal e quitação) e indicador de receita recebida | Hoje o sistema mostra só o valor registrado e o combinado, não o recebido | G |
| 15 | **Taxa de entrega** por bairro ou distância | Hoje a entrega é combinada pelo WhatsApp | M |
| 16 | Publicação automática no **Instagram** pelo Estúdio de Marketing | A estrutura e o token via Vault estão prontos (migração 008), mas a integração não | G |
| 17 | Domínio próprio (ex.: `pedidos.kikacakes.com.br`) | Mais confiança para a cliente que `*.streamlit.app` | M |

A lista deve ser **reordenada depois das sessões de validação** (`relatorio_validacao.md`, seções 2 e 3). O que as pessoas tiverem dificuldade de fazer passa na frente.
