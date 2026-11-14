# Estúdio de Marketing (Instagram): relatório

**Data:** 2026-11-12 · **Branch:** `dev` · **Commit base:** `d2ba37c`

## 1. Critério de aceite

✅ **Atendido no ambiente local (SQLite).** A confeiteira entra no painel, abre o Estúdio, seleciona um produto, gera a arte (Feed ou Story), edita título, preço, chamada e legenda, vê a prévia, baixa o PNG e salva no histórico, que continua disponível depois de reiniciar o servidor.

⚠️ **No Supabase, a geração, a prévia, a legenda e o download funcionam. O salvamento depende de rodar a migração `004_marketing.sql`**, que não pôde ser aplicada daqui (ver Limitações). Até lá, ao salvar, aparece uma mensagem explicando que a migração precisa ser rodada.

## 2. O que foi implementado

### Etapa 1: interface (`pages/marketing.py`)
- **Acesso:** só com a sessão administrativa válida, usando a mesma regra do painel: login, vínculo da sessão e, no Supabase, usuária válida e dona da confeitaria. Sem isso, a página mostra "Área restrita".
- **Controles:** produto, formato (**Feed 1080×1080** ou **Story 1080×1920**), template, título, preço e chamada editáveis, e foto (a do produto, uma enviada pela confeiteira ou nenhuma).
  - O enquadramento da foto pode ser "Preencher", que recorta as bordas, ou "Mostrar foto inteira".
  - A foto enviada é validada: JPG, PNG ou WEBP, até 10 MB. Arquivo corrompido ou falso é recusado.
- **Prévia** ao vivo, **Baixar PNG**, **Salvar no histórico** (com status) e lista de **Posts salvos**. Na lista, dá para editar a legenda e o status, ver a imagem e baixá-la.
- **Navegação:** o painel tem um link para o Estúdio e o Estúdio tem "Voltar ao painel", ambos sem perder o login.

### Etapa 2: geração automática (`services/post_generator.py`, `services/brand.py`)
- **3 templates:**
  - **Divulgação de produto:** fundo rosa algodão.
  - **Promoção especial:** fundo chocolate.
  - **Novidade do catálogo:** fundo rosa algodão com confetes só nas margens livres.
- **Identidade da marca:** paleta do brand book (`#FDE8EC`, `#F4A7BB`, `#E0628A`, `#5C3317`) e tipografia autorizada (Abril Fatface nos títulos e Quicksand nos textos, carregadas de `assets/fonts`).
  - **O logo original nunca é alterado:** só é redimensionado proporcionalmente. No fundo escuro, ele fica sobre uma placa clara. Há um teste que confere que o arquivo do logo continua idêntico.
- **Garantias de layout:**
  - Cada elemento tem uma **área própria, sem sobreposição**, dentro das **margens de segurança**.
  - No Story, nada fica nas faixas de 250 px do topo e da base, onde a interface do Instagram aparece.
  - O texto **quebra em linhas e diminui até caber**. Se nem no tamanho mínimo couber, é abreviado com "…" e a tela avisa.
  - A **proporção da foto é preservada**: recorte ou encaixe, sem distorção.
  - Se a foto precisar ser ampliada mais de 2×, a tela avisa que ela pode ficar borrada.
  - Os contrastes foram medidos: textos com no mínimo 7:1 e preço e chamada com no mínimo 3:1.

### Etapa 3: legendas (`services/caption_generator.py`, `templates/*.json`)
- **Tons:** amigável, promocional e elegante.
- **Conteúdo:** usa os dados do produto (nome, descrição, preço "a partir de" com o aviso de que o valor final é confirmado no orçamento), uma chamada para ação de acordo com o tom, o link da vitrine (opcional), o @ da Kika e até 10 hashtags relevantes (do template, da categoria e do produto).
- **Edição:** a legenda é **editável** antes de copiar ou salvar. O quadro de copiar quebra as linhas, então funciona no celular.

### Etapa 4: persistência (`services/marketing_store.py`, `supabase/migrations/004_marketing.sql`)
- **Tabela `marketing_posts`:** guarda produto (id e nome), template, formato, título, preço, chamada, tom, legenda, caminho da imagem, status (**Rascunho, Pronto, Publicado manualmente**), autora, `created_at` e `updated_at`.
- **Supabase Storage:** bucket **`marketing` privado**, só PNG, até 5 MB. O caminho de cada imagem é `<confeitaria_id>/<post_id>.png`.
- **RLS:**
  - Só a dona da confeitaria lê, cria, altera e apaga os próprios posts e imagens.
  - O visitante (`anon`) não tem acesso à tabela nem ao bucket.
- **Segurança:**
  - Se o registro falhar depois do upload, a imagem é apagada, para não ficar órfã.
  - O caminho da imagem é validado contra path traversal.
- **SQLite local:** tabela equivalente, com os PNGs em `data/marketing/`.

## 3. Arquivos alterados

**Criados:**
- `services/brand.py`
- `services/marketing_store.py`
- `supabase/migrations/004_marketing.sql`
- `docs/evidencias/marketing/` (este relatório, as capturas e as 11 artes)

**Alterados:**
- `pages/marketing.py`: Estúdio completo
- `services/post_generator.py`: motor de layout e templates
- `services/caption_generator.py`: tons, chamada e hashtags
- `templates/produto.json`, `promocao.json` e `novidade.json`: textos por tom
- `services/auth.py`: verificação de sessão reaproveitável e chave estável no hot-reload
- `pages/admin.py`: link para o Estúdio e teste do `pyarrow` em cache
- `.streamlit/config.toml`: upload de até 10 MB
- `requirements.txt`: `pillow<14`
- `tests/test_marketing.py`: 49 testes

## 4. Testes realizados

**Automatizados:** `193 passed, 10 skipped`. Os 10 pulados dependem de DLLs bloqueadas pelo Windows desta máquina (ver Limitações).

| Pedido | Testes |
|---|---|
| Post quadrado | 3 templates em 1080×1080: PNG válido, todos os elementos, sem sobreposição, dentro das margens |
| Story | 3 templates em 1080×1920, também fora das faixas da interface do Instagram |
| Imagens com diferentes proporções | 4 proporções (4:1, 1:4, 1:1, 1:32) × 2 modos: um círculo continua circular, sem distorção |
| Títulos longos | Fonte reduz e quebra em até 3 linhas, sem sobrepor. Título absurdo é abreviado e informado |
| Preços grandes | "R$ 12.345.678,90 / caixa com 6 unidades decoradas" cabe em feed e story |
| Produtos sem imagem | Espaço da foto com o logo, layout íntegro |
| Exportação PNG | Assinatura PNG, tamanho exato, botão de download na página |
| Salvamento e recuperação | Salvar, reabrir (nova instância), editar legenda e status, dados inválidos recusados, PNG falso recusado, path traversal bloqueado. Supabase com cliente simulado: bucket privado, caminho por confeitaria, limpeza da imagem se o registro falhar |
| Acesso não autorizado | Sem login: "Área restrita". Sessão forjada (`admin_ok` sem vínculo) também é bloqueada |
| Outros | 9 combinações de tom × template com chamada, preço e hashtags; tons diferentes entre si; contraste; logo inalterado; aviso de foto ampliada |

**No navegador** (instância local isolada):
- **Acesso:** sem login, aparece "Área restrita". Depois do login, o link do painel abre o Estúdio **logado**.
- **Fluxo completo:**
  1. Bem Casado + Story + Promoção especial.
  2. Tom Elegante, com a legenda editada à mão.
  3. A cópia reflete a edição.
  4. Salvo como Rascunho.
- **Recuperação:** **servidor reiniciado**, novo login, e o rascunho continua no histórico (horário de Brasília).
- **Tela estreita (500 px):** sem rolagem lateral.

**Artes geradas** (`artes/`): 11 cenários, incluindo título longo (3 linhas, sem abreviar), preço gigante (2 linhas), sem foto, foto larga inteira, foto alta recortada e foto alta inteira no Story.

## 5. Defeitos encontrados e corrigidos (3 ciclos)

| # | Defeito | Correção |
|---|---|---|
| 1 | Preço rosa sobre fundo rosa com contraste 2,85:1 (ilegível) | Preço em chocolate (contraste ≥ 7:1) |
| 2 | Título longo e preço grande saíam abreviados mesmo havendo espaço | Título com até 3 linhas no feed e preço com até 2 linhas |
| 3 | Foto pequena ampliada sem aviso (fica borrada) | Aviso com o fator de ampliação e sugestão de "Mostrar foto inteira" |
| 4 | **O link do painel abria o Estúdio deslogado** (o link Markdown cria uma sessão nova) | `st.page_link`, que mantém a sessão |
| 5 | Horário do histórico em UTC | Convertido para o horário de Brasília |
| 6 | Quadro de copiar a legenda com rolagem lateral no celular | Quebra de linhas |
| 7 | Upload anunciava "200MB per file" | Limite de 10 MB também no Streamlit |
| 8 | **Recarregar o código derrubava todas as sessões** (chave aleatória recriada a cada carregamento de `services/auth.py`) | Chave em cache por processo |
| 9 | Teste do painel intermitente (o `pyarrow` bloqueado era testado a cada atualização) | Resultado guardado em cache: 3/3 aprovações e o dobro da velocidade |

## 6. Limitações

1. **Migração 004 não aplicada no Supabase.** O `psycopg` está bloqueado pela política de Controle de Aplicativo do Windows desta máquina, então não consegui rodar a migração daqui. Rodar `supabase/migrations/004_marketing.sql` no SQL Editor. **O teste real do Storage e do RLS do marketing no Supabase continua pendente.**
2. **Fontes da marca não instaladas.** Abril Fatface e Quicksand (licença OFL) ainda não estão em `assets/fonts`. Enquanto isso, usamos Georgia Bold e Segoe UI no Windows, ou DejaVu no Linux, todas com acentos, e a página avisa. Coloque `AbrilFatface-Regular.ttf`, `Quicksand-Medium.ttf` e `Quicksand-Bold.ttf` em `assets/fonts`.
3. **Ilustrações SVG não viram foto.** Produtos que só têm ilustração usam o logo no espaço da foto ou uma foto enviada.
4. **Sem publicação automática** no Instagram, conforme pedido. A confeiteira baixa o PNG e copia a legenda.
5. **Teclado no modo celular emulado:** na automação do navegador, o texto não chegou aos campos no modo celular, por limitação da ferramenta. A tela estreita foi validada em 500 px.
6. **Bloqueio do Windows:** 10 testes ficam pulados nesta máquina, os de `pyarrow` (tabelas) e os de PostgreSQL. Eles rodam em máquinas sem a política.
