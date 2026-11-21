// Contrato com o backend: os repositórios REAIS (Supabase) conversando com um servidor falso.
// Confere exatamente o que sai do app: tabela, filtros, colunas, funções e ordem das operações.
import 'dart:convert';
import 'dart:typed_data';

import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/dashboard/data/dashboard_repository.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:doceflow_app/features/marketing/data/instagram_repository.dart';
import 'package:doceflow_app/features/marketing/data/marketing_api.dart';
import 'package:doceflow_app/features/marketing/domain/marketing.dart';
import 'package:doceflow_app/features/orders/data/orders_repository.dart';
import 'package:doceflow_app/features/orders/domain/order.dart';
import 'package:doceflow_app/features/products/data/products_repository.dart';
import 'package:doceflow_app/features/products/domain/product.dart';
import 'package:doceflow_app/features/quotes/data/quotes_repository.dart';
import 'package:doceflow_app/features/quotes/domain/quote.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

const store = '00000000-0000-0000-0000-0000000000c1';
const prod = '00000000-0000-0000-0000-0000000000p1';

class Call {
  Call(this.method, this.url, this.body);
  final String method;
  final Uri url;
  final String body;

  String get path => url.path;
  Map<String, String> get q => url.queryParameters;
  dynamic get json => body.isEmpty ? null : jsonDecode(body);
}

typedef Responder = http.Response Function(Call c);

(SupabaseClient, List<Call>) server(Responder respond) {
  final calls = <Call>[];
  final client = SupabaseClient(
    'https://teste.supabase.co',
    'sb_publishable_teste',
    httpClient: MockClient((req) async {

      final text = utf8.decode(req.bodyBytes, allowMalformed: true); // upload de foto é binário
      final c = Call(req.method, req.url, req.url.path.contains('/storage/') && req.method == 'POST' ? '' : text);
      calls.add(c);
      final r = respond(c);
      return http.Response.bytes(r.bodyBytes, r.statusCode, headers: r.headers, request: req);
    }),
  );
  return (client, calls);
}

http.Response ok(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json; charset=utf-8'});

http.Response pgError(String code, String message, [int status = 400]) =>
    ok({'code': code, 'message': message, 'details': null, 'hint': null}, status);

const draft = ProductDraft(
  name: 'Bolo de Cenoura',
  category: 'Bolos',
  description: '',
  unit: 'kg',
  price: 85.5,
  priceType: priceFrom,
  available: true,
  published: false,
  featured: false,
  minQty: 1,
  maxQty: 10,
  productionDays: 3,
);

Map<String, dynamic> orderRow({String status = 'Aguardando confirmação'}) => {
      'id': 'o1',
      'protocolo': 'PD-1',
      'created_at': '2026-11-21T15:00:00+00:00',
      'status': status,
      'cliente_nome': 'Ana',
      'cliente_whatsapp': '5511987654321',
      'data_entrega': '2026-12-01',
      'modalidade': 'Retirada',
      'endereco_entrega': '',
      'observacoes': '',
      'observacoes_internas': '',
      'valor_estimado': 600,
      'valor_final': null,
      'origem': 'site',
      'lead_id': null,
      'order_items': [
        {'produto_nome': 'Bem-casado', 'unidade': 'un', 'quantidade': 50, 'preco_unitario': 6, 'subtotal': 300, 'tipo_preco': 'a_partir_de'}
      ],
    };

void main() {
  group('Produtos', () {
    test('cadastro envia a confeitaria e NÃO envia slug (o banco gera)', () async {
      final (client, calls) = server((c) => ok({'id': prod}, 201)); // .single(): objeto
      final id = await SupabaseProductsRepository(client, storeId: store).create(draft);
      expect(id, prod);
      final c = calls.single;
      expect((c.method, c.path), ('POST', '/rest/v1/produtos'));
      final body = c.json is List ? (c.json as List).single : c.json;
      expect(body['confeitaria_id'], store);
      expect(body.containsKey('slug'), isFalse);
      expect(body['publicado'], isFalse);
      expect(body['preco'], 85.5);
    });

    test('edição manda só colunas editáveis, filtrando por id e confeitaria', () async {
      final (client, calls) = server((c) => ok([{'id': prod}]));
      await SupabaseProductsRepository(client, storeId: store).update(prod, draft);
      final c = calls.single;
      expect(c.method, 'PATCH');
      expect(c.q['id'], 'eq.$prod');
      expect(c.q['confeitaria_id'], 'eq.$store');
      expect((c.json as Map).keys.toSet(), {
        'nome', 'categoria', 'descricao', 'unidade', 'preco', 'tipo_preco', 'disponivel', 'publicado', 'destaque',
        'qtd_min', 'qtd_max', 'prazo_producao_dias'
      });
    });

    test('sob consulta grava preço vazio', () {
      const d = ProductDraft(
          name: 'X', category: 'Bolos', description: '', unit: 'kg', price: 10, priceType: priceOnRequest,
          available: true, published: true, featured: false, minQty: 1, maxQty: 1, productionDays: null);
      expect(d.toColumns()['preco'], isNull);
    });

    test('excluir produto com pedidos: o banco recusa (23503) e nada sai do Storage', () async {
      final (client, calls) = server((c) {
        if (c.path.endsWith('/product_images')) return ok([{'id': 'i1', 'produto_id': prod, 'storage_path': '$store/$prod/i1.jpg', 'principal': true, 'ordem': 1}]);
        return pgError('23503', 'update or delete on table "produtos" violates foreign key constraint', 409);
      });
      await expectLater(
        SupabaseProductsRepository(client, storeId: store).delete(prod),
        throwsA(isA<AppFailure>().having((f) => f.message, 'msg', contains('Despublique'))),
      );
      expect(calls.where((c) => c.path.contains('/storage/')), isEmpty);
    });

    test('excluir produto livre: apaga o registro e depois os arquivos', () async {
      final (client, calls) = server((c) {
        if (c.path.endsWith('/product_images')) return ok([{'id': 'i1', 'produto_id': prod, 'storage_path': '$store/$prod/i1.jpg', 'principal': true, 'ordem': 1}]);
        if (c.path.contains('/storage/')) return ok([{'name': 'i1.jpg'}]);
        return ok([{'id': prod}]);
      });
      await SupabaseProductsRepository(client, storeId: store).delete(prod);
      expect(calls.map((c) => '${c.method} ${c.path}').toList(), [
        'GET /rest/v1/product_images',
        'DELETE /rest/v1/produtos',
        'DELETE /storage/v1/object/product-images',
      ]);
      expect(calls.last.json['prefixes'], ['$store/$prod/i1.jpg']);
    });

    test('foto: envia para a pasta da confeitaria e registra o mesmo caminho', () async {
      final (client, calls) = server((c) {
        if (c.method == 'GET') return ok([]);
        if (c.path.contains('/storage/')) return ok({'Key': 'product-images/x', 'Id': 'x'});
        final row = (c.json is List ? (c.json as List).single : c.json) as Map;
        return ok(row, 201); // .single(): objeto
      });
      final img = await SupabaseProductsRepository(client, storeId: store).addImage(prod, Uint8List.fromList([0xFF, 0xD8, 0xFF]));
      final upload = calls.firstWhere((c) => c.path.contains('/storage/'));
      expect(upload.method, 'POST');
      expect(upload.path, startsWith('/storage/v1/object/product-images/$store/$prod/'));
      expect(upload.path, endsWith('.jpg'));
      final insert = calls.last;
      expect(insert.path, '/rest/v1/product_images');
      final row = (insert.json is List ? (insert.json as List).single : insert.json) as Map;
      expect('/storage/v1/object/product-images/${row['storage_path']}', upload.path);
      expect(row['principal'], isTrue); // primeira foto vira a principal
      expect(img.principal, isTrue);
    });

    test('foto: se o banco recusar o registro (limite), o arquivo enviado é apagado', () async {
      final (client, calls) = server((c) {
        if (c.method == 'GET') return ok([]);
        if (c.path.contains('/storage/')) return ok({'Key': 'x'});
        return pgError('P0001', 'limite_fotos: no máximo 10 fotos por produto');
      });
      await expectLater(
        SupabaseProductsRepository(client, storeId: store).addImage(prod, Uint8List.fromList([1, 2, 3])),
        throwsA(isA<AppFailure>().having((f) => f.message, 'msg', contains('10 fotos'))),
      );
      expect(calls.last.method, 'DELETE');
      expect(calls.last.path, '/storage/v1/object/product-images');
    });

    test('lista de produtos e fotos em ordem crescente', () async {
      final (client, calls) = server((c) => ok([]));
      final repo = SupabaseProductsRepository(client, storeId: store);
      await repo.list();
      await repo.images(prod);
      expect(calls[0].q['order'], 'ordem.asc.nullslast,nome.asc.nullslast');
      expect(calls[2].q['order'], startsWith('ordem.asc'));
    });

    test('foto principal pela função definir_foto_principal', () async {
      final (client, calls) = server((c) => ok(null));
      await SupabaseProductsRepository(client, storeId: store).setPrincipal('img9');
      expect(calls.single.path, '/rest/v1/rpc/definir_foto_principal');
      expect(calls.single.json, {'p_image_id': 'img9'});
    });
  });

  group('Orçamentos', () {
    test('lista paginada, mais novos primeiro, com filtro de status', () async {
      final (client, calls) = server((c) => ok([]));
      await SupabaseQuotesRepository(client, storeId: store).list(status: 'Novo', limit: 30);
      final c = calls.single;
      expect(c.path, '/rest/v1/leads');
      expect(c.q['status'], 'eq.Novo');
      expect(c.q['confeitaria_id'], 'eq.$store');
      expect(c.q['order'], 'created_at.desc.nullslast');
      expect((c.q['offset'], c.q['limit']), ('0', '30'));
    });

    test('mudar status manda só o status', () async {
      final (client, calls) = server((c) => ok([{'id': 'q1'}]));
      await SupabaseQuotesRepository(client, storeId: store).updateStatus('q1', QuoteStatus.enviado);
      expect(calls.single.method, 'PATCH');
      expect(calls.single.json, {'status': 'Orçamento enviado'});
    });

    test('conversão chama a função do banco com os parâmetros', () async {
      final (client, calls) = server((c) => ok([{'id': 'o1', 'protocolo': 'PD-1', 'criado': true, 'status': 'Confirmado'}]));
      final r = await SupabaseQuotesRepository(client, storeId: store).convert(
          'q1', ConversionInput(deliveryDate: DateTime(2026, 12, 1), address: '  Rua A, 1  ', finalValue: 320, internalNotes: 'x'));
      expect(calls.single.path, '/rest/v1/rpc/converter_orcamento_em_pedido');
      expect(calls.single.json, {
        'p_lead_id': 'q1',
        'p_data_entrega': '2026-12-01',
        'p_endereco_entrega': 'Rua A, 1',
        'p_valor_final': 320.0,
        'p_observacoes_internas': 'x',
      });
      expect((r.orderId, r.created), ('o1', true));
    });

    test('motivos do banco viram mensagem (ex.: endereço obrigatório)', () async {
      final (client, _) = server((c) => pgError('22023', 'endereco_obrigatorio'));
      await expectLater(
        SupabaseQuotesRepository(client, storeId: store).convert('q1', const ConversionInput()),
        throwsA(isA<AppFailure>().having((f) => f.message, 'msg', contains('endereço'))),
      );
    });

    test('sem permissão (outra confeitaria ou sem perfil)', () async {
      final (client, _) = server((c) => pgError('42501', 'orcamento_nao_encontrado', 403));
      await expectLater(
        SupabaseQuotesRepository(client, storeId: store).convert('q1', const ConversionInput()),
        throwsA(isA<AppFailure>().having((f) => f.message, 'msg', contains('não encontrado'))),
      );
    });
  });

  group('Pedidos', () {
    test('lista com itens embutidos e paginação', () async {
      final (client, calls) = server((c) => ok([orderRow()]));
      final list = await SupabaseOrdersRepository(client, storeId: store).list(limit: 30);
      expect(calls.single.q['select'], contains('order_items('));
      expect(list.single.items.single.subtotal, 300);
      expect(list.single.estimatedValue, 600);
      expect(list.single.finalValue, isNull);
    });

    test('atualização manda só os campos alterados (nunca valor estimado ou cliente)', () async {
      final (client, calls) = server((c) => ok([{'id': 'o1'}]));
      final repo = SupabaseOrdersRepository(client, storeId: store);
      await repo.update('o1', const OrderUpdate(status: OrderStatus.emProducao));
      await repo.update('o1', OrderUpdate(finalValue: 650, deliveryDate: DateTime(2026, 12, 2), internalNotes: ' sinal '));
      await repo.update('o1', const OrderUpdate(clearFinalValue: true));
      expect(calls.map((c) => c.json).toList(), [
        {'status': 'Em produção'},
        {'valor_final': 650.0, 'data_entrega': '2026-12-02', 'observacoes_internas': 'sinal'},
        {'valor_final': null},
      ]);
      expect(calls.every((c) => c.q['confeitaria_id'] == 'eq.$store'), isTrue);
    });

    test('atualização vazia não chama o servidor', () async {
      final (client, calls) = server((c) => ok([]));
      await SupabaseOrdersRepository(client, storeId: store).update('o1', const OrderUpdate());
      expect(calls, isEmpty);
    });

    test('pedido de outra confeitaria: nenhuma linha afetada vira "não encontrado"', () async {
      final (client, _) = server((c) => ok([]));
      await expectLater(
        SupabaseOrdersRepository(client, storeId: store).update('o9', const OrderUpdate(status: OrderStatus.pronto)),
        throwsA(isA<AppFailure>().having((f) => f.message, 'msg', contains('não encontrado'))),
      );
    });

    test('histórico lido em ordem', () async {
      final (client, calls) = server((c) => ok([
            {'campo': 'criado', 'valor_anterior': null, 'valor_novo': 'Aguardando confirmação', 'alterado_por': null, 'alterado_em': '2026-11-21T15:00:00+00:00'},
            {'campo': 'status', 'valor_anterior': 'Aguardando confirmação', 'valor_novo': 'Confirmado', 'alterado_por': 'u1', 'alterado_em': '2026-11-21T16:00:00+00:00'},
          ]));
      final h = await SupabaseOrdersRepository(client, storeId: store).history('o1');
      expect(calls.single.path, '/rest/v1/order_history');
      expect(calls.single.q['order'], startsWith('alterado_em.asc')); // mais antigo primeiro
      expect(h.map((e) => e.text).toList(),
          ['Pedido feito pela cliente no site (Aguardando confirmação)', 'Status: Aguardando confirmação → Confirmado']);
    });
  });

  group('Dashboard', () {
    test('usa a função painel_indicadores com o período', () async {
      final (client, calls) = server((c) => ok({
            'orcamentos': {'total': 3, 'novos': 1, 'vendas_concluidas': 1, 'taxa_conversao': 0.3333},
            'pedidos': {'total': 2, 'valor_registrado': 600, 'valor_final_combinado': 650, 'sem_valor_estimado': 1},
            'entregas_proximos_7_dias': 1,
          }));
      final d = await SupabaseDashboardRepository(client, now: () => DateTime.utc(2026, 11, 21, 15))
          .load(DashboardPeriod.last7);
      expect(calls.single.path, '/rest/v1/rpc/painel_indicadores');
      expect(calls.single.json, {'p_inicio': '2026-11-15', 'p_fim': '2026-11-21'});
      expect((d.registeredValue, d.finalValue, d.withoutEstimate), (600.0, 650.0, 1));
    });
  });

  group('API de marketing (HTTP)', () {
    (HttpMarketingApi, List<http.Request>) api(http.Response Function(http.Request r) respond, {String? token = 'jwt-da-dona'}) {
      final calls = <http.Request>[];
      final client = MockClient((req) async {
        calls.add(req);
        final r = respond(req);
        return http.Response.bytes(r.bodyBytes, r.statusCode, headers: r.headers, request: req);
      });
      return (HttpMarketingApi(baseUrl: 'https://api.exemplo', accessToken: () => token, client: client), calls);
    }

    const req = ArtRequest(productId: 'p1', imageId: 'img2', format: 'story', template: 'promocao', title: 'Oi');

    test('prévia: token da sessão no cabeçalho e campos da arte', () async {
      final (a, calls) = api((_) => ok({
            'imagem_png_base64': 'iVBORw0KGgo=', 'largura': 1080, 'altura': 1920,
            'textos': {'titulo': 'Oi', 'preco_texto': 'R', 'cta': 'C'},
            'legenda': 'Texto\n\n#a', 'legenda_texto': 'Texto', 'hashtags': ['#a'], 'avisos': []
          }));
      final p = await a.preview(req);
      final c = calls.single;
      expect((c.method, c.url.toString()), ('POST', 'https://api.exemplo/v1/marketing/previa'));
      expect(c.headers['Authorization'], 'Bearer jwt-da-dona');
      expect(jsonDecode(c.body), containsPair('imagem_id', 'img2'));
      expect(jsonDecode(c.body)['formato'], 'story');
      expect((p.height, p.captionBody), (1920, 'Texto'));
      expect(p.hashtags, ['#a']);
    });

    test('salvar manda a Idempotency-Key e a legenda final', () async {
      final (a, calls) = api((_) => ok({'id': 'm1', 'criado': true, 'post': {
            'id': 'm1', 'produto_id': 'p1', 'produto_nome': 'Bolo', 'template': 'promocao', 'formato': 'story',
            'titulo': 'Oi', 'preco_texto': '', 'cta': '', 'tom': 'amigavel', 'legenda': 'L', 'status': 'Rascunho',
            'created_at': '2026-11-21T15:00:00+00:00'}}, 201));
      final post = await a.save(req, caption: 'L', idempotencyKey: 'chave-0001');
      expect(calls.single.headers['Idempotency-Key'], 'chave-0001');
      expect(jsonDecode(calls.single.body)['legenda'], 'L');
      expect(post.id, 'm1');
    });

    test('erros da API viram mensagens (409 agendado, 401 sessão)', () async {
      final (a, _) = api((_) => ok({'erro': {'codigo': 'post_agendado', 'mensagem': 'Este post está agendado no Instagram.'}}, 409));
      await expectLater(a.update('m1', req, caption: '', status: 'Rascunho'),
          throwsA(isA<AppFailure>().having((f) => f.message, 'm', contains('agendado'))));
      final (b, calls) = api((_) => ok({}), token: null);
      await expectLater(b.list(), throwsA(isA<AppFailure>().having((f) => f.kind, 'k', FailureKind.expired)));
      expect(calls, isEmpty); // sem sessão, nem chama a API
    });
  });

  group('Instagram (banco + serviço)', () {
    test('agendar chama a função do banco com a chave de idempotência', () async {
      final (client, calls) = server((c) => ok([{
            'id': 'pub1', 'marketing_post_id': 'm1', 'formato': 'feed', 'legenda': 'L', 'status': 'agendado',
            'agendado_para': '2026-11-22T15:00:00+00:00', 'tentativas': 0, 'max_tentativas': 3,
            'erro_mensagem': null, 'permalink': null, 'publicado_em': null, 'ig_media_id': null,
            'created_at': '2026-11-21T15:00:00+00:00'}]));
      final repo = SupabaseInstagramRepository(client, storeId: store);
      final p = await repo.schedule('m1', when: DateTime.utc(2026, 11, 22, 15), idempotencyKey: 'chave-0001');
      expect(calls.single.path, '/rest/v1/rpc/agendar_publicacao_instagram');
      expect(calls.single.json, {'p_post_id': 'm1', 'p_agendado_para': '2026-11-22T15:00:00.000Z', 'p_idempotency_key': 'chave-0001'});
      expect((p.status, p.confirmedByMeta), ('agendado', false));
    });

    test('a conta é lida sem o token (só colunas públicas)', () async {
      final (client, calls) = server((c) => ok({'username': 'kika', 'status': 'conectado', 'account_type': 'business',
            'token_expira_em': null, 'ultimo_erro': null}));
      final acc = await SupabaseInstagramRepository(client, storeId: store).account();
      expect(calls.single.q['select'], 'username,status,account_type,token_expira_em,ultimo_erro');
      expect(acc.connected, isTrue);
    });

    test('cancelar, tentar de novo e desconectar pelas funções do banco', () async {
      final (client, calls) = server((c) => ok(null));
      final repo = SupabaseInstagramRepository(client, storeId: store);
      await repo.cancel('pub1');
      await repo.retry('pub1');
      await repo.disconnect();
      expect(calls.map((c) => c.path).toList(), [
        '/rest/v1/rpc/cancelar_publicacao_instagram',
        '/rest/v1/rpc/tentar_publicacao_instagram_novamente',
        '/rest/v1/rpc/desconectar_instagram',
      ]);
    });

    test('sem endereço do serviço, a conexão não é oferecida', () async {
      final (client, _) = server((c) => ok(null));
      await expectLater(SupabaseInstagramRepository(client, storeId: store).connectUrl(),
          throwsA(isA<AppFailure>().having((f) => f.message, 'm', contains('não foi configurada'))));
    });
  });
}
