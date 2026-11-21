// Integração app ↔ página pública, em duas fases intercaladas com a vitrine (Python):
//   app1 (este arquivo) → site1 (doceflow/tests_e2e/test_vitrine_integracao.py) → app2 → site2
// Mesmo Supabase local, mesmo E2E_STAMP. Ver doceflow/docs/evidencias/auditoria_app/.
@Tags(['e2e'])
library;

import 'dart:convert';
import 'dart:typed_data';

import 'package:doceflow_app/features/auth/data/supabase_auth_repository.dart';
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
const email = String.fromEnvironment('E2E_OWNER_EMAIL');
const pass = String.fromEnvironment('E2E_OWNER_PASS');
const phase = String.fromEnvironment('E2E_PHASE');
const stamp = String.fromEnvironment('E2E_STAMP');

ProductDraft draft(String name, {required bool published}) => ProductDraft(
    name: name, category: 'Integração', description: 'Criado pelo app', unit: 'unidade', price: 42.5,
    priceType: priceFrom, available: true, published: published, featured: true, minQty: 1, maxQty: 10,
    productionDays: 3);

void main() {
  if (url.isEmpty || phase.isEmpty || stamp.isEmpty) {
    test('integração com a vitrine', () {}, skip: 'Sem E2E_URL/E2E_PHASE/E2E_STAMP.');
    return;
  }
  if (url.contains('dfimrkfcudidosdldsjv')) throw StateError('Nunca contra produção.');

  late ProductsRepository products;
  late QuotesRepository quotes;
  late OrdersRepository orders;

  setUpAll(() async {
    final client = SupabaseClient(url, key, authOptions: const AuthClientOptions(autoRefreshToken: false));
    final acc = await SupabaseAuthRepository(client, storeSlug: 'kika-cakes').signIn(email: email, password: pass);
    products = SupabaseProductsRepository(client, storeId: acc.storeId);
    quotes = SupabaseQuotesRepository(client, storeId: acc.storeId);
    orders = SupabaseOrdersRepository(client, storeId: acc.storeId);
  });

  test('app1: dona cadastra produto publicado com foto e outro oculto', () async {
    if (phase != 'app1') return;
    final id = await products.create(draft('Integração $stamp', published: true));
    await products.addImage(id, Uint8List.fromList(base64Decode('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDQooopH6Kf/9k=')));
    await products.create(draft('Oculto $stamp', published: false));
    expect((await products.images(id)).single.principal, isTrue);
  });

  test('app2: pedido e orçamento do site chegam ao app; dona converte, confirma e despublica', () async {
    if (phase != 'app2') return;
    final q = (await quotes.list(limit: 100)).firstWhere((x) => x.customerName == 'Cliente Site $stamp');
    expect((q.productName, q.quantity, q.status), ('Integração $stamp', 2, QuoteStatus.novo));
    final conv = await quotes.convert(q.id, const ConversionInput(finalValue: 90));
    expect(conv.created, isTrue);

    final o = (await orders.list(limit: 100)).firstWhere((x) => x.customerName == 'Pedido Site $stamp');
    expect(o.status, OrderStatus.aguardando);
    expect(o.items.single.name, 'Integração $stamp');
    expect(o.estimatedValue, 42.5 * 3); // preço calculado pelo banco a partir do cadastro feito no app
    await orders.update(o.id, const OrderUpdate(status: OrderStatus.confirmado, finalValue: 130));

    final p = (await products.list()).firstWhere((x) => x.name == 'Integração $stamp');
    await products.update(p.id, draft('Integração $stamp', published: false));
  });
}
