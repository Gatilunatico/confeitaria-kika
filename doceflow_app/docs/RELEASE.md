# DoceFlow Android: APK de release, instalação e manutenção

## Versão 1.0.0 (21/11/2026)

| Item | Valor (conferido no APK com `aapt2` e `apksigner`) |
|---|---|
| Arquivo | `C:\Users\Inteli\Desktop\DoceFlow-APK\doceflow-kika-cakes-1.0.0.apk` |
| Cópia do build | `doceflow_app\build\app\outputs\flutter-apk\app-release.apk` |
| Tamanho | 57,0 MB (um APK único para celulares ARM 64 e 32 bits e x86_64) |
| SHA-256 do arquivo | `f4243eec826e123be43176fe41b3c83c2bd785be95243d0411275c334b175950` |
| Nome no celular | **Kika Cakes** (ícone: logo oficial sobre o rosa `#FDE8EC`) |
| Identificador | `br.com.kikacakes.doceflow` |
| Versão | `versionName 1.0.0`, `versionCode 1` |
| Android mínimo | **Android 7.0 (API 24)**. Alvo: Android 16 (API 36) |
| Permissões | **Só internet.** Câmera e galeria usam o seletor do próprio Android e não pedem permissão ao app |
| Assinatura | Esquema v2, certificado `CN=Kika Cakes Confeitaria`, SHA-256 `d7264eb1…1add8e1b` |
| Backend | Supabase de produção, só com a chave **publishable**. A proteção é o RLS e o login da dona |
| Marketing | Estúdio e Instagram **ainda não ativados** nesta versão (a API e o serviço não estão publicados). O app mostra o aviso |

## Instalar no celular

1. Copie o arquivo `doceflow-kika-cakes-1.0.0.apk` para o celular, por cabo USB, Google Drive ou WhatsApp para você mesma.
2. No celular, toque no arquivo. Se o Android pedir, permita **"Instalar apps desconhecidos"** para o app que está abrindo o arquivo (Arquivos, Drive ou Chrome).
3. Se o **Play Protect** avisar "app desconhecido", toque em **Mais detalhes → Instalar assim mesmo**. O aviso aparece porque o app não veio da Play Store.
4. Abra **Kika Cakes** e entre com o e-mail e a senha da dona.
5. Depois de instalar, desligue de novo a permissão "Instalar apps desconhecidos".

**Conferir que o arquivo é o original (opcional):** no Windows, rode o comando abaixo. O resultado tem que ser igual ao SHA-256 da tabela.

```powershell
Get-FileHash "$env:USERPROFILE\Desktop\DoceFlow-APK\doceflow-kika-cakes-1.0.0.apk"
```

## Roteiro de teste no aparelho (preencher)

| # | Passo | Esperado | OK? |
|---|---|---|---|
| 1 | Abrir o app | Logo e depois "Entrar no painel" | |
| 2 | Entrar com a conta da dona | Início com os números reais (3 orçamentos) | |
| 3 | Orçamentos → abrir um | Detalhe e botão do WhatsApp | |
| 4 | Produtos → abrir um → Fotos → Câmera | Tirar a foto e ver a miniatura | |
| 5 | A mesma foto na vitrine do site | A foto aparece no produto | |
| 6 | Desligar a internet e tocar em Pedidos | "Sem conexão…" e "Tentar de novo" | |
| 7 | Perfil → Sair | Volta ao login | |
| 8 | Marketing | Aviso "Estúdio de marketing ainda não ativado" | |

## Atualizar o app (próximas versões)

1. Aumente a versão em `pubspec.yaml`. O número depois do `+` precisa **sempre aumentar**. Exemplo: `1.0.0+1` → `1.0.1+2`.
2. Gere o APK **com a mesma chave**:

   ```powershell
   docker run --rm -v "${PWD}:/app" -v "$env:USERPROFILE\DoceFlow-assinatura:/assinatura" -e DOCEFLOW_SIGNING_PROPERTIES=/assinatura/key.properties -w /app ghcr.io/cirruslabs/flutter:stable bash -lc "flutter build apk --release --obfuscate --split-debug-info=build/symbols-1.0.1 --dart-define-from-file=config/producao.json"
   ```

3. Instale o APK novo **por cima** do antigo, sem desinstalar. O Android só aceita se a assinatura for a mesma, e a dona continua logada.
4. Guarde a pasta `build/symbols-<versão>` junto com o APK. Ela serve para ler os relatórios de erro do app ofuscado.

Sem a chave, o build de release é **recusado de propósito**. Para um APK só de teste, use `-PallowDebugSigning=true` (ou `ORG_GRADLE_PROJECT_allowDebugSigning=true`), e **nunca distribua** esse APK.

## Assinatura: onde está e como cuidar

- **Arquivos:**
  - a chave e a senha estão em `C:\Users\Inteli\DoceFlow-assinatura\` (`doceflow-kika-upload.jks` e `key.properties`), **fora do repositório**;
  - a pasta também tem o `LEIA-ME.txt` para a confeiteira.
- **Combinado:** a chave fica **com a confeiteira**. Ela copia a pasta para dois lugares seguros (pen drive guardado e nuvem pessoal com verificação em duas etapas) e guarda as senhas num gerenciador de senhas. Depois disso, a pasta é apagada deste computador.
- **Se a chave se perder:** não dá mais para atualizar o app. Será preciso desinstalar e instalar um app novo. Os dados não se perdem, porque ficam no Supabase.
- **Nunca** envie a chave por GitHub, e-mail ou WhatsApp. O `.gitignore` bloqueia `key.properties`, `*.jks` e `*.keystore`.
- **Play Store (futuro):** use esta chave como *upload key* e ative o *Play App Signing*.

## Configuração de produção

- **Arquivo:** `config/producao.json`, fora do git. Contém `SUPABASE_URL` e `SUPABASE_KEY` (publishable). `API_URL` e `INSTAGRAM_SERVICE_URL` estão vazios até os serviços serem publicados.
- **Proteções no próprio app:**
  - ele **recusa abrir** com uma chave `sb_secret_…` ou `service_role`;
  - só aceita endereços `https`;
  - o Android bloqueia tráfego sem criptografia (`usesCleartextTraffic=false` e `network_security_config`).
- **Para ativar o marketing:**
  1. publique a API (`doceflow/api`) e o serviço do Instagram (`doceflow/instagram_service`), conforme `doceflow/docs/app_mobile/instagram.md`;
  2. preencha as duas URLs no `config/producao.json`;
  3. gere a versão 1.0.1.
