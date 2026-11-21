import 'dart:typed_data';

import 'package:doceflow_app/features/orders/domain/order.dart';
import 'package:doceflow_app/features/products/data/image_preparer.dart';
import 'package:doceflow_app/features/products/domain/product.dart';
import 'package:doceflow_app/features/quotes/domain/quote.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fakes.dart';

Future<void> openTab(WidgetTester tester, String label) async {
  await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(label)));
  await tester.pumpAndSettle();
}

Future<void> tapKey(WidgetTester tester, String key) async {
  await tester.ensureVisible(field(key));
  await tester.pumpAndSettle();
  await tester.tap(field(key));
  await tester.pumpAndSettle();
}

void main() {
  // ============================================================ dashboard financeiro
  testWidgets('Início separa valor estimado e valor final', (tester) async {
    await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount));
    await tester.ensureVisible(find.text('Valor final combinado'));
    await tester.pumpAndSettle();
    expect(find.text('Valor estimado'), findsOneWidget);
    expect(find.text('Valor final combinado'), findsOneWidget);
    expect(find.textContaining('não é receita'), findsOneWidget);
  });

  // ============================================================ produtos
  group('Produtos', () {
    testWidgets('lista vazia explica o que fazer', (tester) async {
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: FakeProductsRepository(items: []));
      await openTab(tester, 'Produtos');
      expect(find.text('Nenhum produto cadastrado'), findsOneWidget);
    });

    testWidgets('busca e filtro "Ocultos"', (tester) async {
      final repo = FakeProductsRepository(items: [product(), product(id: 'p2', name: 'Brigadeiro', published: false)]);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      expect(find.text('Bolo de Pote'), findsOneWidget);
      await tester.tap(find.text('Ocultos'));
      await tester.pumpAndSettle();
      expect(find.text('Bolo de Pote'), findsNothing);
      expect(find.text('Brigadeiro'), findsOneWidget);
      await tester.tap(find.text('Todos'));
      await tester.enterText(field('product_search'), 'brig');
      await tester.pumpAndSettle();
      expect(find.text('Bolo de Pote'), findsNothing);
    });

    testWidgets('cadastro valida, envia uma vez só e abre a edição para as fotos', (tester) async {
      final repo = FakeProductsRepository(items: []);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      await tester.tap(field('product_new'));
      await tester.pumpAndSettle();

      await tapKey(tester, 'product_save');
      expect(find.text('Nome entre 2 e 120 caracteres.'), findsOneWidget);
      expect(repo.created, isEmpty);

      await tester.enterText(field('product_name'), 'Bolo de Cenoura');
      await tester.enterText(field('product_category'), 'Bolos');
      await tester.enterText(field('product_unit'), 'kg');
      await tester.enterText(field('product_price'), '85,50');
      await tester.enterText(field('product_min'), '2');
      await tester.enterText(field('product_max'), '1');
      await tapKey(tester, 'product_save');
      expect(find.text('A máxima não pode ser menor que a mínima.'), findsOneWidget);

      await tester.enterText(field('product_max'), '10');
      await tester.ensureVisible(field('product_save'));
      await tester.pumpAndSettle();
      await tester.tap(field('product_save'));
      await tester.tap(field('product_save'), warnIfMissed: false); // toque duplo
      await tester.pumpAndSettle();
      expect(repo.created, hasLength(1));
      final d = repo.created.single;
      expect((d.name, d.category, d.unit, d.price, d.minQty, d.maxQty), ('Bolo de Cenoura', 'Bolos', 'kg', 85.5, 2, 10));
      expect(d.toColumns().containsKey('slug'), isFalse); // o banco gera o slug
      expect(find.text('Editar produto'), findsOneWidget);
      expect(find.text('Fotos'), findsOneWidget);
    });

    testWidgets('sob consulta não envia preço', (tester) async {
      final repo = FakeProductsRepository(items: []);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      await tester.tap(field('product_new'));
      await tester.pumpAndSettle();
      await tester.enterText(field('product_name'), 'Bolo Personalizado');
      await tester.enterText(field('product_category'), 'Bolos');
      await tester.enterText(field('product_unit'), 'kg');
      await tester.tap(find.text('Sob consulta'));
      await tester.pumpAndSettle();
      expect(field('product_price'), findsNothing);
      await tapKey(tester, 'product_save');
      expect(repo.created.single.toColumns()['preco'], isNull);
      expect(repo.created.single.priceType, priceOnRequest);
    });

    testWidgets('editar: despublicar e salvar', (tester) async {
      final repo = FakeProductsRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      await tester.tap(find.text('Bolo de Pote'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'product_published');
      await tapKey(tester, 'product_save');
      expect(repo.updated.single.$1, 'p1');
      expect(repo.updated.single.$2.published, isFalse);
      expect(find.text('Produto salvo.'), findsOneWidget);
    });

    testWidgets('excluir pede confirmação; com pedidos o banco recusa e o app orienta', (tester) async {
      final repo = FakeProductsRepository(inUse: {'p1'});
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      await tester.tap(find.text('Bolo de Pote'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'product_delete');
      expect(find.textContaining('não pode ser desfeita'), findsOneWidget);
      await tester.tap(field('confirm_action'));
      await tester.pumpAndSettle();
      expect(repo.deleted, isEmpty);
      await tester.ensureVisible(find.textContaining('Despublique'));
      expect(find.textContaining('Despublique'), findsOneWidget);
    });

    testWidgets('excluir produto sem pedidos volta para a lista', (tester) async {
      final repo = FakeProductsRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      await tester.tap(find.text('Bolo de Pote'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'product_delete');
      await tester.tap(field('confirm_action'));
      await tester.pumpAndSettle();
      expect(repo.deleted, ['p1']);
      expect(find.text('Nenhum produto cadastrado'), findsOneWidget);
    });

    testWidgets('fotos: câmera e galeria, cancelar, principal e apagar', (tester) async {
      final repo = FakeProductsRepository();
      final picker = FakePhotoPicker(result: Uint8List.fromList([0xFF, 0xD8, 0xFF]));
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo, picker: picker);
      await openTab(tester, 'Produtos');
      await tester.tap(find.text('Bolo de Pote'));
      await tester.pumpAndSettle();

      await tapKey(tester, 'photo_camera');
      await tapKey(tester, 'photo_gallery');
      expect(picker.calls, [PhotoSource.camera, PhotoSource.gallery]);
      expect(repo.uploads, hasLength(2));
      expect(find.text('2/10'), findsOneWidget);

      picker.result = null; // a pessoa cancelou
      await tapKey(tester, 'photo_gallery');
      expect(repo.uploads, hasLength(2));

      await tapKey(tester, 'photo_img2');
      await tester.tap(field('photo_make_principal'));
      await tester.pumpAndSettle();
      expect(repo.principals, ['img2']);
      await tester.pump(const Duration(seconds: 5)); // aviso (SnackBar) some
      await tester.pumpAndSettle();

      await tapKey(tester, 'photo_img1');
      await tester.tap(field('photo_delete'));
      await tester.pumpAndSettle();
      await tester.tap(field('confirm_action'));
      await tester.pumpAndSettle();
      expect(repo.deletedImages, ['img1']);
    });

    testWidgets('limite de 10 fotos desliga câmera e galeria', (tester) async {
      final repo = FakeProductsRepository();
      repo.imgs['p1'] = [
        for (var i = 0; i < 10; i++) ProductImage(id: 'i$i', path: 'p/$i.jpg', url: '', principal: i == 0, order: i)
      ];
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), products: repo);
      await openTab(tester, 'Produtos');
      await tester.tap(find.text('Bolo de Pote'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Limite de 10 fotos'), findsOneWidget);
      final camera = tester.widget<OutlinedButton>(find.ancestor(of: find.text('Câmera'), matching: find.byWidgetPredicate((w) => w is OutlinedButton)));
      expect(camera.onPressed, isNull);
    });
  });

  // ============================================================ orçamentos
  group('Orçamentos', () {
    testWidgets('lista, filtro por status e estado vazio', (tester) async {
      final repo = FakeQuotesRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), quotes: repo);
      await openTab(tester, 'Orçamentos');
      expect(find.text('Ana Souza'), findsOneWidget);
      await tester.ensureVisible(find.widgetWithText(ChoiceChip, QuoteStatus.perdido));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ChoiceChip, QuoteStatus.perdido));
      await tester.pumpAndSettle();
      expect(repo.listCalls.last.$1, QuoteStatus.perdido);
      expect(find.text('Nenhum orçamento "Perdido"'), findsOneWidget);
    });

    testWidgets('detalhe e mudança de status (toque duplo grava uma vez)', (tester) async {
      final repo = FakeQuotesRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), quotes: repo);
      await openTab(tester, 'Orçamentos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      expect(find.text('Sem lactose'), findsOneWidget);
      expect(find.text('(11) 98765-4321'), findsOneWidget);
      final chip = field('quote_status_${QuoteStatus.emAtendimento}');
      await tester.ensureVisible(chip);
      await tester.pumpAndSettle();
      await tester.tap(chip);
      await tester.tap(chip, warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(repo.statusUpdates, [('q1', QuoteStatus.emAtendimento)]);
    });

    testWidgets('converter (retirada): confirma e abre o pedido criado', (tester) async {
      final repo = FakeQuotesRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), quotes: repo);
      await openTab(tester, 'Orçamentos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'quote_convert');
      expect(find.text('Converter em pedido'), findsWidgets);
      expect(field('convert_address'), findsNothing); // retirada: sem endereço
      await tester.enterText(field('convert_value'), '320,00');
      await tester.enterText(field('convert_notes'), 'Sinal pago');
      await tester.ensureVisible(field('convert_submit'));
      await tester.pumpAndSettle();
      await tester.tap(field('convert_submit'));
      await tester.tap(field('convert_submit'), warnIfMissed: false);
      await tester.pumpAndSettle();
      expect(repo.conversions, hasLength(1));
      final input = repo.conversions.single.$2;
      expect((input.finalValue, input.internalNotes), (320.0, 'Sinal pago'));
      expect(find.text('Pedido'), findsWidgets); // tela do pedido
      expect(find.text('PD-261121-XYZ789'), findsOneWidget);
    });

    testWidgets('converter entrega exige endereço', (tester) async {
      final repo = FakeQuotesRepository(items: [quote(fulfillment: 'Entrega')]);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), quotes: repo);
      await openTab(tester, 'Orçamentos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'quote_convert');
      await tester.ensureVisible(field('convert_submit'));
      await tester.pumpAndSettle();
      await tester.tap(field('convert_submit'));
      await tester.pumpAndSettle();
      expect(find.textContaining('pelo menos 10 caracteres'), findsOneWidget);
      expect(repo.conversions, isEmpty);
      await tester.enterText(field('convert_address'), 'Rua das Flores, 123, Centro');
      await tester.ensureVisible(field('convert_submit'));
      await tester.pumpAndSettle();
      await tester.tap(field('convert_submit'));
      await tester.pumpAndSettle();
      expect(repo.conversions.single.$2.address, 'Rua das Flores, 123, Centro');
    });

    testWidgets('orçamento perdido não converte; já convertido mostra o pedido', (tester) async {
      final repo = FakeQuotesRepository(items: [quote(status: QuoteStatus.perdido), quote(id: 'q2', orderId: 'o1')]);
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), quotes: repo);
      await openTab(tester, 'Orçamentos');
      await tester.tap(find.text('Ana Souza').first);
      await tester.pumpAndSettle();
      await tester.ensureVisible(field('quote_convert'));
      await tester.pumpAndSettle();
      expect(tester.widget<FilledButton>(find.ancestor(of: find.text('Converter em pedido'), matching: find.byWidgetPredicate((w) => w is FilledButton))).onPressed, isNull);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ana Souza').last);
      await tester.pumpAndSettle();
      expect(field('quote_open_order'), findsOneWidget);
    });
  });

  // ============================================================ pedidos
  group('Pedidos', () {
    testWidgets('detalhe: itens, estimado x final e histórico', (tester) async {
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount));
      await openTab(tester, 'Pedidos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      expect(find.text('Bem-casado'), findsOneWidget);
      expect(find.textContaining('50 × unidade · a partir de R\$'), findsOneWidget);
      expect(find.textContaining('600,00'), findsWidgets); // estimado
      expect(find.text('a combinar'), findsOneWidget); // final ainda vazio
      await tester.ensureVisible(find.textContaining('Pedido feito pela cliente'));
      expect(find.textContaining('Pedido feito pela cliente'), findsOneWidget);
    });

    testWidgets('todos os 6 status podem ser escolhidos; cancelar pede confirmação', (tester) async {
      final repo = FakeOrdersRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), orders: repo);
      await openTab(tester, 'Pedidos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      for (final s in OrderStatus.all) {
        expect(field('order_status_$s'), findsOneWidget);
      }
      for (final s in [OrderStatus.confirmado, OrderStatus.emProducao, OrderStatus.pronto, OrderStatus.entregue]) {
        await tapKey(tester, 'order_status_$s');
      }
      expect(repo.updates.map((u) => u.$2['status']).toList(),
          [OrderStatus.confirmado, OrderStatus.emProducao, OrderStatus.pronto, OrderStatus.entregue]);

      await tapKey(tester, 'order_status_${OrderStatus.cancelado}');
      expect(find.textContaining('Cancelar o pedido'), findsOneWidget);
      await tester.tap(find.text('Voltar'));
      await tester.pumpAndSettle();
      expect(repo.updates, hasLength(4)); // desistiu: nada gravado
      await tapKey(tester, 'order_status_${OrderStatus.cancelado}');
      await tester.tap(field('confirm_action'));
      await tester.pumpAndSettle();
      expect(repo.updates.last.$2, {'status': OrderStatus.cancelado});
      await tester.ensureVisible(find.text('Status: Entregue → Cancelado'));
    });

    testWidgets('editar envia só os campos alterados (valor final)', (tester) async {
      final repo = FakeOrdersRepository();
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), orders: repo);
      await openTab(tester, 'Pedidos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'order_edit');
      await tester.enterText(field('order_final_value'), '650,00');
      await tester.tap(field('order_edit_save'));
      await tester.pumpAndSettle();
      expect(repo.updates.single.$2, {'valor_final': 650.0});
      expect(find.textContaining('650,00'), findsOneWidget);
    });

    testWidgets('WhatsApp abre wa.me com mensagem e não diz que enviou', (tester) async {
      final opened = <Uri>[];
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), openedUrls: opened);
      await openTab(tester, 'Pedidos');
      await tester.tap(find.text('Ana Souza'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'whatsapp_open');
      expect(opened, hasLength(1));
      expect(opened.single.host, 'wa.me');
      expect(opened.single.path, '/5511987654321');
      expect(opened.single.queryParameters['text'], contains('PD-261121-XYZ789'));
      expect(opened.single.queryParameters['text'], startsWith('Olá, Ana! Aqui é da Kika Cakes'));
      expect(find.textContaining('enviad'), findsNothing);
    });

    testWidgets('pedido inexistente mostra erro', (tester) async {
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), orders: FakeOrdersRepository(items: []));
      await openTab(tester, 'Pedidos');
      expect(find.text('Nenhum pedido ainda'), findsOneWidget);
    });
  });
}
