# Etapa 05: relatório de QA independente

**Data:** 2026-11-07 · **Branch:** `dev` · **Ambientes:**
- Vitrine ligada ao Supabase real em `localhost:8501`.
- Instância isolada de QA (SQLite) em `localhost:8502`.
- Navegador automatizado em tela de celular (375 × 812).

> Revisão feita sob prazo curto, a pedido da equipe: 2 ciclos de correção e reteste. O que não foi testado está declarado na seção 4.

## 1. Resultado

| # | Verificação | Resultado | Evidência |
|---|---|---|---|
| 1 | Inicialização da aplicação | ✅ Aprovado | Servidor sobe (`/_stcore/health` = ok) nas duas portas |
| 2 | Carregamento de produtos | ✅ Aprovado | Os **27 produtos oficiais** dos 3 PDFs aparecem, com 28 imagens carregadas (contando o logo) e nenhuma quebrada. As categorias seguem a ordem do cardápio. Preço, unidade e mínimo de cada item foram conferidos com os PDFs em 27 testes. Captura 01 e 02 |
| 3 | Seleção e envio de orçamento | ✅ Aprovado (após correção QA-01) | Bem Casado e Docinhos Premium enviados no celular. Protocolos `DF-261107-0A76D4` e `DF-261107-BCB5FB`. Captura 05 |
| 4 | Campos obrigatórios | ✅ Aprovado (após correção QA-02) | Telefone sem DDD, quantidade abaixo do mínimo (10 < 25), data e consentimento foram apontados. Captura 03 |
| 5 | Persistência e recuperação | ✅ Aprovado | O lead continua no banco após reiniciar o servidor (etapas 03 e 04 e pytest). No Supabase: criar, ler e bloquear a leitura pública foi verificado com a chave publishable |
| 6 | Link do WhatsApp | ✅ Aprovado | `wa.me/5511979855065` (número oficial do cardápio), com `&`, `#`, acentos e quebras de linha codificados. A mensagem corresponde ao registro gravado, e nenhum texto diz "foi enviada" |
| 7 | Envio duplicado | ✅ Aprovado (pytest) | A repetição devolve o mesmo protocolo, no SQLite e no PostgreSQL real |
| 8 | Autenticação administrativa | ✅ Aprovado no modo local · ⚠️ **não testado no Supabase** | Senha local e bloqueio após 5 tentativas (pytest). No modo Supabase falta criar a usuária dona |
| 9 | Bloqueio de acesso não autorizado | ✅ Aprovado | Sem login não aparece nenhum indicador, tabela ou nome. Visitante sem SELECT, UPDATE ou DELETE em leads. Dona de outra confeitaria vê 0 leads (PostgreSQL real e Supabase) |
| 10 | Status comerciais | ✅ Aprovado | Os 5 status persistem, e a venda exige confirmação (pytest + Supabase com rollback) |
| 11 | Cadastro e edição de produtos | ✅ Aprovado | Pela tela do painel (pytest), e a mudança aparece na vitrine. RLS de escrita só na própria confeitaria |
| 12 | Falhas no banco | ✅ Aprovado (pytest) · ⚠️ não reproduzido no navegador | Falha simulada mostra a mensagem de erro, sem sucesso, sem link e sem lead. Banco não configurado mostra "catálogo indisponível" |
| 13 | Telas móveis | ✅ Aprovado (após correção QA-01) | 375 px sem rolagem horizontal (`scrollWidth = 375`) |
| 14 | Segredos expostos | ✅ Aprovado | Varredura de **todo o histórico do Git**: 0 ocorrências de `sb_secret_`, de URL do banco, da senha antiga, de `ADMIN_PASSWORD` preenchido e de JWT. Nenhum `.env` ou `secrets.toml` versionado. A senha do banco que vazou no chat foi **trocada** |

**Testes automatizados:** `179 passed`. São 143 das etapas anteriores e 36 novos em `tests/test_etapa05.py`, que cobrem o catálogo oficial e as regressões.

## 2. Defeitos encontrados

| ID | Gravidade | Defeito | Correção | Reteste |
|---|---|---|---|---|
| QA-01 | **Alta** (celular) | Depois de enviar, a página continuava rolada no catálogo. A mensagem de sucesso e o botão do WhatsApp ficavam **fora da tela**, e a cliente podia não perceber que o pedido foi registrado (captura 04) | A confirmação e o botão do WhatsApp aparecem **dentro do diálogo** logo após gravar, com o botão "Fechar". Escolher outro produto abre sempre um formulário novo | ✅ Navegador (captura 05) + 3 testes |
| QA-02 | Baixa | A mensagem de erro dizia "Confira os campos **abaixo**", mas os campos ficam acima | O texto agora é "Corrija estes campos do formulário" | ✅ Teste |
| QA-03 | Baixa | As categorias apareciam em ordem alfabética, e não na ordem do cardápio | Agora seguem a ordem dos produtos | ✅ Navegador + teste |
| QA-04 | Média | Os produtos fictícios das etapas anteriores apareciam para clientes | Substituídos pelos 27 produtos reais (migração `003_catalogo_real.sql`, **aplicada no Supabase**) | ✅ Navegador |

## 3. Bloqueios e riscos em aberto (não resolvidos)

| Item | Gravidade | Situação |
|---|---|---|
| Painel no Supabase sem usuária dona | **Alta para o uso real** | Ainda não existe usuário em Authentication. Sem ele, o painel de produção não abre. Precisa ser criado no Supabase e vinculado com `owner_user_id` |
| Envio em massa de leads | Média | A função `criar_lead` é pública por natureza. Falta captcha ou limite por IP |
| Bloqueio de login por sessão | Média | As 5 tentativas são contadas por sessão do navegador. Uma sessão nova recomeça a contagem. No Supabase Auth valem também os limites do próprio Supabase |
| Tabela `leads_antiga` no Supabase | Baixa | Vazia, com RLS ativa. Pode ser apagada |
| Banco local `data/doceflow_dev.db` | Baixa | Se existir de testes antigos, ainda tem os produtos fictícios. Apagar o arquivo recria com o catálogo real |
| Preço das mini trufas simples | Informativo | O cardápio dá o preço por cento. A vitrine mostra "a partir de R$ 1,60 / unidade", e a descrição informa "R$ 160,00 o cento" |

## 4. Não testado nesta rodada

- Login e uso do painel **com o Supabase real**, por falta da usuária dona.
- Falha de banco **reproduzida no navegador**. Coberta só por pytest.
- O painel não foi refeito no navegador com o catálogo novo, por causa do prazo. Os fluxos do painel estão cobertos por pytest e foram validados no navegador na etapa 04.
- Navegadores além do Chromium (Safari/iOS e Firefox).

## 5. Fluxo ponta a ponta catálogo → formulário → banco → WhatsApp → painel

- **No modo local (SQLite):** ✅ funciona de ponta a ponta, conferido no navegador e nos testes.
- **No Supabase real:** ✅ catálogo → formulário → banco → WhatsApp. ⚠️ O **painel** depende da usuária dona.

## Capturas (`capturas/`)

01 catálogo no celular · 02 doces finos com fotos reais · 03 validação · 04 QA-01 antes · 05 QA-01 depois · 06 indicadores do painel
