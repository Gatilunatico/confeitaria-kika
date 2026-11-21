# Auditoria de QA e segurança: DoceFlow Android 1.0.0 (21/11/2026)

**Escopo:**
- o app Android (`doceflow_app/`);
- o backend Supabase (migrações 001 a 014);
- a API de marketing (`doceflow/api`);
- o serviço do Instagram (`doceflow/instagram_service`);
- a integração com a página pública (vitrine) e o painel web.

> **Este relatório não declara segurança total nem o projeto pronto.**
> - Não houve teste num aparelho real: o teste de instalação está com a equipe.
> - Não houve teste de invasão externo.
> - A migração 014 e os serviços de marketing ainda não estão em produção.

## 1. Como foi testado

| Camada | Ambiente | Resultado |
|---|---|---|
| App: telas, unidade e contrato com o Supabase | `flutter test` (Flutter 3.44, Docker) | **121 passando**, 0 toques perdidos |
| App: telas em 7 tamanhos × 3 tamanhos de fonte | `test/responsive_audit_test.dart`, com o toque perdido tratado como falha | 24/24 passando (depois da correção M2) |
| App: sem internet, sessão vencida, ação que falha | `test/offline_audit_test.dart` | 3/3 passando |
| App contra um **Supabase local real** (Auth, REST, Storage, RLS) | `test_e2e/backend_e2e_test.dart` | 16/16 passando |
| **Integração app ↔ vitrine ↔ painel web** (código real dos dois lados, mesmo Supabase local) | `test_e2e/integracao_vitrine_test.dart` + `tests_e2e/test_vitrine_integracao.py`, em 4 fases | 4/4 fases passando |
| Backend, API, serviço do Instagram, vitrine e painel web | `pytest` (Postgres 16 real + TestClient) | **646 passando**, 1 pulado (`leads_antiga`, que só existe em produção) |
| Marketing e Instagram contra um **Supabase local real** (com o Vault) | `tests_e2e/test_instagram_e2e.py` | 6/6 passando (a Meta é **simulada**) |
| **Produção, só leitura** | `auditoria_producao.py` (transação somente leitura + chave publishable) | Ver a seção 3 |
| **APK de release** | `apksigner`, `aapt2`, `unzip` + busca de textos | Ver a seção 4 |

## 2. Funcionalidades auditadas

| Área | Evidência | Situação |
|---|---|---|
| Login, logout e recuperação de senha | Telas (senha errada, conta sem perfil, outra confeitaria, bloqueio depois de 5 tentativas, código de 6 dígitos) + e2e | OK |
| Dashboard | Valores estimados e finais separados; períodos; números iguais aos do banco | OK |
| Produtos e imagens | Do cadastro à exclusão; foto pela câmera ou galeria sem EXIF; foto principal; limite de 10; produto com pedido não sai | OK |
| Orçamentos e conversão | Status; conversão explícita; dois toques ao mesmo tempo geram 1 pedido; entrega exige endereço; orçamento perdido não converte | OK |
| Pedidos e status | Os 6 status; cancelar pede confirmação; só os campos permitidos mudam; histórico em ordem | OK (a ordem do histórico foi corrigida na etapa anterior) |
| Marketing e Instagram | Estúdio, posts, PNG, agendamento idempotente, fila com concorrência, nada de "publicado" falso | OK **nos testes**. **Não ativado** no APK 1.0.0 (serviços não publicados) |
| Integração com a página pública | Produto do app aparece na vitrine com foto e preço; oculto não aparece; pedido e orçamento do site chegam ao app; mudanças do app aparecem no painel web; despublicado bloqueia pedido | OK |
| Sincronização com o Supabase | Todas as leituras e gravações passam pelo banco; não há cópia local de dados de clientes | OK. Atualiza ao puxar a tela (veja B5) |
| Sem internet e sessão vencida | Mensagem clara + "Tentar de novo"; sessão encerrada volta ao login sem dados na tela | OK |
| Resoluções e dispositivos | 320×568 a tablet de 10", deitado, fonte 1,0×, 1,3× e 2,0× | OK (depois da correção M2). **Aparelho real: pendente** |

## 3. Segurança

| Verificação | Resultado (evidência) |
|---|---|
| Tabelas sem RLS em produção | **Nenhuma** |
| Tabelas que o visitante lê | Só `confeitarias`, `produtos` e `product_images` (catálogo público) |
| Visitante: leads, pedidos, itens, histórico, perfis, marketing, Instagram, clientes, dispositivos | **HTTP 401** em todas (produção) |
| Funções que o visitante executa | Só `criar_lead`, `criar_pedido` e os auxiliares do RLS (`is_store_admin`, `storage_folder_admin`). As funções do painel e do serviço respondem **401** |
| Storage | `product-images` público só para leitura. `marketing` e `instagram-media` privados. Envio pelo visitante: **"new row violates row-level security policy"** |
| Cadastro público no Auth | **Fechado** (`disable_signup = true`) |
| Usuário logado sem perfil e dona de outra confeitaria | Recusados no login do app e no banco (e2e: não veem nem alteram nada da Kika) |
| API de marketing | Toda rota exige o token conferido no Supabase; outra confeitaria recebe 403; limite de uso; corpo máximo de 64 KB; erros sem detalhes; documentação desligada em produção |
| Serviço do Instagram | OAuth oficial; `state` de uso único com 10 min; token só no **Vault** (cifrado, conferido no Supabase local); funções do serviço bloqueadas para o app; token nunca na URL nem nos logs |
| Credenciais no APK | Ver a seção 4: só a URL e a chave **publishable** |
| Dados dos clientes | Só a dona logada acessa. A mensagem do WhatsApp leva só o primeiro nome e o protocolo. Nenhum log com dados pessoais. Sem backup nem transferência do app entre aparelhos |

## 4. APK de release 1.0.0

| Verificação | Resultado |
|---|---|
| Assinatura | v2 válida, **chave oficial nova** (`CN=Kika Cakes Confeitaria`, SHA-256 `d7264eb1…1add8e1b`) |
| Identificador, versão e mínimo | `br.com.kikacakes.doceflow`, 1.0.0 (1), Android 7.0+ (API 24), alvo API 36 |
| Permissões | Só `INTERNET` (a outra é interna do AndroidX e não é exportada) |
| Manifesto | `allowBackup=false`, `usesCleartextTraffic=false`, `networkSecurityConfig` e `dataExtractionRules` presentes. O único componente exportado além da tela principal é o `ProfileInstallReceiver` do AndroidX, protegido pela permissão de sistema `DUMP` |
| Busca de segredos em **todos** os arquivos do APK | 0 ocorrências de `SUPABASE_DB_URL`, `postgresql://`, `postgres:`, `INSTAGRAM_APP_SECRET`, `client_secret`, chave privada, `SUPABASE_SERVICE_KEY`, `ADMIN_PASSWORD` e contas de teste. 0 JWTs. `sb_secret`/`service_role` aparecem **só como texto da trava que recusa essas chaves**: 0 ocorrências com formato de chave real |
| Backend com a configuração do APK | Produção responde HTTP 200 (27 produtos publicados); Auth responde; cadastro fechado |

## 5. Problemas encontrados

Nenhum problema **crítico** foi encontrado.

| # | Nível | Problema | Situação |
|---|---|---|---|
| A1 | **Alto** | Um APK de release sem `key.properties` era assinado **com a chave pública de depuração**: qualquer pessoa poderia gerar um APK "atualização" que o Android aceitaria | **Corrigido.** O Gradle recusa release sem a chave (comprovado: o build falhou com a explicação). A chave oficial foi gerada **fora do repositório**, e o APK 1.0.0 está assinado com ela |
| M1 | Médio | No Android 12+, a transferência entre aparelhos ignora `allowBackup=false` | **Corrigido:** `data_extraction_rules.xml` exclui tudo do backup e da transferência (conferido no manifesto do APK) |
| M2 | Médio | **Acessibilidade:** com a fonte ampliada do Android, a lista de posts do Marketing quebrava a tela (`RenderBox was not laid out`) | **Corrigido.** O selo de status foi para baixo do título; 24/24 combinações passam |
| M3 | Médio | Num build sem os serviços de marketing, o app mostraria erros genéricos ao abrir o Marketing | **Corrigido:** aviso "ainda não ativado"; nenhuma chamada é feita (testado) |
| M4 | Médio | A API de marketing publicava `/v1/docs` e `/v1/openapi.json` (mapa da API) | **Corrigido:** desligados, salvo com `API_DOCS=1` (testado) |
| M5 | Médio | A chave de assinatura está neste computador de desenvolvimento | **Pendente:** a confeiteira copia para 2 lugares seguros e apaga daqui (`LEIA-ME.txt`) |
| M6 | Médio | O app **não foi instalado num aparelho real** | **Pendente:** a equipe instala e preenche o roteiro de `doceflow_app/docs/RELEASE.md` |
| M7 | Médio | A migração 014 não está em produção, e a API de marketing e o serviço do Instagram não estão publicados | **Pendente**, com autorização e hospedagem. O app 1.0.0 já mostra o aviso |
| B1 | Baixo | O tráfego sem criptografia não estava bloqueado **explicitamente** (o alvo API 36 já bloqueava) | **Corrigido:** `usesCleartextTraffic=false` + `network_security_config` |
| B2 | Baixo | O `libapp.so` ainda tem informação de depuração (DWARF), o que enfraquece a ofuscação | **Pendente** para a 1.0.1 (gerar com `--strip`, quando a opção estiver estável). Não há segredo no binário |
| B3 | Baixo | A tela de apps recentes e os prints mostram dados de clientes (sem `FLAG_SECURE`) | **Pendente:** decisão da confeiteira (bloquear prints atrapalha compartilhar artes) |
| B4 | Baixo | A tabela legada `leads_antiga` continua em produção (sem nenhuma permissão) | **Pendente:** decisão da equipe |
| B5 | Baixo | O app não recebe pedidos novos sozinho; é preciso puxar a tela para atualizar | **Pendente:** notificações (FCM) e Realtime nas próximas versões |
| B6 | Baixo | `/v1/instagram/conexao` não tem limite de chamadas (exige o login da dona) | **Pendente** |
| B7 | Baixo | Durante a auditoria, uma busca mostrou no terminal as credenciais do **Supabase local** de teste | **Mitigado:** o arquivo foi apagado e o Supabase local desligado. Essas credenciais nunca deram acesso à produção |

## 6. O que fica como próximo passo

1. **Instalar o APK no celular** e preencher o roteiro (M6).
2. **Guardar a chave** com a confeiteira e apagar a cópia deste computador (M5).
3. **Ativar o marketing:** aplicar a 014, publicar a API e o serviço e configurar a Meta (M7, `doceflow/docs/app_mobile/instagram.md`).
4. Gerar a versão 1.0.1 com `--strip` e decidir sobre o `FLAG_SECURE` (B2 e B3).
