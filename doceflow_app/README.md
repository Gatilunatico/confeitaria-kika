# DoceFlow · app da confeiteira (Android)

App Flutter da área administrativa da **Kika Cakes**. Ele fala direto com o mesmo Supabase do painel web, com o login da dona, e cada dado é protegido pelo RLS do banco. O contrato completo está em [`../doceflow/docs/app_mobile/backend_app.md`](../doceflow/docs/app_mobile/backend_app.md).

O painel web (`doceflow/admin_app.py`) e a vitrine continuam funcionando como antes: este app não muda nada neles.

## O que o app faz

| Tela | O que faz |
|---|---|
| **Abertura** | Mostra o logo enquanto confere a sessão salva no servidor. Sem internet, explica e oferece "Tentar de novo" |
| **Entrar** | E-mail e senha da dona, com validação. Bloqueia por 5 min depois de 5 senhas erradas. **Não tem cadastro**: as contas são criadas pela equipe |
| **Esqueceu a senha?** | Envia o código de 6 números por e-mail, sem revelar se o e-mail existe. Depois troca a senha (mín. 10 caracteres, com letras e números) e volta ao login |
| **Início** | Indicadores reais por período (7, 30 e 90 dias ou tudo), em três blocos. **Orçamentos:** novos, em andamento, vendas e conversão. **Pedidos:** para confirmar, em andamento, entregas em 7 dias e entregues. **Financeiro:** valor **estimado** separado do valor **final** combinado, e quantos pedidos estão sem estimativa |
| **Orçamentos** | Lista com filtro por status e "Carregar mais". O detalhe mostra o produto, a data, a modalidade e as observações. Dá para mudar o status (Novo, Em atendimento, Orçamento enviado, Venda concluída, Perdido) e **converter em pedido** por escolha da dona: ela confere a data, o endereço (se for entrega), o valor final e as observações internas |
| **Pedidos** | Lista com filtro pelos 6 status. O detalhe mostra os itens com subtotal, o valor estimado e o final, a entrega e as observações. Dá para mudar o status (cancelar pede confirmação) e editar o valor final, a data de entrega e as observações internas. Mostra o **histórico** de alterações |
| **Produtos** | Busca e filtros (na vitrine, ocultos, indisponíveis). Cadastro e edição: nome, categoria, descrição, unidade, tipo de preço, preço, quantidade mínima e máxima, tempo de produção, publicação, disponibilidade e destaque. Exclusão com confirmação. **Fotos pela câmera ou galeria** (até 10), foto principal e apagar foto |
| **WhatsApp** | Nos orçamentos e pedidos, "Abrir conversa no WhatsApp" abre o app com a mensagem já escrita. **Quem envia é a confeiteira.** O app não diz que a mensagem foi enviada |
| **Perfil** | Conta, confeitaria e papel, trocar senha, versão e **Sair** (com confirmação) |

**Regras de negócio:** as regras ficam no banco (CHECKs, permissões por coluna, RLS e funções), e o app não as repete.
- **Preço e valor estimado** são calculados pelo banco.
- **Conversão de orçamento em pedido:** é feita pela função `converter_orcamento_em_pedido`, que cria um pedido por orçamento e grava o histórico.
- **Slug do produto:** quem gera é um gatilho do banco.
- **Histórico do pedido:** quem grava é um gatilho.
- **Limite de 10 fotos:** quem aplica é um gatilho.
- **Excluir produto com orçamento ou pedido:** o banco recusa, e o app orienta a despublicar.
- **Validação nos formulários:** o app repete só os limites dos CHECKs, para mostrar o erro antes de enviar. O banco valida de novo.

**Sem operações duplicadas:**
- Os botões ficam desligados enquanto a operação roda.
- A conversão é idempotente no banco: repetida, devolve o mesmo pedido.
- Cada foto tem um id único.
- O pedido só envia os campos que mudaram.

**Fotos:** são comprimidas no celular e enviadas **sem EXIF/GPS**, para não levar a localização ao catálogo público.

**Segurança:**
- A sessão fica no **armazenamento seguro do Android** (Keystore), não em texto puro.
- O backup do app está desligado.
- O app só aceita a chave **publishable**: uma chave `sb_secret` ou `service_role` é recusada ao abrir.
- Só entra quem tem **perfil administrativo ativo** na confeitaria configurada.
- Se o servidor encerrar a sessão, o app volta ao login.

## Identidade visual

| Elemento | Valor |
|---|---|
| Rosa (fundo) | `#FDE8EC` |
| Marrom (texto e botões) | `#5C3317`: 10,4:1 sobre o rosa e 12:1 com branco |
| Destaque | `#E0628A`: ícones, bordas e indicadores. Não é usado em texto pequeno, porque tem só 3,3:1 com branco |
| Títulos | Abril Fatface |
| Textos | Quicksand |
| Logo | `assets/logo/logo-kika-cakes.png`, cópia byte a byte do logo oficial, só redimensionada (sem recorte nem recoloração). Também é o ícone do app, sobre o rosa |

As fontes estão dentro do app (`assets/fonts`, licença OFL), então ele não depende da internet para mostrar o texto.

> A vitrine e o painel web usam a paleta do PDF da confeitaria (`doceflow/docs/identidade_visual.md`). O app usa a paleta definida para ele em 21/11/2026.

## Estrutura

```
lib/
  main.dart                  inicia o Supabase (sessão segura) e injeta os repositórios
  app.dart                   MaterialApp + tema + rotas
  core/
    config/app_config.dart   URL e chave lidas no build (recusa chave privilegiada)
    errors/app_failure.dart  todo erro vira uma mensagem em português, sem detalhe técnico
    router/app_router.dart   go_router: as rotas seguem o estado do login
    storage/                 sessão do Supabase no flutter_secure_storage
    theme/app_theme.dart     cores, fontes e componentes da Kika Cakes
    widgets/                 logo, botão com carregamento, mensagens, barra inferior
  features/
    auth/      domain (conta, validações) · data (Supabase) · application (estado) · presentation (telas)
    dashboard/ domain (indicadores, períodos) · data (RPC painel_indicadores) · presentation
    quotes/    domain (orçamento, status, conversão) · data (leads + RPC de conversão) · presentation
    orders/    domain (pedido, itens, histórico, status) · data (orders, order_items, order_history) · presentation
    products/  domain (produto, regras) · data (produtos, fotos no Storage, câmera/galeria) · presentation
    profile/   presentation (perfil, trocar senha, sair)
  core/format.dart, core/whatsapp.dart   moeda e datas pt-BR; link wa.me
test/                        unidade, telas e contrato com o Supabase (sem rede)
test_e2e/                    ponta a ponta contra um Supabase local (não roda no `flutter test` normal)
```

Os estados ficam no Riverpod. Cada seção tem uma aba em `core/widgets/home_shell.dart`.

## Como executar

### 1. Configuração (uma vez)

Copie o exemplo e preencha com a URL do projeto e a chave **publishable** (Supabase → Project Settings → API Keys):

```powershell
Copy-Item config\local.example.json config\local.json
```

O `config/local.json` está no `.gitignore`. **Nunca** coloque a chave `service_role` ou `sb_secret`.

### 2a. Com o Flutter instalado (Flutter 3.44 / Dart 3.12 ou mais novo)

```powershell
flutter pub get
```

```powershell
flutter run --dart-define-from-file=config/local.json
```

```powershell
flutter test
```

### 2b. Sem Flutter instalado (Docker)

É assim que o projeto foi criado e testado. A imagem tem Flutter e Android SDK:

```powershell
docker run --rm -v "${PWD}:/app" -w /app ghcr.io/cirruslabs/flutter:stable bash -lc "flutter pub get && flutter analyze && flutter test"
```

```powershell
docker run --rm -v "${PWD}:/app" -w /app ghcr.io/cirruslabs/flutter:stable bash -lc "flutter build apk --release --dart-define-from-file=config/local.json"
```

O APK fica em `build/app/outputs/flutter-apk/`.

### 3. Assinatura do APK de produção

A chave de assinatura fica **com a confeiteira**, fora deste repositório. Para assinar:

1. Crie `android/key.properties` com `storeFile`, `storePassword`, `keyAlias` e `keyPassword`.
2. Os arquivos `key.properties`, `*.jks` e `*.keystore` estão no `.gitignore`.

Sem esse arquivo, o build de release usa a chave de depuração, que serve **só para testes**.

## Testes (21/11/2026)

`flutter analyze` não encontra problemas.

| Suíte | O que cobre | Resultado |
|---|---|---|
| `flutter test` (72) | **Unidade:** validações, configuração, erros e indicadores. **Telas:** cada operação de produtos, orçamentos, pedidos e WhatsApp, com estados vazios, erros, toque duplo e layout em 320 px e na horizontal. **Contrato:** os repositórios reais contra um servidor simulado, conferindo tabela, filtros, colunas, funções e ordem | 72 passando |
| `test_e2e` (16) | Os repositórios **reais** contra um **Supabase local** com as migrações 001 a 013, Auth, Storage e RLS. Cobre login, produtos (do cadastro à exclusão, com fotos), orçamentos (status e conversão com dois toques simultâneos), pedidos (6 status, edição e histórico), dashboard e permissões (outra confeitaria, visitante e depois de sair) | 16 passando |

Evidências: `../doceflow/docs/evidencias/app_mobile/modulos_admin_app.md`.

### Teste ponta a ponta (Supabase local, nunca o de produção)

1. Com o Docker ligado, rode `npx supabase start` numa pasta com as migrações em `supabase/migrations/` e o `seed.sql`.
2. Crie três usuários: a dona, a dona de outra confeitaria e um usuário sem perfil. Rode `cadastrar_admin` para as duas donas.
3. Preencha `config/e2e.local.json` (no `.gitignore`) com `E2E_URL`, `E2E_KEY` (publishable local) e os e-mails e senhas.
4. Rode o teste:

```powershell
flutter test test_e2e --dart-define-from-file=config/e2e.local.json
```

O teste se recusa a rodar contra o projeto de produção.

## Pendências

- Os **indicadores** usam a função `painel_indicadores` da migração **012**, aplicada em produção em 21/11/2026. Se o app for apontado para um banco sem a 012, ele calcula os mesmos números com as tabelas (com o mesmo RLS).
- **Não testado num celular real nem com os dados de produção.**
  - O fluxo completo foi testado num Supabase local idêntico.
  - Câmera, galeria, compressão e abertura do WhatsApp dependem do aparelho e precisam ser conferidas no celular da confeiteira.
- Próximas etapas: clientes, marketing (API) e notificações (FCM).
