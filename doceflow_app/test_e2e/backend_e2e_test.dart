// Ponta a ponta: os repositórios REAIS do app contra um Supabase de verdade (local), com as
// migrações 001–013, Auth, PostgREST, Storage e RLS. Não roda no `flutter test` normal.
//
// Uso (ver doceflow_app/README.md, "Teste ponta a ponta"):
//   flutter test test_e2e --dart-define=E2E_URL=... --dart-define=E2E_KEY=<publishable/anon> \
//     --dart-define=E2E_OWNER_EMAIL=... --dart-define=E2E_OWNER_PASS=... \
//     --dart-define=E2E_OTHER_EMAIL=... --dart-define=E2E_OTHER_PASS=... \
//     --dart-define=E2E_NOPROFILE_EMAIL=... --dart-define=E2E_NOPROFILE_PASS=...
//
// NUNCA aponte para produção: o teste cria e altera dados.
@Tags(['e2e'])
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/auth/data/supabase_auth_repository.dart';
import 'package:doceflow_app/features/auth/domain/admin_account.dart';
import 'package:doceflow_app/features/dashboard/data/dashboard_repository.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:doceflow_app/features/orders/data/orders_repository.dart';
import 'package:doceflow_app/features/orders/domain/order.dart';
import 'package:doceflow_app/features/products/data/products_repository.dart';
import 'package:doceflow_app/features/products/domain/product.dart';
import 'package:doceflow_app/features/quotes/data/quotes_repository.dart';
import 'package:doceflow_app/features/quotes/domain/quote.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

const url = String.fromEnvironment('E2E_URL');
const key = String.fromEnvironment('E2E_KEY');
const ownerEmail = String.fromEnvironment('E2E_OWNER_EMAIL');
const ownerPass = String.fromEnvironment('E2E_OWNER_PASS');
const otherEmail = String.fromEnvironment('E2E_OTHER_EMAIL');
const otherPass = String.fromEnvironment('E2E_OTHER_PASS');
const noProfileEmail = String.fromEnvironment('E2E_NOPROFILE_EMAIL');
const noProfilePass = String.fromEnvironment('E2E_NOPROFILE_PASS');

final jpeg = base64Decode(
    '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDQooopH6Kf/9k=');

SupabaseClient newClient() => SupabaseClient(url, key, authOptions: const AuthClientOptions(autoRefreshToken: false));

Matcher failureWith(String text) => isA<AppFailure>().having((f) => f.message, 'mensagem', contains(text));

/// O que o site público faz (visitante, chave publishable): orçamento e pedido pelas funções.
Future<String> publicLead(SupabaseClient anon, String phone, {String product = 'docinhos-tradicionais', String mode = 'Retirada'}) async {
  final rows = await anon.rpc('criar_lead', params: {
    'p_confeitaria_slug': 'kika-cakes',
    'p_produto_slug': product,
    'p_cliente_nome': 'Cliente Ponta a Ponta',
    'p_cliente_whatsapp': phone,
    'p_quantidade': 2,
    'p_data_desejada': DateTime.now().add(const Duration(days: 10)).toIso8601String().substring(0, 10),
    'p_modalidade': mode,
    'p_observacoes': 'teste e2e',
    'p_origem': 'e2e',
    'p_consentimento': true,
  }) as List;
  return (rows.first as Map)['id'] as String;
}

Future<String> publicOrder(SupabaseClient anon, String phone) async {
  final rows = await anon.rpc('criar_pedido', params: {
    'p_confeitaria_slug': 'kika-cakes',
    'p_cliente_nome': 'Cliente Pedido Site',
    'p_cliente_whatsapp': phone,
    'p_data_entrega': DateTime.now().add(const Duration(days: 12)).toIso8601String().substring(0, 10),
    'p_modalidade': 'Retirada',
    'p_observacoes': '',
    'p_itens': [
      {'produto_slug': 'bem-casado', 'quantidade': 50},
    ],
    'p_origem': 'e2e',
    'p_consentimento': true,
    'p_endereco_entrega': '',
  }) as List;
  return (rows.first as Map)['id'] as String;
}

void main() {
  if (url.isEmpty || key.isEmpty || ownerEmail.isEmpty) {
    test('configuração do teste ponta a ponta', () {}, skip: 'Sem E2E_URL/E2E_KEY/E2E_OWNER_*: teste ponta a ponta não configurado.');
    return;
  }
  if (url.contains('dfimrkfcudidosdldsjv')) {
    throw StateError('O teste ponta a ponta nunca roda contra o Supabase de produção.');
  }

  late SupabaseClient owner;
  late AdminAccount account;
  late ProductsRepository products;
  late QuotesRepository quotes;
  late OrdersRepository orders;
  late DashboardRepository dashboard;
  final anon = newClient();
  final stamp = DateTime.now().millisecondsSinceEpoch % 100000000;
  String phone(int n) => '55119${(stamp + n).toString().padLeft(8, '0')}';

  setUpAll(() async {
    owner = newClient();
    account = await SupabaseAuthRepository(owner, storeSlug: 'kika-cakes').signIn(email: ownerEmail, password: ownerPass);
    products = SupabaseProductsRepository(owner, storeId: account.storeId);
    quotes = SupabaseQuotesRepository(owner, storeId: account.storeId);
    orders = SupabaseOrdersRepository(owner, storeId: account.storeId);
    dashboard = SupabaseDashboardRepository(owner);
  });

  group('Login (Supabase Auth + perfil administrativo)', () {
    test('dona entra e o app descobre a confeitaria pelo perfil', () {
      expect((account.storeSlug, account.storeName, account.role), ('kika-cakes', 'Kika Cakes', 'proprietaria'));
    });

    test('senha errada', () async {
      await expectLater(
          SupabaseAuthRepository(newClient(), storeSlug: 'kika-cakes').signIn(email: ownerEmail, password: 'senha-errada-1'),
          throwsA(failureWith('E-mail ou senha incorretos')));
    });

    test('conta sem perfil administrativo não entra', () async {
      await expectLater(
          SupabaseAuthRepository(newClient(), storeSlug: 'kika-cakes').signIn(email: noProfileEmail, password: noProfilePass),
          throwsA(failureWith('não tem acesso')));
    });

    test('dona de OUTRA confeitaria não entra neste app', () async {
      await expectLater(
          SupabaseAuthRepository(newClient(), storeSlug: 'kika-cakes').signIn(email: otherEmail, password: otherPass),
          throwsA(failureWith('não tem acesso')));
    });
  });

  group('Produtos', () {
    test('lista real do catálogo', () async {
      final list = await products.list();
      expect(list, isNotEmpty);
      expect(list.any((p) => p.slug == 'bem-casado'), isTrue);
    });

    test('cadastro → slug pelo banco → edição → foto → principal → apagar foto → excluir', () async {
      const draft = ProductDraft(
          name: 'Bolo de Maçã E2E', category: 'Bolos', description: 'Teste', unit: 'kg', price: 80, priceType: priceFrom,
          available: true, published: false, featured: false, minQty: 1, maxQty: 5, productionDays: 2);
      final id = await products.create(draft);
      var p = await products.get(id);
      expect(p.slug, startsWith('bolo-de-maca-e2e'));
      expect(p.published, isFalse);

      await products.update(id, const ProductDraft(
          name: 'Bolo de Maçã E2E', category: 'Bolos', description: 'Teste', unit: 'kg', price: 95.5, priceType: priceEstimated,
          available: false, published: true, featured: true, minQty: 2, maxQty: 8, productionDays: 3));
      p = await products.get(id);
      expect((p.price, p.priceType, p.available, p.published, p.featured, p.minQty, p.maxQty, p.productionDays),
          (95.5, priceEstimated, false, true, true, 2, 8, 3));

      final a = await products.addImage(id, Uint8List.fromList(jpeg));
      final b = await products.addImage(id, Uint8List.fromList(jpeg));
      expect((a.principal, b.principal), (true, false));
      await products.setPrincipal(b.id);
      var imgs = await products.images(id);
      expect(imgs.firstWhere((i) => i.principal).id, b.id);
      await products.deleteImage(imgs.firstWhere((i) => i.principal));
      imgs = await products.images(id);
      expect(imgs.single.principal, isTrue); // a outra foi promovida

      await products.delete(id);
      await expectLater(products.get(id), throwsA(failureWith('não encontrado')));
    });

    test('validação do banco: quantidade máxima menor que a mínima é recusada', () async {
      const bad = ProductDraft(
          name: 'Inválido E2E', category: 'Bolos', description: '', unit: 'kg', price: 1, priceType: priceFrom,
          available: true, published: false, featured: false, minQty: 5, maxQty: 1, productionDays: null);
      await expectLater(products.create(bad), throwsA(failureWith('recusou os dados')));
    });

    test('produto com orçamento não pode ser excluído (o banco recusa)', () async {
      await publicLead(anon, phone(1));
      final p = (await products.list()).firstWhere((p) => p.slug == 'docinhos-tradicionais');
      await expectLater(products.delete(p.id), throwsA(failureWith('Despublique')));
      expect((await products.get(p.id)).id, p.id);
    });
  });

  group('Orçamentos e conversão', () {
    test('consulta, detalhe, status e conversão explícita (sem duplicar)', () async {
      final leadId = await publicLead(anon, phone(2));
      final list = await quotes.list(limit: 50);
      expect(list.any((q) => q.id == leadId), isTrue);
      expect((await quotes.list(status: QuoteStatus.perdido, limit: 50)).any((q) => q.id == leadId), isFalse);

      await quotes.updateStatus(leadId, QuoteStatus.emAtendimento);
      expect((await quotes.get(leadId)).status, QuoteStatus.emAtendimento);

      // dois toques ao mesmo tempo: o banco devolve o MESMO pedido
      final results = await Future.wait([
        quotes.convert(leadId, const ConversionInput(finalValue: 320, internalNotes: 'sinal pago')),
        quotes.convert(leadId, const ConversionInput(finalValue: 999)),
      ]);
      expect(results[0].orderId, results[1].orderId);
      expect(results.where((r) => r.created), hasLength(1));

      final q = await quotes.get(leadId);
      expect((q.status, q.orderId), (QuoteStatus.vendido, results[0].orderId));
      final o = await orders.get(results[0].orderId);
      expect(o.status, OrderStatus.confirmado);
      expect(o.leadId, leadId);
      expect(o.items.single.quantity, 2);
      expect(o.finalValue, anyOf(320.0, 999.0)); // valor do toque que chegou primeiro
    });

    test('entrega exige endereço; perdido não converte', () async {
      final delivery = await publicLead(anon, phone(3), mode: 'Entrega');
      await expectLater(quotes.convert(delivery, const ConversionInput()), throwsA(failureWith('endereço')));
      final r = await quotes.convert(delivery, const ConversionInput(address: 'Rua das Flores, 123, Centro'));
      expect((await orders.get(r.orderId)).address, 'Rua das Flores, 123, Centro');

      final lost = await publicLead(anon, phone(4));
      await quotes.updateStatus(lost, QuoteStatus.perdido);
      await expectLater(quotes.convert(lost, const ConversionInput()), throwsA(failureWith('Perdido')));
    });
  });

  group('Pedidos', () {
    test('pedido do site: itens, valores, os 6 status, edição e histórico', () async {
      final id = await publicOrder(anon, phone(5));
      var o = await orders.get(id);
      expect((o.status, o.estimatedValue, o.finalValue), (OrderStatus.aguardando, 300.0, null));
      expect(o.items.single.subtotal, 300.0);

      for (final s in [OrderStatus.confirmado, OrderStatus.emProducao, OrderStatus.pronto, OrderStatus.entregue, OrderStatus.cancelado, OrderStatus.aguardando]) {
        await orders.update(id, OrderUpdate(status: s));
        expect((await orders.get(id)).status, s);
      }
      final newDate = DateTime.now().add(const Duration(days: 20));
      await orders.update(id, OrderUpdate(finalValue: 350, deliveryDate: newDate, internalNotes: 'retirar às 15h'));
      o = await orders.get(id);
      expect((o.finalValue, o.internalNotes, o.estimatedValue), (350.0, 'retirar às 15h', 300.0));

      final h = await orders.history(id);
      expect(h.first.field, 'criado');
      expect(h.first.byAdmin, isFalse); // criado pela cliente no site
      expect(h.where((e) => e.field == 'status'), hasLength(6));
      expect(h.where((e) => e.field == 'status').every((e) => e.byAdmin), isTrue);
      expect(h.map((e) => e.field).toSet(), containsAll(['valor_final', 'data_entrega', 'observacoes_internas']));

      final filtered = await orders.list(status: OrderStatus.aguardando, limit: 100);
      expect(filtered.every((x) => x.status == OrderStatus.aguardando), isTrue);
      expect((await orders.list(limit: 1)), hasLength(1)); // paginação
    });

    test('confirmar um pedido do site', () async {
      final id = await publicOrder(anon, phone(6));
      await orders.update(id, const OrderUpdate(status: OrderStatus.confirmado));
      expect((await orders.get(id)).status, OrderStatus.confirmado);
    });
  });

  group('Dashboard', () {
    test('indicadores reais, com estimado e final separados', () async {
      final all = await dashboard.load(DashboardPeriod.all);
      final week = await dashboard.load(DashboardPeriod.last7);
      expect(all.quotesTotal, greaterThanOrEqualTo(week.quotesTotal));
      expect(week.quotesTotal, greaterThan(0));
      expect(week.ordersTotal, greaterThan(0));
      expect(week.finalValue, greaterThan(0));
      expect(week.registeredValue, greaterThan(0));
    });
  });

  group('Permissões no backend', () {
    test('dona de outra confeitaria não vê nem altera nada da Kika', () async {
      final leadId = await publicLead(anon, phone(7));
      final orderId = await publicOrder(anon, phone(8));
      final other = newClient();
      await other.auth.signInWithPassword(email: otherEmail, password: otherPass);
      final otherQuotes = SupabaseQuotesRepository(other, storeId: account.storeId); // tenta com o id da Kika
      final otherOrders = SupabaseOrdersRepository(other, storeId: account.storeId);
      expect(await otherQuotes.list(limit: 100), isEmpty);
      expect(await otherOrders.list(limit: 100), isEmpty);
      await expectLater(otherOrders.update(orderId, const OrderUpdate(status: OrderStatus.cancelado)), throwsA(failureWith('não encontrado')));
      await expectLater(otherQuotes.updateStatus(leadId, QuoteStatus.perdido), throwsA(failureWith('não encontrado')));
      await expectLater(otherQuotes.convert(leadId, const ConversionInput()), throwsA(failureWith('não encontrado')));
      final otherProducts = SupabaseProductsRepository(other, storeId: account.storeId);
      await expectLater(
          otherProducts.create(const ProductDraft(
              name: 'Invasão', category: 'Bolos', description: '', unit: 'kg', price: 1, priceType: priceFrom,
              available: true, published: true, featured: false, minQty: 1, maxQty: 1, productionDays: null)),
          throwsA(isA<AppFailure>()));
      expect((await orders.get(orderId)).status, OrderStatus.aguardando); // nada mudou
      await other.auth.signOut();
    });

    test('visitante (sem login) não lê orçamentos nem pedidos', () async {
      await expectLater(SupabaseQuotesRepository(anon, storeId: account.storeId).list(limit: 10), throwsA(isA<AppFailure>()));
      await expectLater(SupabaseOrdersRepository(anon, storeId: account.storeId).list(limit: 10), throwsA(isA<AppFailure>()));
      await expectLater(anon.rpc('painel_indicadores'), throwsA(isA<PostgrestException>()));
    });

    test('depois de sair, a sessão não vale mais', () async {
      final c = newClient();
      final acc = await SupabaseAuthRepository(c, storeSlug: 'kika-cakes').signIn(email: ownerEmail, password: ownerPass);
      await SupabaseAuthRepository(c, storeSlug: 'kika-cakes').signOut();
      await expectLater(SupabaseOrdersRepository(c, storeId: acc.storeId).list(limit: 5), throwsA(isA<AppFailure>()));
    });
  });
}
