# Módulos administrativos do app Android: evidências (21/11/2026)

O app (`doceflow_app/`) ganhou **Dashboard**, **Produtos**, **Orçamentos** e **Pedidos**. Todos usam o mesmo Supabase do painel web, com o login da dona. As regras ficam no banco: CHECKs, permissões por coluna, RLS, gatilhos e as funções `converter_orcamento_em_pedido`, `painel_indicadores` e `definir_foto_principal`.

## Como foi testado

| Camada | Ferramenta | Resultado |
|---|---|---|
| Análise estática | `flutter analyze` (Flutter 3.44 / Dart 3.12, em Docker) | **No issues found** |
| Unidade + telas + contrato | `flutter test`: 72 testes, com repositórios falsos nas telas e os repositórios **reais** contra um servidor HTTP simulado no contrato | **72 passando**, 0 toques perdidos (`would not hit test` = 0) |
| Ponta a ponta | `flutter test test_e2e`: repositórios **reais** contra um **Supabase local** (CLI 2.122, Postgres + GoTrue + PostgREST + Storage + Kong), com as migrações **001 a 013** e o `seed.sql` do projeto | **16 passando** |
| Build Android | `flutter build apk --debug`, com os plugins nativos de câmera, galeria, compressão e abrir link | ver o fim deste arquivo |

O teste ponta a ponta **não toca a produção**: ele se recusa a rodar se a URL for a do projeto de produção. As contas usadas existiam só no Supabase local:
- `dona.kika@e2e.test`, dona da Kika Cakes;
- `dona.outra@e2e.test`, dona da "Outra Doceria";
- `sem.perfil@e2e.test`, sem perfil administrativo.

As senhas foram geradas aleatoriamente e ficaram fora do repositório.

## Ponta a ponta: as 16 operações no Supabase local

```
Login (Supabase Auth + perfil administrativo)
  ✓ dona entra e o app descobre a confeitaria pelo perfil
  ✓ senha errada
  ✓ conta sem perfil administrativo não entra
  ✓ dona de OUTRA confeitaria não entra neste app
Produtos
  ✓ lista real do catálogo (27 produtos do seed)
  ✓ cadastro → slug pelo banco → edição → foto → principal → apagar foto → excluir
  ✓ validação do banco: quantidade máxima menor que a mínima é recusada
  ✓ produto com orçamento não pode ser excluído (o banco recusa)
Orçamentos e conversão
  ✓ consulta, detalhe, status e conversão explícita (dois toques simultâneos → um pedido só)
  ✓ entrega exige endereço; perdido não converte
Pedidos
  ✓ pedido do site: itens, valores, os 6 status, edição e histórico
  ✓ confirmar um pedido do site
Dashboard
  ✓ indicadores reais, com estimado e final separados
Permissões no backend
  ✓ dona de outra confeitaria não vê nem altera nada da Kika (lista vazia, update/conversão recusados, produto não criado)
  ✓ visitante (sem login) não lê orçamentos nem pedidos, nem chama painel_indicadores
  ✓ depois de sair, a sessão não vale mais
00:02 +16: All tests passed!
```

## Bug real encontrado pelo teste ponta a ponta

O método `order()` da biblioteca do Supabase para Dart ordena **do maior para o menor por padrão**. Isso deixava três listas invertidas:
- o histórico do pedido;
- a lista de produtos (pela `ordem`);
- as fotos.

Os testes com servidor simulado não pegaram o erro, porque o servidor falso devolvia as linhas já na ordem esperada.

**Correção:** `ascending: true` explícito em todas as ordenações crescentes. Também entrou um teste de contrato que confere `order=alterado_em.asc` e `order=ordem.asc`.

## Outros defeitos encontrados e corrigidos durante os testes

1. **Lista de pedidos:** um status longo ("Aguardando confirmação") fazia a linha estourar a largura (*RenderFlex overflowed*). Agora o selo encolhe (`Flexible`), nas listas e nos detalhes de pedidos e orçamentos.

## Telas (`flutter test`, trechos do relatório)

```
test/modules_test.dart: Início separa valor estimado e valor final
test/modules_test.dart: Orçamentos converter entrega exige endereço
test/modules_test.dart: Orçamentos converter (retirada): confirma e abre o pedido criado
test/modules_test.dart: Orçamentos detalhe e mudança de status (toque duplo grava uma vez)
test/modules_test.dart: Orçamentos lista, filtro por status e estado vazio
test/modules_test.dart: Orçamentos orçamento perdido não converte; já convertido mostra o pedido
test/modules_test.dart: Pedidos detalhe: itens, estimado x final e histórico
test/modules_test.dart: Pedidos editar envia só os campos alterados (valor final)
test/modules_test.dart: Pedidos pedido inexistente mostra erro
test/modules_test.dart: Pedidos todos os 6 status podem ser escolhidos; cancelar pede confirmação
test/modules_test.dart: Pedidos WhatsApp abre wa.me com mensagem e não diz que enviou
test/modules_test.dart: Produtos busca e filtro "Ocultos"
test/modules_test.dart: Produtos cadastro valida, envia uma vez só e abre a edição para as fotos
test/modules_test.dart: Produtos editar: despublicar e salvar
test/modules_test.dart: Produtos excluir pede confirmação; com pedidos o banco recusa e o app orienta
test/modules_test.dart: Produtos excluir produto sem pedidos volta para a lista
test/modules_test.dart: Produtos fotos: câmera e galeria, cancelar, principal e apagar
test/modules_test.dart: Produtos limite de 10 fotos desliga câmera e galeria
test/modules_test.dart: Produtos lista vazia explica o que fazer
test/modules_test.dart: Produtos sob consulta não envia preço
```

**Contrato (`test/contract_test.dart`, 20 testes).** Conferem que:
- o cadastro **não envia slug**;
- a edição envia só as colunas editáveis, filtrando por `id` e `confeitaria_id`;
- excluir com pedido não apaga arquivo nenhum;
- excluir sem pedido apaga primeiro o registro e depois o arquivo;
- a foto vai para `<confeitaria>/<produto>/<id>.jpg` e é registrada com o mesmo caminho;
- se o registro da foto for recusado, o arquivo é apagado;
- a conversão chama a RPC com os parâmetros certos;
- o pedido envia **só** os campos alterados;
- a paginação usa `offset`/`limit`;
- o dashboard chama `painel_indicadores` com o período.

## O que não foi testado

| Item | Motivo | Como conferir |
|---|---|---|
| Câmera, galeria e compressão no aparelho | São plugins nativos: nos testes, o seletor é simulado | No celular: tirar uma foto, conferir na vitrine e confirmar que o arquivo no Storage não tem EXIF/GPS |
| Abrir o WhatsApp de verdade | Depende do aparelho; o teste confere o link `wa.me` gerado | No celular: tocar em "Abrir conversa no WhatsApp" |
| Operações com os dados de produção | Para não criar nem alterar dados reais (decisão da equipe) | Primeiro uso assistido com a dona |

## Build Android

```
Running Gradle task 'assembleDebug'...                            408.0s
✓ Built build/app/outputs/flutter-apk/app-debug.apk
```

Os plugins nativos `image_picker`, `flutter_image_compress` e `url_launcher` compilam para Android.
