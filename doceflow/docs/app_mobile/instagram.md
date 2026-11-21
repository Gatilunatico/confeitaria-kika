# Marketing e Instagram: o que funciona e o que depende da Meta

Situação em 21/11/2026.

| Parte | Situação | Depende de |
|---|---|---|
| **Estúdio de criação no app** (produto e foto reais, Feed 1080×1080 e Story 1080×1920, identidade e logo, títulos, legenda, hashtags, prévia, rascunhos, histórico e exportação PNG) | ✅ **Funciona e está testado.** Precisa da API de marketing publicada (`API_URL` no build do app) | Publicar a API (`doceflow/api`) num servidor com HTTPS |
| **Fila de publicação** (agendar, cancelar, tentar de novo, status, histórico, idempotência e concorrência) | ✅ **Funciona e está testada** no Postgres e no Supabase local. A migração **014** ainda **não está em produção** | Autorização para aplicar a 014 |
| **Serviço do Instagram** (OAuth oficial, token no Vault, publicador com tentativas) | ✅ **Código pronto e testado contra uma Meta SIMULADA.** **Nada foi publicado no Instagram de verdade** | Itens da Meta abaixo + hospedar o serviço |
| **Publicação real no Instagram** | ⏳ **Não ativada** | App da Meta, conta profissional e, para uso fora do modo de desenvolvimento, **revisão da Meta** |

## Como funciona (só APIs oficiais)

1. **Conectar.**
   - No app: Marketing → Instagram → "Conectar Instagram".
   - O app pede ao **serviço do Instagram** o link da página **oficial** de autorização (`www.instagram.com/oauth/authorize`).
   - O link usa um `state` aleatório, de **uso único**, que vale **10 minutos** e fica no banco só como hash.
2. **Autorizar.**
   - A dona autoriza no site da Meta, e a Meta devolve um código ao serviço (`/v1/instagram/callback`).
   - O serviço troca esse código pelo token de 60 dias. Para isso usa o **segredo do app**, que existe só no servidor.
   - O serviço confere se a conta é **profissional** (Empresa ou Criador) e guarda o token **no Supabase Vault**.
   - O app nunca vê o token: a coluna `token_vault_id` não pode ser lida, e as funções que leem o token não podem ser executadas por `anon` nem por `authenticated`.
3. **Agendar.**
   - No post, "Publicar no Instagram", "Agora" ou "Agendar".
   - O app chama `agendar_publicacao_instagram` com uma **chave de idempotência**. Repetir o pedido devolve o mesmo agendamento.
   - Só pode existir **um agendamento ativo por post**.
4. **Publicar.**
   - O **publicador** (`python -m instagram_service.worker`) reserva os itens com `FOR UPDATE SKIP LOCKED`, então duas cópias nunca pegam o mesmo item.
   - Ele converte o PNG em JPEG (a Meta só aceita JPEG) e gera um link assinado de 1 hora no bucket privado `instagram-media`.
   - Depois cria o *container* na Graph API, espera `FINISHED` e chama `media_publish`.
5. **Status.**
   - "Publicado" só existe com o **id da mídia devolvido pela Meta**, garantido por um CHECK no banco.
   - Erros temporários (rede, instabilidade ou limite da Meta) voltam para a fila com espera crescente, até 3 tentativas.
   - Erros permanentes viram "Falhou", com a mensagem.
   - Token vencido ou revogado vira "Falhou", e a conta passa a "erro" (é preciso reconectar).
   - Se o serviço cair **depois** de pedir a publicação, ele pergunta à Meta antes de repetir. Sem confirmação, o status vira **"Conferir no Instagram"**: nunca publica duas vezes e nunca finge que publicou.
6. **Renovação.** O publicador renova o token quando faltam menos de 10 dias para vencer.

## O que a equipe precisa configurar (fora do código)

### Na Meta (developers.facebook.com)

1. Criar um **app do tipo Empresa** e adicionar o produto **Instagram** → "API com login do Instagram".
2. Em **Business login settings**, cadastrar a URL de redirecionamento: `https://<servico-do-instagram>/v1/instagram/callback`.
3. Pedir as permissões `instagram_business_basic` e `instagram_business_content_publish`.
4. **Modo de desenvolvimento:** só funciona com contas adicionadas como **testadoras** do app. Já dá para testar com a conta da Kika, depois de ela aceitar o convite.
5. **Para uso real (modo Live):** a Meta exige
   - **revisão do app**, com vídeo do fluxo, descrição do uso e política de privacidade publicada;
   - provavelmente a **verificação da empresa**.

   **O prazo e a aprovação dependem da Meta.**
6. A conta do Instagram da confeitaria precisa ser **profissional** (Empresa ou Criador de conteúdo). A troca é feita nas configurações do app do Instagram.

### No servidor do serviço do Instagram

| Variável | O que é |
|---|---|
| `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET` | Do app da Meta. **O segredo só existe aqui** |
| `INSTAGRAM_REDIRECT_URI` | A mesma URL cadastrada na Meta (precisa ser https) |
| `INSTAGRAM_GRAPH_VERSION` | Padrão `v23.0`. Confira a versão vigente no painel da Meta |
| `SUPABASE_DB_URL` | Conexão do servidor com o banco (pooler de transações) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Storage (ler o PNG e gravar o JPEG). **Só no servidor, nunca no app** |
| `SUPABASE_KEY`, `STORE_SLUG` | Chave publishable, para validar o login da dona em `/conexao` |

Processos:
- `uvicorn instagram_service.app:app`: a conexão (HTTPS obrigatório);
- `python -m instagram_service.worker`: o publicador, contínuo, ou `--once` num agendador a cada minuto.

### No app (build)

No `config/local.json`, preencha `API_URL` (API de marketing) e `INSTAGRAM_SERVICE_URL` (serviço do Instagram). Se faltarem, o app explica que o estúdio ou a conexão ainda não foram configurados.

## Testes (21/11/2026)

| Suíte | Resultado |
|---|---|
| `tests/test_instagram_postgres.py`: migração 014 num Postgres real | 60 passando. Cobre o token no Vault, permissões, idempotência, um agendamento ativo por post, as funções do serviço bloqueadas para o app, o state de uso único, o CHECK de "publicado", as tentativas, a retomada de item travado e a **concorrência real entre 2 publicadores** |
| `tests/test_instagram_service.py`: publicador e OAuth com **Meta simulada** | 20 passando. Cobre Feed e Story, tentativas, limite diário, imagem em processamento, **queda de rede depois de publicar sem duplicar**, "verificar", token vencido, renovação, fluxo OAuth completo, conta pessoal recusada e token nunca na URL |
| `tests/test_api_app.py`: API de marketing | 44 passando. Inclui foto escolhida, hashtags separadas, edição e edição bloqueada quando agendado |
| `tests_e2e/test_instagram_e2e.py`: **Supabase local** (Auth, Storage, Vault e RLS reais) com Meta simulada | 6 passando. Cobre token **cifrado** no Vault, PNG real no Storage, link assinado que entrega JPEG, publicação confirmada, histórico, outra confeitaria e visitante sem acesso, falha temporária e depois permanente sem "publicado" falso, e desconexão que apaga o token |
| App Flutter (`flutter test`) | 92 passando, incluindo o estúdio, os posts, a exportação PNG, a conexão, o agendamento e os status |

## Pendências

1. Aplicar a **migração 014** em produção (com autorização).
2. Publicar a **API de marketing** e o **serviço do Instagram** (hospedagem com HTTPS) e configurar as variáveis.
3. Criar o **app na Meta**, adicionar a conta da Kika como testadora e fazer o **primeiro teste real** em modo de desenvolvimento.
4. **Revisão da Meta** para o modo Live (depende da Meta).
