import 'dart:async';
import 'dart:typed_data';

import 'package:doceflow_app/app.dart';
import 'package:doceflow_app/core/whatsapp.dart';
import 'package:doceflow_app/features/orders/data/orders_repository.dart';
import 'package:doceflow_app/features/orders/domain/order.dart';
import 'package:doceflow_app/features/products/data/image_preparer.dart';
import 'package:doceflow_app/features/products/data/products_repository.dart';
import 'package:doceflow_app/features/products/domain/product.dart';
import 'package:doceflow_app/features/quotes/data/quotes_repository.dart';
import 'package:doceflow_app/features/quotes/domain/quote.dart';
import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/auth/application/auth_controller.dart';
import 'package:doceflow_app/features/auth/domain/admin_account.dart';
import 'package:doceflow_app/features/dashboard/data/dashboard_repository.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Conta usada SÓ nos testes (nunca entra no app de produção).
const testAccount = AdminAccount(
  userId: '00000000-0000-0000-0000-00000000000a',
  email: 'dona@teste.dev',
  storeId: '00000000-0000-0000-0000-0000000000c1',
  storeName: 'Kika Cakes',
  storeSlug: 'kika-cakes',
  role: 'proprietaria',
);

class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository({this.saved, this.restoreError});

  AdminAccount? saved; // sessão "guardada no aparelho"
  Object? restoreError;
  String password = 'senha-certa-123';
  bool noAccess = false;
  int signInCalls = 0;
  int signOutCalls = 0;
  final List<String> recoveryEmails = [];
  final List<(String, String, String)> resets = [];
  final _ended = StreamController<void>.broadcast();

  void endSession() => _ended.add(null);

  @override
  Stream<void> get sessionEnded => _ended.stream;

  @override
  Future<AdminAccount?> restoreSession() async {
    if (restoreError != null) throw restoreError!;
    return saved;
  }

  @override
  Future<AdminAccount> signIn({required String email, required String password}) async {
    signInCalls++;
    if (password != this.password) {
      throw const AppFailure('E-mail ou senha incorretos.', kind: FailureKind.invalidCredentials);
    }
    if (noAccess) {
      throw const AppFailure('Esta conta não tem acesso ao painel da confeitaria.', kind: FailureKind.noAccess);
    }
    saved = testAccount;
    return testAccount;
  }

  @override
  Future<void> sendRecoveryEmail(String email) async => recoveryEmails.add(email);

  @override
  Future<void> resetPasswordWithCode({required String email, required String code, required String newPassword}) async {
    if (code != '123456') throw const AppFailure('Código inválido ou vencido. Peça um novo código.');
    resets.add((email, code, newPassword));
  }

  @override
  Future<void> changePassword(String newPassword) async => password = newPassword;

  @override
  Future<void> signOut() async {
    signOutCalls++;
    saved = null;
  }
}

class FakeDashboardRepository implements DashboardRepository {
  FakeDashboardRepository({this.error});

  Object? error;
  final List<DashboardPeriod> calls = [];

  @override
  Future<DashboardIndicators> load(DashboardPeriod period) async {
    calls.add(period);
    if (error != null) throw error!;
    return const DashboardIndicators(
      quotesTotal: 8,
      quotesNew: 3,
      quotesSold: 2,
      conversionRate: 0.25,
      ordersTotal: 5,
      ordersWaiting: 1,
      ordersInProgress: 2,
      registeredValue: 1234.5,
      deliveriesNext7Days: 4,
    );
  }
}

Future<void> pumpApp(
  WidgetTester tester, {
  required FakeAuthRepository auth,
  FakeDashboardRepository? dashboard,
  FakeProductsRepository? products,
  FakeQuotesRepository? quotes,
  FakeOrdersRepository? orders,
  FakePhotoPicker? picker,
  List<Uri>? openedUrls,
  Size size = const Size(390, 844), // celular comum
}) async {
  tester.view.physicalSize = size * tester.view.devicePixelRatio;
  addTearDown(tester.view.resetPhysicalSize);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(auth),
        dashboardRepositoryProvider.overrideWithValue(dashboard ?? FakeDashboardRepository()),
        productsRepositoryProvider.overrideWithValue(products ?? FakeProductsRepository()),
        quotesRepositoryProvider.overrideWithValue(quotes ?? FakeQuotesRepository()),
        ordersRepositoryProvider.overrideWithValue(orders ?? FakeOrdersRepository()),
        photoPickerProvider.overrideWithValue(picker ?? FakePhotoPicker()),
        urlOpenerProvider.overrideWithValue((uri) async {
          openedUrls?.add(uri);
          return true;
        }),
      ],
      child: const DoceFlowApp(),
    ),
  );
  await tester.pumpAndSettle();
}

Finder field(String key) => find.byKey(Key(key));

/// Atraso para os testes conseguirem tocar duas vezes enquanto a operação ainda roda.
Future<void> _slow() => Future.delayed(const Duration(milliseconds: 50));

Product product({String id = 'p1', String name = 'Bolo de Pote', bool published = true, bool available = true}) => Product(
      id: id,
      slug: id,
      name: name,
      category: 'Bolos',
      description: 'Cremoso.',
      unit: 'unidade',
      price: 12,
      priceType: priceFrom,
      available: available,
      published: published,
      featured: false,
      minQty: 1,
      maxQty: 50,
      order: 1,
      productionDays: 2,
    );

class FakeProductsRepository implements ProductsRepository {
  FakeProductsRepository({List<Product>? items, this.inUse = const {}}) : items = items ?? [product()];

  final List<Product> items;
  final Set<String> inUse; // produtos com orçamento/pedido: o banco recusa excluir
  final Map<String, List<ProductImage>> imgs = {};
  final List<ProductDraft> created = [];
  final List<(String, ProductDraft)> updated = [];
  final List<String> deleted = [];
  final List<Uint8List> uploads = [];
  final List<String> principals = [];
  final List<String> deletedImages = [];

  @override
  Future<List<Product>> list() async => List.of(items);

  @override
  Future<Product> get(String id) async =>
      items.firstWhere((p) => p.id == id, orElse: () => throw const AppFailure('Produto não encontrado nesta confeitaria.'));

  @override
  Future<String> create(ProductDraft draft) async {
    await _slow();
    created.add(draft);
    final id = 'novo${created.length}';
    items.add(product(id: id, name: draft.name));
    return id;
  }

  @override
  Future<void> update(String id, ProductDraft draft) async {
    await _slow();
    updated.add((id, draft));
  }

  @override
  Future<void> delete(String id) async {
    await _slow();
    if (inUse.contains(id)) {
      throw const AppFailure('Este produto tem orçamentos ou pedidos registrados e não pode ser excluído. '
          'Despublique-o para tirá-lo da vitrine.');
    }
    deleted.add(id);
    items.removeWhere((p) => p.id == id);
  }

  @override
  Future<List<ProductImage>> images(String productId) async => List.of(imgs[productId] ?? const []);

  @override
  Future<ProductImage> addImage(String productId, Uint8List jpeg) async {
    await _slow();
    uploads.add(jpeg);
    final list = imgs.putIfAbsent(productId, () => []);
    final n = uploads.length;
    final img = ProductImage(id: 'img$n', path: 's/$productId/img$n.jpg', url: '', principal: list.isEmpty, order: list.length + 1);
    list.add(img);
    return img;
  }

  @override
  Future<void> setPrincipal(String imageId) async => principals.add(imageId);

  @override
  Future<void> deleteImage(ProductImage image) async {
    deletedImages.add(image.id);
    for (final l in imgs.values) {
      l.removeWhere((i) => i.id == image.id);
    }
  }
}

class FakePhotoPicker implements PhotoPicker {
  FakePhotoPicker({this.result});

  Uint8List? result; // null = cancelou
  final List<PhotoSource> calls = [];

  @override
  Future<Uint8List?> pick(PhotoSource source) async {
    calls.add(source);
    return result;
  }
}

Quote quote({String id = 'q1', String status = QuoteStatus.novo, String fulfillment = 'Retirada', String? orderId}) => Quote(
      id: id,
      protocol: 'DF-261121-ABC123',
      createdAt: DateTime.utc(2026, 11, 21, 15),
      status: status,
      customerName: 'Ana Souza',
      whatsapp: '5511987654321',
      productName: 'Bolo de Pote',
      quantity: 10,
      unit: 'unidade',
      desiredDate: DateTime.now().add(const Duration(days: 10)),
      fulfillment: fulfillment,
      notes: 'Sem lactose',
      origin: 'instagram',
      orderId: orderId,
    );

class FakeQuotesRepository implements QuotesRepository {
  FakeQuotesRepository({List<Quote>? items}) : items = items ?? [quote()];

  List<Quote> items;
  final List<(String?, int)> listCalls = [];
  final List<(String, String)> statusUpdates = [];
  final List<(String, ConversionInput)> conversions = [];

  @override
  Future<List<Quote>> list({String? status, required int limit}) async {
    listCalls.add((status, limit));
    return items.where((q) => status == null || q.status == status).take(limit).toList();
  }

  @override
  Future<Quote> get(String id) async => items.firstWhere((q) => q.id == id);

  @override
  Future<void> updateStatus(String id, String status) async {
    await _slow();
    statusUpdates.add((id, status));
    items = [
      for (final q in items) q.id == id ? quote(id: id, status: status, fulfillment: q.fulfillment, orderId: q.orderId) : q
    ];
  }

  @override
  Future<ConversionResult> convert(String id, ConversionInput input) async {
    await _slow();
    final q = items.firstWhere((x) => x.id == id);
    if (q.fulfillment == 'Entrega' && input.address.trim().length < 10) {
      throw const AppFailure('Informe o endereço de entrega (pelo menos 10 caracteres).');
    }
    conversions.add((id, input));
    final created = q.orderId == null;
    items = [
      for (final x in items)
        x.id == id ? quote(id: id, status: QuoteStatus.vendido, fulfillment: x.fulfillment, orderId: 'o1') : x
    ];
    return ConversionResult(orderId: 'o1', protocol: 'PD-261121-XYZ789', created: created);
  }
}

Order order({String id = 'o1', String status = OrderStatus.aguardando, double? finalValue}) => Order(
      id: id,
      protocol: 'PD-261121-XYZ789',
      createdAt: DateTime.utc(2026, 11, 21, 15),
      status: status,
      customerName: 'Ana Souza',
      whatsapp: '5511987654321',
      deliveryDate: DateTime.now().add(const Duration(days: 10)),
      fulfillment: 'Entrega',
      address: 'Rua das Flores, 123',
      notes: 'Sem lactose',
      internalNotes: '',
      estimatedValue: 600,
      finalValue: finalValue,
      origin: 'site',
      leadId: null,
      items: const [
        OrderItem(name: 'Bem-casado', unit: 'unidade', quantity: 50, unitPrice: 6, subtotal: 300, priceType: 'a_partir_de'),
        OrderItem(name: 'Docinhos', unit: 'cento', quantity: 2, unitPrice: 150, subtotal: 300, priceType: 'a_partir_de'),
      ],
    );

class FakeOrdersRepository implements OrdersRepository {
  FakeOrdersRepository({List<Order>? items}) : items = items ?? [order()];

  List<Order> items;
  final List<(String?, int)> listCalls = [];
  final List<(String, Map<String, dynamic>)> updates = [];
  final List<HistoryEntry> hist = [
    HistoryEntry(field: 'criado', before: null, after: 'Aguardando confirmação', byAdmin: false, at: DateTime.utc(2026, 11, 21, 15)),
  ];

  @override
  Future<List<Order>> list({String? status, required int limit}) async {
    listCalls.add((status, limit));
    return items.where((o) => status == null || o.status == status).take(limit).toList();
  }

  @override
  Future<Order> get(String id) async =>
      items.firstWhere((o) => o.id == id, orElse: () => throw const AppFailure('Pedido não encontrado nesta confeitaria.'));

  @override
  Future<List<HistoryEntry>> history(String id) async => List.of(hist);

  @override
  Future<void> update(String id, OrderUpdate update) async {
    await _slow();
    final cols = update.toColumns();
    updates.add((id, cols));
    final o = items.firstWhere((x) => x.id == id);
    if (cols.containsKey('status')) {
      hist.add(HistoryEntry(
          field: 'status', before: o.status, after: cols['status'] as String, byAdmin: true, at: DateTime.now().toUtc()));
    }
    items = [
      for (final x in items)
        x.id == id
            ? order(
                id: id,
                status: (cols['status'] as String?) ?? x.status,
                finalValue: cols.containsKey('valor_final') ? (cols['valor_final'] as num?)?.toDouble() : x.finalValue)
            : x
    ];
  }
}
