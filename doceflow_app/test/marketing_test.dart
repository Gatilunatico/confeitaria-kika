import 'package:doceflow_app/features/marketing/data/marketing_api.dart';
import 'package:doceflow_app/features/marketing/domain/marketing.dart';
import 'package:doceflow_app/features/products/domain/product.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fakes.dart';

Future<void> openMarketing(WidgetTester tester, [String tab = 'Criar']) async {
  await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Marketing')));
  await tester.pumpAndSettle();
  if (tab != 'Criar') {
    await tester.tap(find.descendant(of: find.byType(TabBar), matching: find.text(tab)));
    await tester.pumpAndSettle();
  }
}

Future<void> tapKey(WidgetTester tester, String key) async {
  await tester.ensureVisible(field(key));
  await tester.pumpAndSettle();
  await tester.tap(field(key));
  await tester.pumpAndSettle();
}

Future<void> chooseProduct(WidgetTester tester) async {
  await tester.tap(field('studio_product'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Bolo de Pote').last);
  await tester.pumpAndSettle();
}

FakeProductsRepository productsWithPhotos() {
  final repo = FakeProductsRepository();
  repo.imgs['p1'] = const [
    ProductImage(id: 'img1', path: 's/p1/img1.jpg', url: '', principal: true, order: 1),
    ProductImage(id: 'img2', path: 's/p1/img2.jpg', url: '', principal: false, order: 2),
  ];
  return repo;
}

void main() {
  group('Estúdio', () {
    testWidgets('produto e foto reais, Story, prévia, legenda e hashtags, salvar uma vez só', (tester) async {
      final api = FakeMarketingApi();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), marketing: api, products: productsWithPhotos());
      await openMarketing(tester);
      await chooseProduct(tester);
      await tapKey(tester, 'studio_photo_img2'); // foto real escolhida
      await tapKey(tester, 'studio_format_story');
      await tapKey(tester, 'studio_template_promocao');
      await tapKey(tester, 'studio_preview');
      expect(api.previews.single.imageId, 'img2');
      expect(api.previews.single.format, 'story');
      expect(api.previews.single.template, 'promocao');
      expect(find.text('Prévia (1080×1920)'), findsOneWidget);
      expect(find.byKey(const Key('studio_image')), findsOneWidget);
      expect(tester.widget<TextField>(field('studio_caption')).controller!.text, 'Olha só que delícia: Bolo de Pote! 🧁');

      await tapKey(tester, 'tag_#bolodepote'); // abre o chip; o X remove
      await tester.tap(find.byTooltip('Remover #bolodepote'));
      await tester.pumpAndSettle();
      await tester.enterText(field('studio_new_tag'), 'Festa Junina');
      await tapKey(tester, 'studio_add_tag');
      expect(field('tag_#FestaJunina'), findsOneWidget);
      await tester.enterText(field('studio_caption'), 'Bolo de pote com recheio duplo!');

      await tester.ensureVisible(field('studio_save'));
      await tester.pumpAndSettle();
      await tester.tap(field('studio_save'));
      await tester.tap(field('studio_save'), warnIfMissed: false); // toque duplo
      await tester.pumpAndSettle();
      expect(api.saves, hasLength(1));
      expect(api.saves.single.$2, 'Bolo de pote com recheio duplo!\n\n#kikacakes #FestaJunina');
      expect(find.text('Publicar no Instagram'), findsOneWidget); // abriu o post salvo
    });

    testWidgets('sem foto: a arte usa o logo e o app avisa', (tester) async {
      final api = FakeMarketingApi();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), marketing: api, products: productsWithPhotos());
      await openMarketing(tester);
      await chooseProduct(tester);
      await tapKey(tester, 'studio_no_photo');
      await tapKey(tester, 'studio_preview');
      expect(api.previews.single.usePhoto, isFalse);
      expect(find.textContaining('usa o logo'), findsOneWidget);
    });

    testWidgets('sem produto escolhido não gera prévia', (tester) async {
      final api = FakeMarketingApi();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), marketing: api);
      await openMarketing(tester);
      await tapKey(tester, 'studio_preview');
      expect(find.text('Escolha um produto.'), findsOneWidget);
      expect(api.previews, isEmpty);
    });

    testWidgets('API de marketing não configurada: mensagem clara', (tester) async {
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), marketing: const UnconfiguredMarketingApi());
      await openMarketing(tester);
      await chooseProduct(tester);
      await tapKey(tester, 'studio_preview');
      expect(find.textContaining('ainda não foi configurado'), findsOneWidget);
    });

    test('hashtags: normalização e legenda final', () {
      expect(normalizeHashtag(' #Festa Junina '), '#FestaJunina');
      expect(normalizeHashtag('###'), isNull);
      expect(composeCaption('Texto ', ['#a', '', '#b']), 'Texto\n\n#a #b');
      expect(composeCaption('', ['#a']), '#a');
    });
  });

  group('Posts e exportação', () {
    testWidgets('lista vazia explica o que fazer', (tester) async {
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount));
      await openMarketing(tester, 'Posts');
      expect(find.text('Nenhum post ainda'), findsOneWidget);
    });

    testWidgets('detalhe: exportar PNG, copiar legenda e mudar a situação', (tester) async {
      final api = FakeMarketingApi(posts: [mpost()]);
      final exporter = FakeExporter();
      String? clipboard;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
        if (call.method == 'Clipboard.setData') clipboard = (call.arguments as Map)['text'] as String;
        return null;
      });
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), marketing: api, exporter: exporter);
      await openMarketing(tester, 'Posts');
      await tester.tap(field('post_m1'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'post_export');
      expect(exporter.exported.single.$2, 'kika-bolo-de-pote-feed.png');
      expect(exporter.exported.single.$1, pngBytes.length);
      await tapKey(tester, 'post_copy_caption');
      expect(clipboard, contains('#kikacakes'));
      await tapKey(tester, 'post_status_Pronto');
      expect(api.statuses, [('m1', 'Pronto')]);
    });
  });

  group('Instagram', () {
    const connected = InstagramAccount(status: 'conectado', username: 'kikacakes_confeitaria', accountType: 'business');

    testWidgets('desconectado: conectar abre a página OFICIAL da Meta', (tester) async {
      final ig = FakeInstagramRepository();
      final opened = <Uri>[];
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), instagram: ig, openedUrls: opened);
      await openMarketing(tester, 'Instagram');
      expect(find.textContaining('nunca pede a senha'), findsOneWidget);
      await tapKey(tester, 'ig_connect');
      expect(ig.connectCalls, 1);
      expect(opened.single.host, 'www.instagram.com');
    });

    testWidgets('conectado: mostra a conta e desconecta com confirmação', (tester) async {
      final ig = FakeInstagramRepository(acc: connected);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), instagram: ig);
      await openMarketing(tester, 'Instagram');
      expect(find.text('@kikacakes_confeitaria'), findsOneWidget);
      await tapKey(tester, 'ig_disconnect');
      await tester.tap(field('confirm_action'));
      await tester.pumpAndSettle();
      expect(ig.disconnects, 1);
    });

    testWidgets('agendar "agora": um pedido só, com chave de idempotência, e sem fingir que publicou', (tester) async {
      final ig = FakeInstagramRepository(acc: connected);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), instagram: ig,
          marketing: FakeMarketingApi(posts: [mpost()]));
      await openMarketing(tester, 'Posts');
      await tester.tap(field('post_m1'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'post_schedule');
      await tester.tap(field('schedule_submit'));
      await tester.tap(field('schedule_submit'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(ig.schedules, hasLength(1));
      expect(ig.schedules.single.$1, 'm1');
      expect(ig.schedules.single.$2, isNull);
      expect(ig.schedules.single.$3, matches(RegExp(r'^[A-Za-z0-9_-]{8,128}$')));
      expect(find.textContaining('Agendado para'), findsOneWidget);
      expect(find.text('Publicado'), findsNothing);
      await tester.ensureVisible(find.text('Agendado').last);
      expect(tester.widget<FilledButton>(find.ancestor(of: find.text('Publicar no Instagram'),
          matching: find.byWidgetPredicate((w) => w is FilledButton))).onPressed, isNull); // já agendado
    });

    testWidgets('sem conta conectada: não agenda', (tester) async {
      final ig = FakeInstagramRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), instagram: ig,
          marketing: FakeMarketingApi(posts: [mpost()]));
      await openMarketing(tester, 'Posts');
      await tester.tap(field('post_m1'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'post_schedule');
      expect(find.textContaining('não está conectado'), findsOneWidget);
      expect(field('schedule_submit'), findsNothing);
    });

    testWidgets('status: publicado com link, falhou com nova tentativa, agendado cancelável, conferir', (tester) async {
      final ig = FakeInstagramRepository(acc: connected, pubs: [
        publication(id: 'a', status: 'publicado', mediaId: '17900001', permalink: 'https://www.instagram.com/p/ABC/'),
        publication(id: 'b', status: 'falhou', error: 'A Meta recusou: formato'),
        publication(id: 'c', status: 'agendado'),
        publication(id: 'd', status: 'verificar'),
      ]);
      final opened = <Uri>[];
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), instagram: ig, openedUrls: opened);
      await openMarketing(tester, 'Instagram');
      await tapKey(tester, 'pub_open_a');
      expect(opened.single.toString(), 'https://www.instagram.com/p/ABC/');
      expect(find.text('A Meta recusou: formato'), findsOneWidget);
      await tapKey(tester, 'pub_retry_b');
      expect(ig.retries, ['b']);
      await tapKey(tester, 'pub_cancel_c');
      expect(ig.cancels, ['c']);
      expect(field('pub_cancel_a'), findsNothing); // publicado não cancela
      await tester.ensureVisible(find.text('Conferir no Instagram'));
      expect(find.textContaining('confira se o post saiu'), findsOneWidget);
      await tapKey(tester, 'pub_logs_a');
      expect(find.textContaining('Publicado (confirmado pela Meta)'), findsOneWidget);
    });

    test('"publicado" sem id da Meta não conta como confirmado', () {
      expect(publication(status: 'publicado').confirmedByMeta, isFalse);
      expect(publication(status: 'publicado', mediaId: '1').confirmedByMeta, isTrue);
    });
  });

  group('Build sem os serviços de marketing (como a versão 1.0.0)', () {
    testWidgets('sem API: Marketing explica e não chama nada', (tester) async {
      final api = FakeMarketingApi();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), marketing: api,
          features: (studio: false, instagram: false));
      await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Marketing')));
      await tester.pumpAndSettle();
      expect(find.text('Estúdio de marketing ainda não ativado'), findsOneWidget);
      expect(api.previews, isEmpty);
    });

    testWidgets('com API e sem serviço do Instagram: estúdio funciona, publicação explica', (tester) async {
      final ig = FakeInstagramRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), instagram: ig,
          marketing: FakeMarketingApi(posts: [mpost()]), features: (studio: true, instagram: false));
      await openMarketing(tester, 'Instagram');
      expect(find.text('Publicação automática ainda não ativada'), findsOneWidget);
      await tester.tap(find.descendant(of: find.byType(TabBar), matching: find.text('Posts')));
      await tester.pumpAndSettle();
      await tester.tap(field('post_m1'));
      await tester.pumpAndSettle();
      expect(field('post_schedule'), findsNothing);
      expect(field('post_export'), findsOneWidget);
    });
  });
}
