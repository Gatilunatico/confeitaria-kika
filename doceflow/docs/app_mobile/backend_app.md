# Backend do app da confeiteira (Flutter)

Este é o contrato do backend do DoceFlow para o app Android da confeiteira. Ele segue a arquitetura aprovada em 21/11/2026:

- **O app fala direto com o Supabase** para login, produtos, fotos, orçamentos, pedidos, clientes e indicadores. Usa o token da usuária, e o banco decide tudo pelo RLS.
- **Uma API pequena em Python** (`doceflow/api/`, FastAPI) cuida só do que precisa de Python no servidor: as artes e legendas do Estúdio de Marketing.
- **O painel web continua no ar** como reserva, usando as mesmas tabelas e regras.

> Situação em 21/11/2026: as migrações **012** e **013** foram **aplicadas em produção**, com autorização, e verificadas (evidências em `docs/evidencias/app_mobile/migracoes_012_013.md`). A API ainda **não está publicada** (veja "Pendências").

## 1. Segurança: o que vale para tudo

| Regra | Como é garantida |
|---|---|
| Só a dona (perfil ativo) acessa dados administrativos | RLS com `is_store_admin()` em todas as tabelas. A API confere o token no Supabase Auth a cada pedido e procura o perfil ativo |
| Visitante não lê pedidos nem orçamentos | `leads`, `orders`, `order_items`, `order_history`, `clientes_resumo` e `admin_devices` não têm permissão para `anon`. As funções novas também não (teste `test_new_functions_not_executable_by_visitor`) |
| Uma confeitaria não vê a outra | RLS por `confeitaria_id`. As funções novas usam o perfil de quem chama, e o app nunca informa a confeitaria |
| Nenhuma chave privilegiada no app ou na API | O app e a API usam só a chave **publishable** e o token da usuária. A `service_role` não aparece em nenhum arquivo (teste `test_api_code_never_mentions_service_role_keys`) |
| Valores registrados não são adulterados | Permissão por coluna: em `orders`, só `status`, `valor_final`, `data_entrega` e `observacoes_internas` são editáveis. O histórico é gravado por gatilho |
| Sem duplicidade | Pedido por orçamento: índice único `orders(lead_id)`. Post de marketing: `Idempotency-Key`. Celular: `token` único. Pedido do site: `fingerprint` (já existia) |

**Sessão no app:** guarde a sessão do `supabase_flutter` no `flutter_secure_storage` e deixe a renovação automática ligada. Para chamar a API, envie o `access_token` atual da sessão.

## 2. Operações diretas no Supabase (`supabase_flutter`)

### 2.1 Login e perfil

| Ação | Chamada |
|---|---|
| Entrar | `auth.signInWithPassword(email, password)` |
| Confirmar que é dona | `from('admin_profiles').select('confeitaria_id,papel').eq('ativo', true).maybeSingle()`. Se vier vazio, a conta não administra nenhuma loja: mostre "sem acesso" e faça `signOut` |
| Dados da loja | `from('confeitarias').select('id,slug,nome,whatsapp').eq('id', confeitariaId).single()` |
| Esqueci a senha | `auth.resetPasswordForEmail(email)`. O e-mail traz o link do painel e um código de 6 dígitos. No app: `auth.verifyOTP(type: recovery, email, token)` e depois `auth.updateUser(password)` |
| Sair | `auth.signOut()` e apagar o dispositivo (2.8) |

### 2.2 Indicadores (migração 012)

```dart
rpc('painel_indicadores', params: {'p_inicio': '2026-11-01', 'p_fim': '2026-11-30'})  // datas opcionais
```

A resposta é um JSON:
- `orcamentos`: `total`, `novos`, `em_atendimento`, `orcamentos_enviados`, `vendas_concluidas`, `perdidos` e `taxa_conversao` (de 0 a 1, ou `null` sem orçamentos);
- `pedidos`: `total`, um contador por status, `valor_registrado` (soma dos estimados dos pedidos não cancelados, que **não é receita**), `sem_valor_estimado` e `valor_final_combinado`;
- `entregas_proximos_7_dias`: entregas dos próximos 7 dias, sem contar entregues e cancelados.

O período usa a data de registro no horário de Brasília. As definições são as mesmas do painel web.

### 2.3 Produtos

| Ação | Chamada | Observações |
|---|---|---|
| Listar | `from('produtos').select().eq('confeitaria_id', id).order('ordem').range(0, 49)` | A dona vê também os não publicados |
| Criar | `from('produtos').insert({...}).select('id,slug')` | `slug` é opcional: o banco gera a partir do nome, sem acento e sem repetir (012) |
| Editar | `update({...}).eq('id', id)` | Colunas editáveis: `nome`, `categoria`, `descricao`, `unidade`, `preco`, `tipo_preco`, `disponivel`, `publicado`, `imagem`, `qtd_min`, `qtd_max`, `ordem`, `destaque`, `prazo_producao_dias`. `slug` e `confeitaria_id` não mudam |
| Excluir | `delete().eq('id', id)` | Recusado (código `23503`) se houver orçamento ou pedido. Nesse caso, ofereça **despublicar** |

Limites (CHECK no banco):
- `nome`: 2 a 120 caracteres;
- `categoria`: 2 a 60;
- `descricao`: até 500;
- `preco`: 0 ou mais;
- `tipo_preco`: `a_partir_de`, `estimado` ou `sob_consulta`;
- `qtd_max` ≥ `qtd_min` ≥ 1;
- `prazo_producao_dias`: de 0 a 90.

### 2.4 Fotos dos produtos

1. Antes de enviar, comprima a foto e **remova os metadados (EXIF/GPS)** com `flutter_image_compress`: lado maior até 1600 px, JPEG ou WEBP, no máximo 5 MB.
2. Gere um `image_id` (UUID) e envie para `storage.from('product-images').uploadBinary('<confeitaria_id>/<produto_id>/<image_id>.jpg', bytes)`.
3. Registre a foto: `from('product_images').insert({id: image_id, confeitaria_id, produto_id, storage_path, alt_text, principal, ordem})`.
   - **Se o registro falhar, apague o arquivo enviado.**
   - O banco recusa caminho fora da pasta da loja e mais de 10 fotos por produto.
4. Para trocar a foto principal, use `rpc('definir_foto_principal', params: {'p_image_id': id})`.
5. Para apagar, primeiro `delete()` em `product_images`, depois `storage.remove([path])`.

### 2.5 Orçamentos (`leads`)

| Ação | Chamada |
|---|---|
| Listar | `from('leads').select('id,protocolo,created_at,status,cliente_nome,cliente_whatsapp,produto_nome,quantidade,unidade,data_desejada,modalidade,observacoes,origem').order('created_at', ascending: false).range(0, 29)` |
| Mudar status | `update({'status': 'Em atendimento'}).eq('id', id)`. Status aceitos: `Novo`, `Em atendimento`, `Orçamento enviado`, `Venda concluída`, `Perdido` |
| **Converter em pedido** (012) | `rpc('converter_orcamento_em_pedido', params: {'p_lead_id': id, 'p_data_entrega': null, 'p_endereco_entrega': '', 'p_valor_final': 350, 'p_observacoes_internas': ''})` |

O que a conversão faz:
- Cria o pedido já **Confirmado**, com o item do orçamento: preço atual do produto e nome registrado no orçamento.
- Marca o orçamento como **Venda concluída** e grava no histórico quem converteu.
- Repetir a chamada devolve o mesmo pedido (`criado = false`).
- `p_endereco_entrega` é obrigatório quando o orçamento é de **Entrega**.
- Se `p_data_entrega` vier vazio, vale a data desejada do orçamento. Ela não pode estar no passado.
- Orçamento **Perdido** não é convertido.

### 2.6 Pedidos

| Ação | Chamada |
|---|---|
| Listar | `from('orders').select('*, order_items(produto_nome,unidade,quantidade,preco_unitario,tipo_preco,subtotal)').order('created_at', ascending: false).range(0, 29)` |
| Filtrar | `.eq('status', 'Confirmado')`, `.gte('data_entrega', '2026-12-01')`, `.ilike('cliente_nome', '%ana%')` |
| Atualizar | `update({'status', 'valor_final', 'data_entrega', 'observacoes_internas'}).eq('id', id)`. Qualquer outra coluna é recusada pelo banco |
| Histórico | `from('order_history').select('campo,valor_anterior,valor_novo,alterado_por,alterado_em').eq('order_id', id).order('alterado_em')` |
| Tempo real | `channel('pedidos').onPostgresChanges(event: insert, table: 'orders', ...)`. Também vale para `leads`. O Realtime respeita o RLS (012) |

O fluxo de status é Aguardando confirmação → Confirmado → Em produção → Pronto → Entregue, com Cancelado a qualquer momento. Pedidos não são apagados pelo app: para desistir, use **Cancelado**.

### 2.7 Clientes (012)

```dart
from('clientes_resumo').select().order('ultimo_contato', ascending: false).range(0, 29)
```

Cada linha traz:
- `cliente_whatsapp`;
- `cliente_nome` (o do contato mais recente);
- `total_pedidos`, `total_orcamentos` e `pedidos_em_andamento`;
- `valor_pedidos` (valor final, ou o estimado, dos pedidos não cancelados);
- `primeiro_contato` e `ultimo_contato`.

O histórico de um cliente são os pedidos e orçamentos com `.eq('cliente_whatsapp', numero)`.

### 2.8 Celular para notificações (013)

| Ação | Chamada |
|---|---|
| Registrar, depois do login e quando o FCM trocar o token | `rpc('registrar_dispositivo', params: {'p_token': fcmToken, 'p_plataforma': 'android'})` |
| Remover, ao sair | `from('admin_devices').delete().eq('token', fcmToken)` |

O mesmo celular registrado por outra conta passa para a conta que entrou por último. Cada pessoa só vê os próprios celulares.

### 2.9 Paginação

Use sempre `.range(inicio, fim)`, em páginas de 20 a 50 itens. Para mostrar o total, use `select('...', count: CountOption.exact)`. O banco limita cada resposta ao `max_rows` do projeto (padrão do Supabase: 1000).

### 2.10 Erros do banco → mensagens no app

| Código ou texto | Mensagem sugerida |
|---|---|
| `42501` / `sem_permissao` / `orcamento_nao_encontrado` | "Sem permissão ou item não encontrado. Entre novamente." |
| `23503` ao excluir produto | "Este produto tem orçamentos ou pedidos. Despublique em vez de excluir." |
| `23505` | "Este registro já existe." |
| `23514` / `22023` + motivo (`data_invalida`, `endereco_obrigatorio`, `valor_invalido`, `orcamento_perdido`, `periodo_invalido`, `token_invalido`) | Mensagem do motivo, campo a campo |
| `limite_fotos` | "Cada produto pode ter no máximo 10 fotos." |
| Sem rede ou tempo esgotado | "Sem conexão. Tente de novo." **Não repita automaticamente** operações que gravam |

## 3. API de marketing (`doceflow/api`)

**Base:** a definir quando a API for publicada (veja "Pendências").

**Cabeçalho em todas as rotas, menos `/v1/saude`:** `Authorization: Bearer <access_token da sessão do Supabase>`.

A documentação interativa fica em `/v1/docs` e o esquema OpenAPI em `/v1/openapi.json`.

| Método e rota | O que faz | Respostas |
|---|---|---|
| `GET /v1/saude` | Verifica se a API está no ar (sem login) | 200 `{status, versao}` |
| `GET /v1/eu` | Quem está logado e qual confeitaria administra | 200, 401, 403 |
| `GET /v1/marketing/opcoes` | Templates, formatos, tons, ajustes de foto, status e limites de texto | 200 |
| `POST /v1/marketing/previa` | Gera a arte (PNG em base64) e a legenda **sem salvar** | 200, 404 (produto de outra loja ou inexistente), 422, 429 |
| `POST /v1/marketing/posts` | Gera e salva o post (imagem no bucket privado `marketing` e registro em `marketing_posts`). **Exige `Idempotency-Key`** (8 a 128 caracteres: letras, números, `-` e `_`) | 201 criado; 200 se a chave já foi usada (devolve o mesmo post, sem duplicar) |
| `GET /v1/marketing/posts?pagina=1&limite=20&status=` | Lista os posts, do mais novo para o mais antigo | 200 `{itens, pagina, limite, total}`. `limite` de 1 a 100 |
| `PATCH /v1/marketing/posts/{id}` | Muda o status: `Rascunho`, `Pronto` ou `Publicado manualmente` | 200, 404, 422 |
| `GET /v1/marketing/posts/{id}/imagem` | Baixa o PNG do post | 200 `image/png` (`Cache-Control: private, no-store`), 404 |
| `GET /v1/instagram/status` | Informa que a publicação automática **ainda não está ativa** e qual é a alternativa | 200 |

**Corpo da prévia e do post:**
- `produto_id` (obrigatório);
- `template`: `produto`, `promocao` ou `novidade`;
- `formato`: `feed` ou `story`;
- `tom`: `amigavel`, `promocional` ou `elegante`;
- `titulo`, `preco_texto`, `cta`: opcionais. Vazios usam o texto sugerido;
- `extra`: frase extra na legenda;
- `usar_foto`: usa a foto principal do produto;
- `ajuste_foto`: `cover` ou `contain`;
- só no post: `legenda` (a editada no app) e `status`.

**Avisos na resposta:**
- `sem_foto`: a arte saiu com o logo no lugar da foto;
- `foto_pequena`: a foto foi ampliada mais de 2 vezes;
- `texto_abreviado:<campo>`: o texto não coube e foi cortado com "…".

**Erros:** sempre no formato `{"erro": {"codigo", "mensagem"}}`. Erros de validação trazem também `campos`, com o campo e o problema, mas **nunca o valor enviado**. Os códigos são:

| Status | Códigos |
|---|---|
| 401 | `token_ausente`, `token_invalido` |
| 403 | `sem_permissao` |
| 404 | `produto_nao_encontrado`, `post_nao_encontrado` |
| 413 | `corpo_muito_grande` (pedido acima de 64 KB) |
| 422 | `dados_invalidos` |
| 429 | `limite_excedido` (20 artes por minuto por usuária, com `Retry-After`) |
| 500 | `erro_interno` (sem detalhes) |
| 503 | `servico_indisponivel` |

**Como rodar localmente:**

```powershell
cd doceflow
.venv\Scripts\pip install -r requirements-api.txt
.venv\Scripts\uvicorn api.main:app --port 8000
```

A API usa as variáveis `SUPABASE_URL`, `SUPABASE_KEY` (publishable), `STORE_SLUG` e `PUBLIC_APP_URL`, as mesmas do painel.

## 4. Testes

| Arquivo | O que cobre | Resultado (21/11/2026) |
|---|---|---|
| `tests/test_app_mobile_postgres.py` | Migrações 012 e 013 num PostgreSQL 16 real, rodadas duas vezes (idempotência): indicadores, clientes, conversão, slug automático, dispositivos, acesso negado ao visitante, à outra loja e ao usuário sem perfil | 45 passando |
| `tests/test_api_app.py` | API: token ausente, malformado, inválido ou sem perfil; outra loja; prévia; idempotência; paginação; status; download; limite de uso; corpo grande; erro sem detalhes | 39 passando |

## 5. Pendências

1. ~~Aplicar as migrações 012 e 013 em produção~~: aplicadas em 21/11/2026.
2. **Publicar a API.** Escolher onde hospedar (Render, Fly.io ou Cloud Run, no plano gratuito), configurar HTTPS e as variáveis, e informar o endereço ao app.
3. **Push de pedido novo:** criar a Edge Function e o Database Webhook (insert em `orders` e `leads`) que leem `admin_devices` e enviam pelo FCM. Isso depende do projeto Firebase da confeiteira.
4. **Instagram:** a publicação automática segue adiada até a conversa com a confeiteira. A API já informa isso em `/v1/instagram/status`.
5. **Remetente provisório do e-mail:** trocar o SMTP para o Gmail da confeiteira quando ela criar a senha de app (`docs/implantacao/README_IMPLANTACAO.md`, seção 8).
