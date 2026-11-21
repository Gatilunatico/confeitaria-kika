import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../../../core/errors/app_failure.dart';
import '../domain/marketing.dart';

/// API de marketing (doceflow/api). Gera as artes no servidor com o código do painel web,
/// sempre com o token da sessão da dona (a API confere no Supabase a cada pedido).
abstract interface class MarketingApi {
  Future<ArtPreview> preview(ArtRequest request);

  /// [idempotencyKey]: a mesma chave devolve o mesmo post (toque repetido não duplica).
  Future<MarketingPost> save(ArtRequest request, {required String caption, required String idempotencyKey});
  Future<MarketingPost> update(String postId, ArtRequest request, {required String caption, required String status});
  Future<({List<MarketingPost> items, int total})> list({int page = 1, int limit = 20});
  Future<void> setStatus(String postId, String status);
  Future<Uint8List> image(String postId);
}

final marketingApiProvider = Provider<MarketingApi>((ref) => const UnconfiguredMarketingApi());

const notConfigured = 'O estúdio de marketing ainda não foi configurado neste app (falta o endereço da API). '
    'Fale com o suporte do DoceFlow.';

class UnconfiguredMarketingApi implements MarketingApi {
  const UnconfiguredMarketingApi();

  Never _fail() => throw const AppFailure(notConfigured, kind: FailureKind.unavailable);

  @override
  Future<ArtPreview> preview(ArtRequest request) async => _fail();
  @override
  Future<MarketingPost> save(ArtRequest request, {required String caption, required String idempotencyKey}) async =>
      _fail();
  @override
  Future<MarketingPost> update(String postId, ArtRequest request, {required String caption, required String status}) async =>
      _fail();
  @override
  Future<({List<MarketingPost> items, int total})> list({int page = 1, int limit = 20}) async => _fail();
  @override
  Future<void> setStatus(String postId, String status) async => _fail();
  @override
  Future<Uint8List> image(String postId) async => _fail();
}

class HttpMarketingApi implements MarketingApi {
  HttpMarketingApi({required this.baseUrl, required this.accessToken, http.Client? client})
      : _http = client ?? http.Client();

  final String baseUrl;
  final String? Function() accessToken; // token atual da sessão do Supabase
  final http.Client _http;
  static const _timeout = Duration(seconds: 40);

  Map<String, String> _headers({String? idempotencyKey, bool json = true}) {
    final token = accessToken();
    if (token == null || token.isEmpty) {
      throw const AppFailure('Sua sessão terminou. Entre novamente.', kind: FailureKind.expired);
    }
    return {
      'Authorization': 'Bearer $token',
      if (json) 'Content-Type': 'application/json',
      if (idempotencyKey != null) 'Idempotency-Key': idempotencyKey,
    };
  }

  Uri _u(String path, [Map<String, String>? q]) => Uri.parse('$baseUrl$path').replace(queryParameters: q);

  Future<http.Response> _send(Future<http.Response> Function() call) async {
    final http.Response r;
    try {
      r = await call().timeout(_timeout);
    } on AppFailure {
      rethrow;
    } catch (e) {
      throw toFailure(e);
    }
    if (r.statusCode >= 200 && r.statusCode < 300) return r;
    String message = 'Não foi possível concluir agora. Tente novamente.';
    String code = '';
    try {
      final err = (jsonDecode(utf8.decode(r.bodyBytes)) as Map)['erro'] as Map;
      message = (err['mensagem'] as String?) ?? message;
      code = (err['codigo'] as String?) ?? '';
    } catch (_) {}
    final kind = switch (r.statusCode) {
      401 => FailureKind.expired,
      403 => FailureKind.noAccess,
      404 || 409 || 422 => FailureKind.validation,
      429 => FailureKind.rateLimited,
      _ => FailureKind.unavailable,
    };
    if (code == 'dados_invalidos') message = 'Confira os campos da arte.';
    throw AppFailure(message, kind: kind);
  }

  Map<String, dynamic> _json(http.Response r) => (jsonDecode(utf8.decode(r.bodyBytes)) as Map).cast<String, dynamic>();

  @override
  Future<ArtPreview> preview(ArtRequest request) async {
    final r = await _send(() => _http.post(_u('/v1/marketing/previa'), headers: _headers(), body: jsonEncode(request.toJson())));
    final j = _json(r);
    final t = (j['textos'] as Map).cast<String, dynamic>();
    return ArtPreview(
      png: base64Decode(j['imagem_png_base64'] as String),
      width: (j['largura'] as num).toInt(),
      height: (j['altura'] as num).toInt(),
      title: t['titulo'] as String,
      priceText: t['preco_texto'] as String,
      cta: t['cta'] as String,
      captionBody: (j['legenda_texto'] as String?) ?? (j['legenda'] as String? ?? ''),
      hashtags: [for (final h in (j['hashtags'] as List? ?? const [])) '$h'],
      warnings: [for (final w in (j['avisos'] as List? ?? const [])) '$w'],
    );
  }

  @override
  Future<MarketingPost> save(ArtRequest request, {required String caption, required String idempotencyKey}) async {
    final r = await _send(() => _http.post(_u('/v1/marketing/posts'),
        headers: _headers(idempotencyKey: idempotencyKey), body: jsonEncode({...request.toJson(), 'legenda': caption})));
    return MarketingPost.fromJson((_json(r)['post'] as Map).cast<String, dynamic>());
  }

  @override
  Future<MarketingPost> update(String postId, ArtRequest request, {required String caption, required String status}) async {
    final r = await _send(() => _http.put(_u('/v1/marketing/posts/$postId'),
        headers: _headers(), body: jsonEncode({...request.toJson(), 'legenda': caption, 'status': status})));
    return MarketingPost.fromJson((_json(r)['post'] as Map).cast<String, dynamic>());
  }

  @override
  Future<({List<MarketingPost> items, int total})> list({int page = 1, int limit = 20}) async {
    final r = await _send(() => _http.get(_u('/v1/marketing/posts', {'pagina': '$page', 'limite': '$limit'}),
        headers: _headers(json: false)));
    final j = _json(r);
    return (
      items: [for (final i in j['itens'] as List) MarketingPost.fromJson((i as Map).cast<String, dynamic>())],
      total: (j['total'] as num).toInt(),
    );
  }

  @override
  Future<void> setStatus(String postId, String status) => _send(() => _http.patch(_u('/v1/marketing/posts/$postId'),
      headers: _headers(), body: jsonEncode({'status': status})));

  @override
  Future<Uint8List> image(String postId) async {
    final r = await _send(() => _http.get(_u('/v1/marketing/posts/$postId/imagem'), headers: _headers(json: false)));
    return r.bodyBytes;
  }
}
