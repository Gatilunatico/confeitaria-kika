# Schema do banco DoceFlow: referência

Supabase (PostgreSQL 17) · projeto `dfimrkfcudidosdldsjv` · região AWS `us-west-2`.
**Multi-tenant:** todo registro de uma confeitaria tem `confeitaria_id`. A autorização é aplicada **no banco** (RLS), não só nas páginas do app.

## 1. Migrações (ordem de execução)

| Arquivo | O que faz | Produção |
|---|---|---|
| `001_schema_leads.sql` | `confeitarias`, `produtos`, `leads`, RLS, `criar_lead` | ✅ aplicada |
| `002_painel_admin.sql` | funil de status, `status_atualizado_em`, escrita de produtos | ✅ aplicada |
| `003_catalogo_real.sql` | catálogo oficial (27 produtos) e WhatsApp | ✅ aplicada |
| `004_marketing.sql` | `marketing_posts` e bucket privado `marketing` | ✅ aplicada (14/11) |
| `005_admin_profiles_rls.sql` | `admin_profiles`, `is_store_admin()`, `cadastrar_admin()`, `produtos.publicado`, FKs compostas, todas as políticas reescritas | ✅ aplicada (14/11) |
| `006_product_images.sql` | `product_images` e bucket `product-images` | ✅ aplicada (14/11) |
| `007_orders.sql` | `orders`, `order_items`, `criar_pedido()`, limites contra abuso (inclusive em `criar_lead`) | ✅ aplicada (14/11) |
| `008_instagram_accounts.sql` | `instagram_accounts` (metadados; token só por referência ao Vault) | ✅ aplicada (14/11) |
| `009_gestao_produtos.sql` | `produtos.destaque` e `prazo_producao_dias`, exclusão de produtos pela administradora, limite de 10 fotos por produto, `definir_foto_principal()` | ✅ aplicada (14/11) |
| `seed.sql` | confeitaria e produtos iniciais (projeto novo) | — |

Todas são **idempotentes**: rodar de novo não duplica nem apaga nada. **Nenhuma apaga ou recria tabela existente.** A tabela `products` da especificação é a tabela existente **`produtos`**, que foi mantida para não quebrar dados, funções e o app.

## 2. Entidades

| Entidade (especificação) | Tabela | Chaves e relações | Observações |
|---|---|---|---|
| confeitarias | `confeitarias` | `id`; `slug` único | `owner_user_id` foi mantida por compatibilidade, mas a **autorização passa a usar `admin_profiles`** |
| admin_profiles | `admin_profiles` (nova) | PK `user_id` → `auth.users`; `confeitaria_id` → confeitarias | `papel` (proprietaria, equipe) e `ativo`. **Um usuário pertence a uma única confeitaria** |
| products | `produtos` | `(confeitaria_id, slug)` único; **`(id, confeitaria_id)` único (nova)** | **nova coluna `publicado`**: só os publicados aparecem para o visitante. Na 009: `destaque` (seção Destaques da vitrine) e `prazo_producao_dias` (0 a 90, opcional) |
| product_images | `product_images` (nova) | FK composta `(produto_id, confeitaria_id)` → produtos | o caminho no Storage precisa começar por `<confeitaria_id>/<produto_id>/` (CHECK); no máximo uma foto principal por produto; **no máximo 10 fotos por produto** (gatilho da 009). O arquivo fica no Storage, a tabela guarda só os metadados |
| leads | `leads` | **nova FK composta `(produto_id, confeitaria_id)`**; `(id, confeitaria_id)` único | validada contra os registros atuais |
| orders | `orders` (nova) | `(id, confeitaria_id)` único; `(confeitaria_id, fingerprint)` único; FK composta opcional para `leads` | status Recebido → Confirmado → Em produção → Pronto → Entregue / Cancelado; `valor_estimado` ("a partir de") e `valor_final` (definido pela dona) |
| order_items | `order_items` (nova) | FKs compostas para `orders` e `produtos` **da mesma confeitaria** | snapshot de nome, unidade e preço |
| instagram_accounts | `instagram_accounts` (nova) | `confeitaria_id` único | `token_vault_id` **não pode ser lido nem gravado** pelo app (permissão por coluna) |
| marketing_posts | `marketing_posts` (004) | `confeitaria_id`, `produto_id` | políticas reescritas na 005 |

**Índices novos:** `admin_profiles(confeitaria_id)`, `produtos(id, confeitaria_id)`, `leads(id, confeitaria_id)`, `product_images(produto_id, ordem)`, `product_images(produto_id) where principal`, `orders(confeitaria_id, created_at)`, `orders(confeitaria_id, cliente_whatsapp, created_at)` e `order_items(order_id)`.

## 3. Autorização

- **`is_store_admin(confeitaria_id)`** é a única regra usada pelas políticas. Ela é verdadeira só se `auth.uid()` tem **perfil ativo** naquela confeitaria e a confeitaria está ativa.
- **O usuário não altera o próprio acesso.** `admin_profiles` só permite ler o próprio perfil: não há permissão de insert, update ou delete para `anon` nem `authenticated`. As colunas `owner_user_id`, `slug` e `ativo` de `confeitarias` também não são editáveis pelo app.
- **`cadastrar_admin(email, slug)`** só pode ser executada no SQL Editor (papel `postgres`). Ela recusa vincular um usuário que já administra outra confeitaria.

| Tabela | Visitante (`anon`) | Logado sem perfil | Administradora da confeitaria |
|---|---|---|---|
| confeitarias | lê as ativas | lê as ativas | + edita `nome` e `whatsapp` da própria |
| produtos | lê os **publicados** | lê os publicados | lê todos da própria, cria, edita (sem mudar `slug` nem a confeitaria) e **exclui** (009), exceto produtos com orçamentos ou pedidos |
| product_images | lê as de produtos publicados | idem | gerencia as da própria; troca a principal por `definir_foto_principal()` |
| leads, orders, order_items | **sem acesso** (só cria pelas funções) | sem acesso | lê e altera só os campos permitidos (status, valor final, data, observações internas) |
| admin_profiles | sem acesso | lê o próprio (se existir) | lê o próprio |
| marketing_posts | sem acesso | sem acesso | tudo, só na própria |
| instagram_accounts | sem acesso | sem acesso | lê e edita `username` (o token nunca) |

## 4. Fluxos públicos (funções SECURITY DEFINER)

- **`criar_lead(...)`**: orçamento de um produto. Desde a 007, aceita só **produtos publicados** e aplica **limite de envios**.
- **`criar_pedido(slug, nome, whatsapp, data, modalidade, obs, itens jsonb, origem, consentimento)`**:
  - Aceita de 1 a 20 itens, sem repetir produto. Cada produto precisa ser **da confeitaria do slug**, publicado e disponível, com a quantidade dentro do mínimo e do máximo.
  - Calcula o valor estimado e não duplica pedidos repetidos.
  - Devolve só o próprio pedido.
- **Limite contra abuso:** 5 envios por hora por WhatsApp e 30 por minuto por confeitaria, somando orçamentos e pedidos. Acima disso, a função recusa com `limite_excedido`.
- **Escolha da confeitaria:** o visitante **não informa `confeitaria_id`**. O app envia o `STORE_SLUG` configurado no servidor, e a função só grava na confeitaria desse slug, com produtos dela.

## 5. Storage

| Bucket | Acesso | Limites | Escrita |
|---|---|---|---|
| `product-images` | **leitura pública** (fotos do catálogo) | 5 MB; JPEG, PNG, WEBP | só a administradora, na pasta `<confeitaria_id>/...` da própria confeitaria |
| `marketing` | **privado** | 5 MB; PNG | leitura e escrita só da administradora, na pasta da própria confeitaria |

## 6. Primeiro administrador (procedimento seguro)

1. No Supabase, abra **Authentication → Users → Add user**, informe o e-mail e a senha da dona e marque **Auto Confirm**.
2. No **SQL Editor**, rode `select public.cadastrar_admin('email@da.dona', 'kika-cakes');`
3. Em **Authentication → Sign In / Providers**, desative **"Allow new users to sign up"**.

Usuários que não têm perfil podem fazer login, mas **não acessam nada** administrativo. A migração 005 já transforma a dona atual (`owner_user_id`) em perfil.

## 7. Exclusão de produtos (009)

- A administradora pode excluir produtos da própria confeitaria. Os registros de fotos saem junto (`on delete cascade`), e o app remove os arquivos do Storage em seguida.
- **Produtos com orçamentos (`leads`) ou pedidos (`order_items`) não podem ser excluídos.** As chaves estrangeiras não têm cascata, para preservar o histórico. O app explica e orienta a **despublicar**.
