import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fakes.dart';

void main() {
  testWidgets('Início mostra os indicadores reais do repositório', (tester) async {
    final dash = FakeDashboardRepository();
    await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), dashboard: dash);
    expect(find.text('Novos'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('25,0%'), findsOneWidget);
    expect(find.textContaining('1.234,50'), findsOneWidget);
    expect(dash.calls, [DashboardPeriod.last30]);
  });

  testWidgets('trocar o período recarrega', (tester) async {
    final dash = FakeDashboardRepository();
    await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), dashboard: dash);
    await tester.tap(find.text('7 dias'));
    await tester.pumpAndSettle();
    expect(dash.calls.last, DashboardPeriod.last7);
  });

  testWidgets('erro ao carregar mostra mensagem e botão de tentar de novo', (tester) async {
    final dash = FakeDashboardRepository(error: const AppFailure(offlineMessage, kind: FailureKind.offline));
    await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), dashboard: dash);
    expect(find.text(offlineMessage), findsOneWidget);
    dash.error = null;
    await tester.tap(find.text('Tentar de novo'));
    await tester.pumpAndSettle();
    expect(find.text('Novos'), findsOneWidget);
  });

  for (final size in const [Size(320, 640), Size(412, 915), Size(915, 412)]) {
    testWidgets('layout sem estouro em ${size.width.toInt()}×${size.height.toInt()}', (tester) async {
      await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), size: size);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Perfil'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('login sem estouro em tela pequena', (tester) async {
    await pumpApp(tester, auth: FakeAuthRepository(), size: const Size(320, 568));
    expect(tester.takeException(), isNull);
  });
}
