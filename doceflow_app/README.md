# DoceFlow · app da confeiteira (Android)

App Flutter da área administrativa da **Kika Cakes**. Ele fala direto com o mesmo Supabase do painel web, com o login da dona, e cada dado é protegido pelo RLS do banco. O contrato completo está em [`../doceflow/docs/app_mobile/backend_app.md`](../doceflow/docs/app_mobile/backend_app.md).

O painel web (`doceflow/admin_app.py`) e a vitrine continuam funcionando como antes: este app não muda nada neles.

## O que já existe (estrutura inicial)

| Tela | O que faz |
|---|---|
| **Abertura** | Mostra o logo enquanto confere a sessão salva no servidor. Sem internet, explica e oferece "Tentar de novo" |
| **Entrar** | E-mail e senha da dona, com validação. Bloqueia por 5 min depois de 5 senhas erradas. **Não tem cadastro**: as contas são criadas pela equipe |
| **Esqueceu a senha?** | Envia o código de 6 números por e-mail, sem revelar se o e-mail existe. Depois troca a senha (mín. 10 caracteres, com letras e números) e volta ao login |
| **Início** | Indicadores reais do banco por período (7, 30 e 90 dias ou tudo): orçamentos novos, pedidos para confirmar, entregas em 7 dias, pedidos em andamento, conversão e valor registrado. Puxe a tela para baixo para atualizar |
| **Perfil** | Conta, confeitaria e papel, trocar senha, versão e **Sair** (com confirmação) |

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
    profile/   presentation (perfil, trocar senha, sair)
test/                        testes de unidade e de tela (com repositórios falsos, sem rede)
```

Os estados ficam no Riverpod. Novas seções (pedidos, orçamentos, produtos, clientes) entram como novas pastas em `features/` e novas abas em `core/widgets/home_shell.dart`.

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

`flutter analyze` não encontra problemas, e `flutter test` passa 32 testes:
- validações, configuração (recusa chave privilegiada), tradução de erros, sessão segura e cálculo dos indicadores;
- telas: abertura, login, senha errada, conta sem acesso, bloqueio por tentativas, recuperação de senha, sessão encerrada, Início, troca de período, erro e nova tentativa, Sair;
- layout sem estouro em 320×568, 320×640, 412×915 e na horizontal.

## Pendências

- Os **indicadores** usam a função `painel_indicadores` da migração **012**, aplicada em produção em 21/11/2026. Se o app for apontado para um banco sem a 012, ele calcula os mesmos números com as tabelas (com o mesmo RLS).
- **Não testado num celular real nem contra o Supabase de produção.** Os testes usam repositórios falsos.
- Próximas etapas: pedidos, orçamentos (com conversão em pedido), produtos e fotos, clientes, marketing (API) e notificações (FCM).
