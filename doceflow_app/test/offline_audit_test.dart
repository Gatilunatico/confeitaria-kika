// Auditoria: sem internet e sessão vencida. Nenhuma tela pode ficar em branco, travar ou
// mostrar detalhe técnico; todas explicam e oferecem "Tentar de novo".
import 'dart:typed_data';

import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:doceflow_app/features/marketing/domain/marketing.dart';
import 'package:doceflow_app/features/orders/domain/order.dart';
import 'package:doceflow_app/features/products/domain/product.dart';
import 'package:doceflow_app/features/quotes/domain/quote.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fakes.dart';

const offline = AppFailure(offlineMessage, kind: FailureKind.offline);

/// Interruptor de rede compartilhado pelos repositórios falsos.
class Net {
  bool up = false;
  Future<void> check() async {
    if (!up) throw offline;
  }
}

class OfflineDashboard extends FakeDashboardRepository {
  OfflineDashboard(this.net);
  final Net net;
  @override
  Future<DashboardIndicators> load(DashboardPeriod period) async {
    await net.check();
    return super.load(period);
  }
}

class OfflineProducts extends FakeProductsRepository {
  OfflineProducts(this.net);
  final Net net;
  @override
  Future<List<Product>> list() async {
    await net.check();
    return super.list();
  }
}

class OfflineQuotes extends FakeQuotesRepository {
  OfflineQuotes(this.net);
  final Net net;
  @override
  Future<List<Quote>> list({String? status, required int limit}) async {
    await net.check();
    return super.list(status: status, limit: limit);
  }
}

class OfflineOrders extends FakeOrdersRepository {
  OfflineOrders(this.net);
  final Net net;
  @override
  Future<List<Order>> list({String? status, required int limit}) async {
    await net.check();
    return super.list(status: status, limit: limit);
  }
}

class OfflineMarketing extends FakeMarketingApi {
  OfflineMarketing(this.net) : super(posts: [mpost()]);
  final Net net;
  @override
  Future<({List<MarketingPost> items, int total})> list({int page = 1, int limit = 20}) async {
    await net.check();
    return super.list(page: page, limit: limit);
  }

  @override
  Future<Uint8List> image(String postId) async {
    await net.check();
    return super.image(postId);
  }
}

class OfflineInstagram extends FakeInstagramRepository {
  OfflineInstagram(this.net);
  final Net net;
  @override
  Future<InstagramAccount> account() async {
    await net.check();
    return super.account();
  }

  @override
  Future<List<Publication>> publications({required int limit}) async {
    await net.check();
    return super.publications(limit: limit);
  }
}

Future<void> go(WidgetTester tester, String tab) async {
  await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(tab)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('sem internet: todas as listas explicam e voltam ao "Tentar de novo"', (tester) async {
    final net = Net();
    await pumpApp(
      tester,
      auth: FakeAuthRepository(saved: testAccount),
      dashboard: OfflineDashboard(net),
      products: OfflineProducts(net),
      quotes: OfflineQuotes(net),
      orders: OfflineOrders(net),
      marketing: OfflineMarketing(net),
      instagram: OfflineInstagram(net),
    );
    expect(find.text(offlineMessage), findsOneWidget); // Início
    for (final tab in ['Orçamentos', 'Pedidos', 'Produtos']) {
      await go(tester, tab);
      expect(find.text(offlineMessage), findsOneWidget, reason: tab);
      expect(find.text('Tentar de novo'), findsOneWidget, reason: tab);
    }
    await go(tester, 'Marketing');
    for (final t in ['Posts', 'Instagram']) {
      await tester.tap(find.descendant(of: find.byType(TabBar), matching: find.text(t)));
      await tester.pumpAndSettle();
      expect(find.text(offlineMessage), findsWidgets, reason: t);
    }
    expect(find.textContaining('Exception'), findsNothing);
    expect(find.textContaining('Socket'), findsNothing);

    // a internet volta: "Tentar de novo" carrega os dados reais
    net.up = true;
    await go(tester, 'Pedidos');
    await tester.tap(find.text('Tentar de novo'));
    await tester.pumpAndSettle();
    expect(find.text('Ana Souza'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('sessão vencida no meio do uso: volta ao login com aviso, sem dados na tela', (tester) async {
    final auth = FakeAuthRepository(saved: testAccount);
    await pumpApp(tester, auth: auth);
    await go(tester, 'Pedidos');
    expect(find.text('Ana Souza'), findsOneWidget);
    auth.endSession();
    await tester.pumpAndSettle();
    expect(find.text('Entrar no painel'), findsOneWidget);
    expect(find.text('Sua sessão terminou. Entre novamente.'), findsOneWidget);
    expect(find.text('Ana Souza'), findsNothing);
  });

  testWidgets('ação com rede caindo: mensagem clara e nada marcado como feito', (tester) async {
    final orders = _FailingUpdates();
    await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount), orders: orders);
    await go(tester, 'Pedidos');
    await tester.tap(find.text('Ana Souza'));
    await tester.pumpAndSettle();
    final chip = find.byKey(Key('order_status_${OrderStatus.confirmado}'));
    await tester.ensureVisible(chip);
    await tester.pumpAndSettle();
    await tester.tap(chip);
    await tester.pumpAndSettle();
    expect(find.text(offlineMessage), findsOneWidget); // aviso
    expect(find.textContaining('Status alterado'), findsNothing);
    expect(orders.items.single.status, OrderStatus.aguardando);
  });
}

class _FailingUpdates extends FakeOrdersRepository {
  @override
  Future<void> update(String id, OrderUpdate update) async => throw offline;
}
