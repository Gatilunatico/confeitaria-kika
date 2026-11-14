# Etapa 4: sistema de pedidos

**Data:** 2026-11-14 · **Branch:** `dev` · **Commit base:** `43d4ab2`

## 1. O que foi entregue

| Entregável | Onde |
|---|---|
| Formulário público de pedidos | `pages/public/order.py` (URL `/pedido`), com link na vitrine ("Já sabe o que quer?") |
| Resumo antes da confirmação | diálogo "Revise o seu pedido": itens, subtotais, total estimado, dados e aviso de preço |
| Protocolo de confirmação | aparece **só depois** que o banco devolve o protocolo, com o botão "Avisar a confeitaria no WhatsApp" |
| Persistência no Supabase | função `criar_pedido` (endpoint controlado) e tabelas `orders`, `order_items` e `order_history` |
| Gestão administrativa | `pages/admin/orders.py` (URL `/pedidos`) |
| Atualização de status | formulário do pedido (status, valor final, data, observações internas) |
| Indicadores comerciais | seção **Pedidos** no Painel (`pages/admin/dashboard.py`) |
| Banco | `database/migrations/010_pedidos_fluxo.sql` |
| Testes | `tests/test_pedidos.py` (29) e `tests/test_pedidos_postgres.py` (20) |

### Orçamento x pedido

- Os dois fluxos continuam separados:
  - **Solicitar orçamento** (por produto): grava em `leads`.
  - **Fazer pedido** (um ou vários produtos): grava em `orders`.
- Nenhum orçamento vira pedido automaticamente.

### Formulário público

- Campos: produtos (até 20), quantidade de cada um (dentro do mínimo e do máximo do produto), nome, WhatsApp, data desejada, retirada ou entrega, observações e consentimento.
- **Endereço:** obrigatório só na entrega. Na retirada, o endereço não é guardado.
- **Validação dupla:** a tela valida, e o servidor valida tudo de novo.
- **Resumo antes de confirmar:** mostra o preço "a partir de" e o subtotal estimado de cada item, além do total. Se algum item for "sob consulta", o total fica "a combinar".
- **Aviso de preço:** os valores são estimados, e a confeitaria confirma a disponibilidade e o valor final.
- **"Voltar e editar"** mantém o que foi digitado. Depois do pedido, o formulário é limpo.
- **Pedido repetido** (mesmo WhatsApp, data, modalidade e itens): não é duplicado, e o protocolo existente é informado.

### Estrutura de dados

A especificação foi adaptada ao schema existente:

| Especificação | Schema |
|---|---|
| `cliente_telefone` | `cliente_whatsapp` |
| `data_desejada` | `data_entrega` |
| `valor_total` | `valor_estimado` |
| `criado_em` / `atualizado_em` | `created_at` / `updated_at` |
| `product_id` / `nome_produto` | `produto_id` / `produto_nome` |

Novidades da migração 010:
- **Status inicial "Aguardando confirmação".** Antes era "Recebido"; não havia pedidos em produção para converter.
- **`endereco_entrega`** no pedido.
- **`subtotal`** em cada item, calculado pelo banco.
- **Tabela `order_history`.**

Os itens guardam o nome e o preço **do momento do pedido**. Testado: alterar o produto depois não muda o pedido.

### Painel: Pedidos

- **Lista:** protocolo, data do pedido, cliente, data desejada, modalidade, número de itens, valor estimado, valor final e status.
- **Filtros:** busca por nome ou protocolo, filtro por status (vários) e período pela **data do pedido** ou pela **data desejada**.
- **Aviso** de pedidos aguardando confirmação.
- **Detalhes:**
  - Contato, com botão para abrir a conversa no WhatsApp com o protocolo.
  - Entrega: data, modalidade e endereço.
  - Observações do cliente.
  - Produtos com o preço registrado e os subtotais.
  - Valor estimado e valor final combinado.
- **Atualizar:** status, valor final combinado, data de entrega e observações internas (o cliente não vê).
- **Histórico de alterações:** quem alterou (cliente pelo site ou painel), quando e o quê.

### Indicadores (Painel)

- **Total de pedidos, Aguardando confirmação, Confirmados, Em produção, Entregues e Valor registrado (estimado).**
- Respeitam o mesmo filtro de período dos orçamentos.
- O **valor registrado** soma os valores **estimados** dos pedidos não cancelados. A tela explica que é o valor **solicitado, não a receita recebida**: o sistema não controla pagamentos. Pedidos com item sob consulta não entram na soma, e a tela informa quantos são.

## 2. Segurança

| Regra | Como |
|---|---|
| Cliente não consulta pedidos de terceiros | o visitante não tem nenhuma permissão em `orders`, `order_items` e `order_history`. `criar_pedido` devolve só o pedido recém-criado |
| Só a proprietária autorizada consulta e altera | RLS com `is_store_admin()`. Testado com a dona de outra confeitaria, um usuário sem perfil e o visitante |
| Endpoint controlado | `criar_pedido` (SECURITY DEFINER): valida a confeitaria (pelo slug do servidor), a modalidade, o endereço, a data, o consentimento e cada item, e limita envios |
| Preços validados no servidor | o navegador envia só produto e quantidade. Testado: campos de preço enviados à força são ignorados |
| Não confiar no navegador | a dona não altera `valor_estimado`, itens, WhatsApp nem a confeitaria (permissão por coluna). O histórico não pode ser escrito, alterado nem apagado pelo app |
| Integridade | itens só de produtos da mesma confeitaria (FK composta). Produto com pedido não pode ser excluído. Status fora da lista é recusado pelo banco |

## 3. Testes

**Suíte completa:** `415 passed, 1 skipped`. São 49 testes novos nesta etapa, e 6 testes antigos foram atualizados para o status e o endereço novos.

| Tema | Testes |
|---|---|
| **Acesso** | visitante não abre `/pedidos`; visitante, usuário sem perfil e dona de outra loja não leem nem alteram pedidos, itens e histórico; a função devolve só o próprio pedido |
| **Integridade** | preço vem do banco (preço injetado é ignorado); snapshot de nome e preço; subtotal calculado; retirada não guarda endereço; item sob consulta deixa o total vazio; a dona não altera valor estimado, itens, WhatsApp nem confeitaria; histórico imutável; status antigo recusado; item de outra loja recusado sem gravar nada; itens precisam ser lista |
| **Validação** | endereço obrigatório na entrega; modalidade inválida; produto inexistente, despublicado ou indisponível; quantidade fora do limite; data passada; pedido repetido não duplica |
| **Telas** | fluxo completo (formulário → resumo → nada gravado → confirmar → protocolo → formulário limpo); erros e "Voltar e editar"; lista, busca, atualização e histórico no painel; filtro por status; indicadores no Painel |
| **Supabase (cliente simulado)** | envia só slugs, quantidades e endereço (nenhum campo de preço); lista com itens; histórico filtrado pela confeitaria |

### Verificação no navegador (app local, banco de teste)

1. **Vitrine (visitante):** apareceu o quadro "Já sabe o que quer?", e o link levou a `/pedido`.
2. **Envio sem dados:** escolhi Bem Casado e Docinhos Tradicionais e marquei Entrega. Ao revisar sem preencher, apareceram as 5 mensagens de campo, inclusive "informe o endereço completo".
3. **Resumo:** com os campos preenchidos, abriu o diálogo de revisão (total "A partir de R$ 300,00", dados, endereço e aviso de preço).
4. **Confirmação:** apareceu "Pedido registrado! Protocolo PD-261114-777138", com o status "Aguardando confirmação" e "ainda não confirma o pedido nem o preço final". O link do WhatsApp leva o protocolo, e o formulário ficou limpo.
5. **Painel:**
   - Indicadores: Total de pedidos 1, Aguardando confirmação 1 e Valor registrado R$ 300,00.
   - Página Pedidos: o aviso de 1 pedido aguardando, o endereço, o contato e o valor estimado.
   - Defini o valor final de R$ 320,00 e salvei: "Pedido atualizado".
   - O histórico mostrou "Pedido registrado pelo site · cliente (site)" e "Valor final: — → R$ 320,00 · painel".
6. **Ajuste depois do teste:** o menu da administração usa 📦 para "Pedidos", para não confundir com "🛒 Fazer pedido".

**Limitação da verificação no navegador:** o painel do navegador estava em segundo plano. Nesse estado, a lista de status e as quantidades não responderam à automação. A troca de status e as quantidades estão cobertas pelos testes automatizados das telas.

## 4. Pendências

1. **Migração 010 aplicada em produção em 14/11**, numa transação única. A verificação depois confirmou:
   - O status padrão é "Aguardando confirmação".
   - `endereco_entrega` e `subtotal` foram criados.
   - `order_history` tem RLS, e o gatilho `orders_historico` está ativo.
   - Só existe a versão nova de `criar_pedido`.
   - Os 27 produtos e os 3 orçamentos foram mantidos. A produção ainda não tem pedidos.
   - Pelo app, com a chave publishable:
     - Um pedido de entrega sem endereço foi recusado pela função nova **sem gravar nada**.
     - O visitante não lê `orders` nem `order_history`.
   - Nenhum pedido de teste foi criado em produção.
2. **Conversão de orçamento em pedido:** não foi feita. Por enquanto a dona registra o acerto pelo WhatsApp. Se for útil, pode virar um botão explícito "Registrar pedido a partir deste orçamento".
3. **Pagamentos e receita recebida:** fora do escopo. O sistema não registra pagamentos.
