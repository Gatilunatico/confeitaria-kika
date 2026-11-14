# Etapa 3: gestão de produtos e upload de imagens

**Data:** 2026-11-14 · **Branch:** `dev` · **Commit base:** `b79984e`

## 1. O que foi entregue

| Entregável | Onde |
|---|---|
| Formulário de cadastro | `pages/admin/products.py` → "Cadastrar novo produto" (campos em `components/product_form.py`) |
| Formulário de edição | aba **Editar** do produto selecionado |
| Componente de upload | `components/image_manager.py` (seleção, pré-visualização, envio, galeria) |
| Integração com o Supabase Storage | `services/image_service.py` (bucket `product-images`) |
| Integração com a tabela de produtos | `services/repository.py` (`produtos` = products) |
| Integração com `product_images` | `services/repository.py` (`list/add/set_principal/delete_product_image`) |
| Atualização automática do catálogo | `pages/public/catalog.py` lê os produtos a cada carregamento; mostra foto principal, destaque e prazo |
| Banco | `database/migrations/009_gestao_produtos.sql` |
| Testes | `tests/test_gestao_produtos.py` (27) e `tests/test_gestao_produtos_postgres.py` (20) |

### Campos do produto

| Pedido | Campo |
|---|---|
| Nome, descrição, categoria, preço | já existiam (o preço continua "a partir de", "estimado" ou "sob consulta") |
| Quantidade mínima | já existia (`qtd_min`, junto da máxima) |
| Tempo estimado de produção | **novo** `prazo_producao_dias` (vazio = não se aplica; 0 = pronta entrega; até 90) |
| Disponibilidade | já existia ("Disponível para orçamento") |
| Destaque no catálogo | **novo** `destaque`: seção **⭐ Destaques** no topo da vitrine e selo no card |
| Status de publicação | `publicado` (Etapa 2), agora também com botão **Publicar / Despublicar** |

### Tela de produtos (painel)

- A tabela agora mostra também destaque, foto e tempo de produção.
- Ao escolher um produto, abrem 4 abas:
  - **Visualizar:** o card exatamente como aparece na vitrine, o status e o botão Publicar/Despublicar.
  - **Editar:** todos os campos.
  - **Fotos:** galeria, escolha da foto principal, remoção com confirmação e envio de fotos novas.
  - **Excluir:** pede uma caixa de confirmação antes de liberar o botão.
- A aba aberta continua aberta depois de cada ação.
- Depois de cadastrar, o produto novo já abre na aba **Fotos**, o próximo passo natural.
- O que já existia continua: tabela, seleção, edição, cadastro e imagem padrão da pasta do projeto, que aparece quando não há foto enviada.

### Fluxo das fotos

1. **Seleção no dispositivo:** várias fotos de uma vez, em JPG, PNG ou WEBP.
2. **Pré-visualização antes do envio:** cada arquivo mostra a miniatura ou o motivo da recusa. Só os válidos são enviados.
3. **Validação de formato e tamanho:** confere o conteúdo real do arquivo, não a extensão, com no máximo 5 MB.
4. **Reprocessamento:** a foto é gravada de novo pelo servidor. Isso corrige a rotação do celular, reduz a no máximo 1600 px e **remove os metadados, inclusive a localização GPS**. O arquivo salvo nunca são os bytes originais.
5. **Upload para o Storage:** caminho `product-images/<confeitaria>/<produto>/<id>.<ext>`, sem sobrescrever arquivos existentes.
6. **Registro em `product_images`:** guarda só os metadados (caminho, descrição, principal, ordem). **Nenhum binário vai para o banco.**
7. **Associação ao produto certo:** o banco confere que o caminho bate com a confeitaria e o produto (CHECK) e que o produto é da mesma confeitaria (FK composta).
8. **Foto principal:** a primeira enviada vira principal. "Tornar principal" troca a foto numa única operação no banco. Se a principal for removida, a seguinte assume.
9. **Tratamento de erros:**
   - Se o registro falhar, o arquivo enviado é apagado.
   - Erros de vários arquivos aparecem juntos, e os que deram certo são mantidos.
   - Mensagens técnicas não aparecem na tela.
   - Limite de 10 fotos por produto.

### Exclusão de produto

- Exige confirmação e apaga o produto, os registros de fotos e os arquivos.
- **Produtos com orçamentos ou pedidos não podem ser excluídos**, para não perder o histórico. O app explica isso e orienta a despublicar. Quem garante é o banco (as chaves estrangeiras não apagam em cascata), não a tela.

## 2. Segurança (garantida no servidor, não só na tela)

| Regra | Como |
|---|---|
| Só administradoras autorizadas cadastram, alteram ou excluem | `require_admin()` em todas as páginas. No banco, as políticas `produtos_admin_insert/update/delete` usam `is_store_admin()` |
| Upload respeita a confeitaria | política do Storage por pasta (`storage_folder_admin`), CHECK do caminho e FK composta |
| Visitante não sobrescreve nem exclui fotos | sem permissão no Storage nem em `product_images`. Testado também para a dona de **outra** confeitaria e para um usuário logado sem perfil |
| Não confiar só na interface | o banco aplica o limite de fotos (gatilho), o prazo de 0 a 90 dias (CHECK), o bloqueio de exclusão com histórico (FK) e a foto principal de outra loja (`foto_invalida`) |
| Produto não publicado | não aparece na vitrine, e as fotos dele também ficam invisíveis para visitantes (RLS da 006) |

## 3. Testes

**Suíte completa:** `363 passed, 1 skipped`. São 47 testes novos nesta etapa.

| Tema | Testes |
|---|---|
| **Cadastro** | criar pela tela → aparece na vitrine e nos Destaques; cadastro como rascunho fica invisível; formulário inválido não grava; validação do prazo; criação com destaque e prazo no banco real |
| **Edição** | preço, descrição, prazo e destaque editados pela tela → a vitrine reflete as mudanças |
| **Publicação** | botão Publicar/Despublicar → o produto some e volta na vitrine; fotos de produto despublicado ficam invisíveis para visitantes |
| **Exclusão** | botão travado sem confirmação; produto com orçamento ou pedido é bloqueado (SQLite, Supabase e banco real); visitante, usuário sem perfil e dona de outra loja não excluem |
| **Upload** | reprocessamento (1600 px, sem EXIF/GPS); arquivos recusados (vazio, SVG, GIF, mais de 5 MB); registro e arquivo na pasta certa; primeira foto vira principal; troca de principal; remoção que promove a seguinte; limite de 10 (app e banco); produto de outra loja recusado; exclusão do produto apaga os arquivos |
| **Supabase (cliente simulado)** | catálogo usa a URL da foto principal; catálogo continua funcionando se a tabela de fotos falhar; colunas novas enviadas com a confeitaria da sessão; segunda foto não vira principal; limite verificado antes do upload; troca de principal via função do banco; exclusão bloqueada não apaga fotos; exclusão permitida limpa o Storage |
| **Tela de fotos** | galeria, troca de principal e remoção com confirmação (AppTest) |

### Verificação no navegador (app local, banco de teste)

- Login → Produtos → cadastrei "Torta de Limão" (Tortas, R$ 95/kg, 3 dias, destaque). Ela abriu selecionada.
- Na aba Fotos, selecionei 2 fotos e um arquivo falso (`falso.jpg`, que era HTML). A pré-visualização mostrou as 2 fotos, recusou o falso com "Arquivo não é uma imagem válida" e liberou "Enviar 2 foto(s)".
- Resultado do envio: "2 foto(s) enviada(s)". A galeria mostrou "2 de 10" com uma foto principal.
- "Tornar principal" funcionou, e a aba Fotos continuou aberta. "Remover" pediu confirmação, e a foto restante virou principal sozinha.
- Abri a vitrine numa sessão nova, como visitante:
  - Apareceram a seção "⭐ Destaques" e "Todos os produtos".
  - O card da torta mostrou a foto enviada, o selo de destaque, o preço e "Produção em cerca de 3 dias".
  - Nada do painel apareceu.
- Ajustes feitos depois desse teste:
  - A aba aberta passou a continuar aberta depois de cada ação; antes, voltava para Visualizar.
  - As opções Publicado, Disponível e Destaque ficaram empilhadas; antes, os rótulos eram cortados.

## 4. Pendências

1. **Migração 009 aplicada em produção em 14/11**, numa transação única. A verificação depois confirmou:
   - As colunas `destaque` e `prazo_producao_dias` foram criadas.
   - Os 27 produtos e os 3 orçamentos foram mantidos.
   - A política de exclusão só vale para administradoras, e o gatilho do limite de fotos está ativo.
   - O visitante não exclui produtos nem troca a foto principal: testado pelo app com a chave publishable, a exclusão foi recusada.
2. **Envio real de fotos para o Storage de produção:** não foi testado, porque exige o login da dona. Ele foi testado com o banco real local (políticas) e com o cliente simulado (fluxo do app).
