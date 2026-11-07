# Etapa 02: vitrine digital e solicitação de orçamento

**Data:** 2026-11-07 · **Branch:** `dev` · **Commit base:** `f9a90e2`

## 1. O que foi implementado

| Requisito | Implementação |
|---|---|
| 1. Cabeçalho com marca e CTA | Logo, nome da confeitaria (`STORE_NAME`), frase e botão "Ver catálogo e pedir orçamento", que leva até `#catalogo` |
| 2. Catálogo | 6 produtos com ilustração, nome, descrição, categoria (selo) e preço. Filtro por categoria (Todos, Bolos, Cupcakes, Doces, Kits) |
| 3. Seleção de produto | Botão "Solicitar orçamento" em cada card abre o formulário já com o produto escolhido |
| 4. Formulário | Nome, WhatsApp com DDD, produto, quantidade (na unidade do produto), data, retirada ou entrega, observações e consentimento |
| 5. Validação | Mensagens por campo, reunidas numa lista "Confira os campos abaixo" |
| 6. Confirmação visual | Cartão de sucesso com protocolo (`DF-AAMMDD-XXXX`), resumo do pedido e aviso de que o envio não confirma pedido nem preço |
| 7. Celular | Colunas empilham, botões ocupam a largura toda e o formulário abre em diálogo. Sem rolagem horizontal em 375 px |
| 8. Erros e indisponibilidade | Produto indisponível mostra botão desativado e um aviso. Se não houver nenhum produto disponível, o formulário avisa |

### Regras de negócio atendidas

- **Preço nunca é final.** Os rótulos dizem "A partir de", "Cerca de... (estimado)" ou "Preço sob consulta". Há um aviso fixo no catálogo e outro no formulário, e a confirmação diz que o envio **não confirma** pedido nem preço.
- **Sem datas passadas.** O seletor bloqueia datas anteriores a hoje, e o servidor valida de novo. Também há um limite de 12 meses à frente.
- **Dados mínimos.** Não são coletados endereço, CPF nem e-mail. O consentimento informa que nome e WhatsApp servem apenas para responder o orçamento.
- **Pronto para o banco.** `QuoteRequest.to_record()` já gera o registro no formato da futura tabela `orcamentos`, e o armazenamento (`InMemoryQuoteStore.add`) pode ser trocado pelo repositório Supabase sem mexer na interface.

### Outros ajustes

- O status do banco saiu da vitrine pública e passou para o painel admin, porque é informação interna.
- O menu lateral foi escondido (`showSidebarNavigation = false`) para o visitante não ver o link do admin. O painel continua em `/admin`.
- O fundo dos campos passou de `#F4A7BB` para `#FFF6F8`, porque o texto ficava com pouco contraste no rosa forte.

## 2. Arquivos alterados

**Criados**
- `services/catalog.py`: produtos, categorias e rótulos de preço
- `services/quotes.py`: validação, normalização de telefone, protocolo, deduplicação e armazenamento temporário
- `assets/images/produtos/*.svg`: 6 ilustrações na paleta da marca, que fazem as vezes das fotos
- `tests/test_etapa02.py`: 36 testes
- `docs/evidencias/etapa_02.md` e `docs/evidencias/img/*`

**Alterados**
- `app.py`: vitrine completa (cabeçalho, catálogo, diálogo de orçamento e confirmação)
- `config.py` e `.env.example`: nova variável `STORE_NAME`
- `pages/admin.py`: recebeu o status do banco
- `.streamlit/config.toml`: menu lateral oculto, toolbar mínima e fundo dos campos mais claro
- `tests/test_etapa01.py`: o título esperado passou a ser "Kika Cakes", porque a vitrine agora mostra o nome da confeitaria

## 3. Comandos executados

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m streamlit run app.py --server.headless true --server.address localhost --server.port 8501
msedge --headless --window-size=1280,1800 --screenshot=docs/evidencias/img/etapa02_desktop.png http://localhost:8501
```

Também testei manualmente no navegador do app, em 375 × 812 (celular) e em desktop.

## 4. Resultados dos testes

**Automatizados:** `44 passed in 3.03s` (8 da etapa 01 e 36 da etapa 02)

| Tema pedido | Testes |
|---|---|
| Produtos disponíveis | catálogo tem itens disponíveis e indisponíveis. Toda imagem existe. Nenhum preço parece final. Produto indisponível ou inexistente é rejeitado. O filtro "Bolos" mostra 1 botão ativo |
| Campos vazios | formulário vazio aponta os 7 campos obrigatórios. Nome só com espaços é rejeitado. Na interface, envio vazio mostra os erros |
| Telefones inválidos | 4 formatos válidos aceitos (celular, +55, 0 + DDD, fixo) e 9 inválidos rejeitados (sem DDD, curto, longo, DDD com 0, celular sem 9, fixo começando com 9, dígitos repetidos, letras). Na interface, telefone `1234` mostra erro |
| Datas inválidas | data passada, data ausente e data além de 12 meses são rejeitadas. Hoje é aceito |
| Submissões duplicadas | o mesmo pedido com o telefone em outro formato é bloqueado com o protocolo original. Data diferente não conta como duplicata. Na interface, reenviar mostra "Você já enviou esta mesma solicitação" e mantém 1 registro |
| Outros | quantidade fora do intervalo do produto, observações com mais de 500 caracteres, consentimento obrigatório, registro com todos os campos |

**Manual (navegador, celular 375 × 812):**
1. O cabeçalho e o CTA aparecem sem corte, e não há rolagem horizontal (`scrollWidth = 375`, 0 elementos vazando).
2. O card indisponível mostra o botão desativado e o aviso.
3. "Solicitar orçamento" em Cupcakes abre o diálogo já com o produto selecionado.
4. Enviar vazio lista nome, WhatsApp, data e consentimento.
5. Preenchido corretamente, o envio fecha o diálogo e mostra a confirmação com o protocolo `DF-261107-E7E6`.

### Capturas de tela

| Tela | Arquivo |
|---|---|
| Desktop, catálogo | `img/etapa02_desktop.png` |
| Celular, cabeçalho e CTA | `img/etapa02_celular_1_cabecalho.jpg` |
| Celular, card disponível e indisponível | `img/etapa02_celular_2_catalogo_indisponivel.jpg` |
| Celular, erros de validação | `img/etapa02_celular_3_erros_validacao.jpg` |
| Celular, formulário preenchido | `img/etapa02_celular_4_formulario_preenchido.jpg` |
| Celular, confirmação com protocolo | `img/etapa02_celular_5_confirmacao.jpg` |

As capturas de celular vêm do navegador do app em 375 px. A captura de celular feita com o Edge headless foi descartada, porque ele não reduz a janela abaixo de uns 500 px e cortava a página, o que não acontece no app.

## 5. Pendências e o que depende de integração

| Item | Situação |
|---|---|
| **Persistência das solicitações** | Ficam só na sessão do navegador (`InMemoryQuoteStore`) e se perdem ao recarregar a página. **Depende da etapa 03 (Supabase)**: tabela `orcamentos` com RLS, mais um repositório que implemente `add` |
| **Duplicidade entre sessões** | Hoje vale só dentro da mesma sessão. No banco, deve virar uma restrição única em `fingerprint` (ou uma janela de tempo) |
| **Catálogo** | Os 6 produtos e os preços são **dados de exemplo**. A Kika precisa confirmar nomes, preços e unidades. Depois disso, ler da tabela `produtos` no Supabase |
| **Fotos reais** | Ilustrações SVG fazem as vezes das fotos. Faltam as fotos dos produtos |
| **Aviso à confeitaria** | O botão "Avisar a confeitaria no WhatsApp" só aparece com `WHATSAPP_NUMBER` configurado, e o número real ainda não foi informado |
| **Painel admin** | Ainda não lista as solicitações, porque depende do banco |
| **Política de privacidade** | O consentimento existe, mas falta a página de política (LGPD) com prazo de retenção |

**Erros pendentes:** nenhum erro interrompe a navegação. Não há falhas nos testes.
