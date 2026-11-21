// Auditoria de telas: todas as telas do app em vários tamanhos de Android e com a fonte
// ampliada do sistema (acessibilidade). Falha se houver estouro de layout ou qualquer exceção.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fakes.dart';

const sizes = {
  'pequeno 320×568': Size(320, 568),
  'comum 360×640': Size(360, 640),
  'médio 393×873': Size(393, 873),
  'grande 412×915': Size(412, 915),
  'tablet 7" 600×960': Size(600, 960),
  'tablet 10" 800×1280': Size(800, 1280),
  'deitado 915×412': Size(915, 412),
};

Future<void> go(WidgetTester tester, String tab) async {
  await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(tab)));
  await tester.pumpAndSettle();
}

Future<void> tapIn(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

Future<void> visitAll(WidgetTester tester, List<String> visited) async {
  void check(String name) {
    final e = tester.takeException();
    expect(e, isNull, reason: 'Erro na tela "$name": $e');
    visited.add(name);
  }

  check('Início');
  await tester.drag(find.byType(Scrollable).first, const Offset(0, -2000));
  await tester.pumpAndSettle();
  check('Início (rolado)');

  await go(tester, 'Orçamentos');
  check('Orçamentos');
  await tapIn(tester, find.text('Ana Souza').first);
  check('Orçamento (detalhe)');
  await tester.tap(find.byType(BackButton));
  await tester.pumpAndSettle();

  await go(tester, 'Pedidos');
  check('Pedidos');
  await tapIn(tester, find.text('Ana Souza').first);
  check('Pedido (detalhe)');
  await tester.tap(find.byType(BackButton));
  await tester.pumpAndSettle();

  await go(tester, 'Produtos');
  check('Produtos');
  await tapIn(tester, find.text('Bolo de Pote').first);
  check('Produto (edição)');
  await tester.tap(find.byType(BackButton));
  await tester.pumpAndSettle();

  await go(tester, 'Marketing');
  check('Marketing · Criar');
  for (final tab in ['Posts', 'Instagram']) {
    await tester.tap(find.descendant(of: find.byType(TabBar), matching: find.text(tab)));
    await tester.pumpAndSettle();
    check('Marketing · $tab');
  }
  await tester.tap(find.descendant(of: find.byType(TabBar), matching: find.text('Posts')));
  await tester.pumpAndSettle();
  await tapIn(tester, field('post_m1'));
  check('Post (detalhe)');
  await tester.tap(find.byType(BackButton));
  await tester.pumpAndSettle();

  await go(tester, 'Início');
  await tapIn(tester, field('open_profile'));
  check('Perfil');
}

void main() {
  setUp(() => WidgetController.hitTestWarningShouldBeFatal = true); // toque perdido = falha
  tearDown(() => WidgetController.hitTestWarningShouldBeFatal = false);

  for (final scale in [1.0, 1.3, 2.0]) {
    for (final entry in sizes.entries) {
      testWidgets('todas as telas: ${entry.key}, fonte ${scale}x', (tester) async {
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await pumpApp(
          tester,
          auth: FakeAuthRepository(saved: testAccount),
          marketing: FakeMarketingApi(posts: [mpost()]),
          instagram: FakeInstagramRepository(pubs: [publication(status: 'falhou', error: 'A Meta recusou a imagem.')]),
          size: entry.value,
        );
        final visited = <String>[];
        await visitAll(tester, visited);
        expect(visited, hasLength(13));
      });
    }
    testWidgets('login e nova senha: fonte ${scale}x em 320×568', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await pumpApp(tester, auth: FakeAuthRepository(), size: const Size(320, 568));
      expect(tester.takeException(), isNull);
      await tester.ensureVisible(find.text('Esqueceu a senha?'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Esqueceu a senha?'));
      await tester.pumpAndSettle();
      expect(find.text('Nova senha'), findsWidgets);
      expect(tester.takeException(), isNull);
    });
  }
}
