# Implantação do DoceFlow (Streamlit Community Cloud + Supabase)

Este guia publica a vitrine e o painel da Kika Cakes para uso real. Ele vale para a branch `dev` (commit atual) e para o Supabase de produção (projeto `dfimrkfcudidosdldsjv`, região us-west-2).

## 1. Pré-requisitos (verificados em 14/11/2026)

| Item | Situação | Como foi verificado |
|---|---|---|
| Testes automatizados | ✅ 420 passando, 1 pulado (`leads_antiga`, que só existe em produção) | `docs/evidencias/etapa_05/revisao_2/ciclo_03_pytest.txt` |
| Revisão de QA no navegador | ✅ 14 de 14 itens aprovados no ambiente de QA, com 4 defeitos corrigidos | `docs/evidencias/etapa_05/revisao_2/relatorio_qa.md` |
| Migrações 001 a 010 no Supabase | ✅ aplicadas | Consulta somente leitura: todas as tabelas e colunas existem |
| Catálogo real | ✅ 27 produtos publicados, disponíveis e com preço | Consulta somente leitura e leitura pela chave publishable |
| Dona vinculada | ✅ 1 perfil `proprietaria` ativo | Consulta somente leitura |
| WhatsApp da confeitaria | ✅ número do cardápio oficial (`5511…5065`) gravado em `confeitarias.whatsapp` | Consulta somente leitura. ⚠️ **Confirme com a Kika** que esse é o número de atendimento |
| Visitante sem acesso a dados privados | ✅ leads, pedidos, itens, histórico, perfis, marketing e Instagram recusados; `cadastrar_admin` recusado | Teste com a chave publishable em produção |
| Cadastro aberto no Supabase Auth | ❌ **aberto** (`disable_signup = false`) | Endpoint público `/auth/v1/settings`. Veja o passo 2.1 |
| Fotos reais dos produtos | ❌ nenhuma enviada (a vitrine usa ilustrações) | `product_images` com 0 linhas. Veja o passo 4 |

## 2. Supabase (painel do Supabase, feito pela equipe)

1. **Fechar o cadastro público:** Authentication → Sign In / Providers → Email → desative **"Allow new users to sign up"**.
   - Hoje qualquer pessoa consegue criar uma conta. Ela não vê nada, porque o RLS exige um perfil vinculado, mas o cadastro não deve ficar aberto.
2. **Senha da dona:** confirme que ela consegue entrar. Se não conseguir, use Authentication → Users → "Send password recovery".
3. **Usuários:** existem 2 contas no Auth e só 1 está vinculada como dona. Remova a outra se não for de ninguém da equipe.
4. **Plano gratuito:** projetos sem atividade podem ser **pausados**. Antes da demonstração, abra o painel do Supabase e confirme que o projeto está ativo ("Active").

## 3. Streamlit Community Cloud

Desde a Etapa 6 são **dois apps separados**, do mesmo repositório, ligados ao mesmo Supabase:

| App | Main file path | Para quem | Endereço sugerido |
|---|---|---|---|
| **Vitrine** | `doceflow/public_app.py` | clientes, sem login | `kika-cakes.streamlit.app` |
| **Painel** | `doceflow/admin_app.py` | só a dona, com login | `kika-cakes-painel.streamlit.app` |

A vitrine **não contém** nenhuma página do painel: `/admin` e `/painel` simplesmente não existem nela.

1. Acesse **share.streamlit.io** com a conta GitHub que tem acesso ao repositório `Gatilunatico/confeitaria-kika`.
2. **Create app → Deploy a public app from GitHub**, uma vez para cada app da tabela:
   - Repository: `Gatilunatico/confeitaria-kika`
   - Branch: `dev`
   - Main file path: o da tabela
3. **Advanced settings → Python version:** 3.12 (a versão testada).
4. **Advanced settings → Secrets** (nos dois apps): cole o conteúdo de `doceflow/.streamlit/secrets.toml.example` com os valores reais:
   - `SUPABASE_URL` e `SUPABASE_KEY`: a chave **publishable** (`sb_publishable_…`), **nunca** a `service_role` ou `sb_secret`.
   - `PUBLIC_APP_URL` = endereço da vitrine. No painel, ele preenche o link do Estúdio de Marketing.
   - Não coloque `SUPABASE_DB_URL` nem `ADMIN_PASSWORD`.
5. **Deploy.** O Cloud instala o `doceflow/requirements.txt` (versões mínimas testadas: Streamlit 1.67 e supabase 2.34).
6. **App já publicado antes com `doceflow/app.py`:** o Streamlit Cloud **não permite trocar** o arquivo principal de um app publicado (as configurações só mudam o endereço e o Python). Por isso, desde 15/11/2026, o próprio `doceflow/app.py` **é a vitrine**, igual ao `public_app.py` (garantido por teste). O app antigo continua no mesmo endereço, agora sem o login do painel.

**Endereços em uso (15/11/2026):**
- Vitrine: `https://confeitaria-kika-wjwdwbhezpirrj9fhswmwq.streamlit.app` (arquivo `doceflow/app.py`, Python 3.14)
- Painel: `https://kika-cakes-painel.streamlit.app` (arquivo `doceflow/admin_app.py`, Python 3.12)

> O Streamlit Community Cloud coloca o app em **repouso** depois de um tempo sem acessos. No primeiro acesso depois disso, aparece um botão para acordá-lo, e leva cerca de 1 minuto. **Abra o link uns 5 minutos antes da demonstração.**

## 4. Conteúdo real (feito pela Kika no painel)

- **Fotos:** Produtos → escolha o produto → aba **Fotos** → envie 1 a 3 fotos (JPG, PNG ou WEBP, até 5 MB).
  - A primeira vira a foto principal da vitrine.
  - Comece pelos 5 produtos mais vendidos.
- **Destaques:** aba **Editar** → marque **"Destaque no catálogo"** em 2 a 4 produtos.
- **Preços e disponibilidade:** conferir na tabela de Produtos. Desmarque **"Disponível para orçamento"** no que não estiver sendo produzido.

## 5. Teste de fumaça depois de publicar (5 minutos, no celular)

| # | Passo | Esperado |
|---|---|---|
| 1 | Abrir a URL pública no celular | Logo, catálogo com os 27 produtos e sem rolagem para os lados |
| 2 | Solicitar orçamento de 1 produto | Protocolo `DF-…` e botão "Abrir conversa no WhatsApp" |
| 3 | Tocar no botão do WhatsApp | Abre o número da Kika com a mensagem e o protocolo |
| 4 | Fazer um pedido com 2 produtos | Resumo com os itens, depois protocolo `PD-…` **na mesma janela** |
| 5 | Abrir o **endereço do painel** e entrar com o e-mail da dona | Painel com os indicadores, contando o orçamento e o pedido novos |
| 6 | Orçamentos → mudar o status do teste para "Perdido". Pedidos → "Cancelado" | Status atual atualizado e o histórico do pedido registrado |
| 7 | Sair e abrir `<painel>/painel`. Na vitrine, abrir `/admin` | Painel: volta ao login, sem dados. Vitrine: volta ao catálogo (a página não existe) |

Se o passo 1 mostrar "catálogo indisponível", abra **"Detalhes técnicos (para a equipe)"**. Ele mostra qual variável está faltando, sem expor o valor.

## 6. Atualizar o app

- Cada `git push` na branch `dev` **atualiza o app publicado** automaticamente.
- Mudanças no banco: aplique a migração **antes** do push. Todas as migrações são idempotentes e não destrutivas (`database/schema_reference.md`).
- **Voltar uma versão:** reverter o commit na `dev` e fazer push. O banco não precisa voltar, porque as migrações só adicionam.

## 7. Link para divulgação

- Use `https://<seu-app>.streamlit.app/?origem=instagram` na bio do Instagram. A origem aparece em cada orçamento e pedido, e dá para saber de onde veio o cliente.
- O QR Code pode ser gerado pelo Estúdio de Marketing ou por qualquer gerador, apontando para esse link.

## 8. "Esqueceu a senha?" do painel (configuração no Supabase)

O painel tem **"Esqueceu a senha?"** na tela de entrada. O app pede ao Supabase o e-mail de recuperação, valida o link ou o código **no servidor** e deixa criar uma senha nova com pelo menos 10 caracteres. Depois disso, a pessoa entra normalmente: recuperar a senha nunca abre o painel direto.

Para o e-mail chegar e funcionar, a equipe precisa configurar **três coisas no Supabase**:

1. **Modelo do e-mail:** Authentication → Emails → Templates → **Reset password**.
   - O link padrão do Supabase devolve o código depois do `#` no endereço, e o Streamlit não consegue ler essa parte. Troque o corpo do e-mail por:

     ```html
     <h2>Kika Cakes · nova senha do painel</h2>
     <p>Recebemos um pedido para criar uma nova senha do painel.</p>
     <p><a href="https://kika-cakes-painel.streamlit.app/?token_hash={{ .TokenHash }}&type=recovery">Criar nova senha</a></p>
     <p>Ou digite este código no painel, em "Esqueceu a senha?": <strong>{{ .Token }}</strong></p>
     <p>O link e o código valem por 1 hora. Se você não pediu, ignore este e-mail: sua senha continua a mesma.</p>
     ```
   - Assunto sugerido: `Kika Cakes · criar nova senha do painel`.
2. **Endereço do painel:** Authentication → URL Configuration.
   - **Site URL:** `https://kika-cakes-painel.streamlit.app`
   - Em **Redirect URLs**, inclua o mesmo endereço.
3. **Envio de e-mails (SMTP):** o serviço de e-mail padrão do Supabase serve só para testes. Ele tem limite baixo de envios por hora e, pela documentação do Supabase, entrega apenas para os e-mails da equipe do projeto. **Antes de depender disso, configure um SMTP próprio** em Authentication → Emails → SMTP Settings:
   - **Escolhido (21/11/2026): Gmail SMTP com a conta Gmail da confeitaria.** É grátis (cerca de 500 e-mails por dia) e não exige domínio próprio.
     - ⚠️ **Provisório:** enquanto a confeiteira não cria a senha de app dela, o remetente e o usuário do SMTP são o Gmail de quem administra o projeto. Quando ela criar a senha, troque os dois campos para o Gmail da confeitaria, cole a senha nova e apague a senha de app provisória.
     - Na conta Google da confeitaria, ative a **verificação em duas etapas**.
     - Em **myaccount.google.com/apppasswords**, crie uma **senha de app** chamada "Supabase DoceFlow". É a própria confeiteira (ou quem tem a conta) quem cria.
   - No Supabase, ative **Enable custom SMTP** e preencha:

     | Campo | Valor |
     |---|---|
     | Sender email | o Gmail da confeitaria |
     | Sender name | `Kika Cakes Confeitaria` |
     | Host | `smtp.gmail.com` |
     | Port | `587` |
     | Username | o mesmo Gmail |
     | Password | a senha de app (16 letras) |

   - A senha de app fica **só** no painel do Supabase, nunca no repositório nem nos Secrets do Streamlit.
   - Se ela vazar, apague-a em myaccount.google.com/apppasswords e crie outra. A senha normal do Gmail continua a mesma.
   - Alternativas se um dia houver domínio próprio: Brevo ou Resend.

**Teste depois de configurar:**
1. No painel, abra **Esqueceu a senha?** e informe o e-mail da dona.
2. Confira se o e-mail chegou (veja também o spam).
3. Clique no link: a tela "Criar nova senha" deve abrir.
4. Salve uma senha nova e entre com ela.

**Se o e-mail não chegar,** um administrador do projeto ainda pode usar Authentication → Users → ⋮ → **Send password recovery**. Esse caminho usa o mesmo modelo de e-mail.

