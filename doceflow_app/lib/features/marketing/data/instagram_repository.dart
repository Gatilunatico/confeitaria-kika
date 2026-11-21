import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/marketing.dart';

/// Instagram no app: SÓ leitura do estado e pedidos à fila (funções do banco, migração 014).
/// O token da Meta nunca passa por aqui: conexão e publicação são do serviço no servidor.
abstract interface class InstagramRepository {
  Future<InstagramAccount> account();
  Future<List<Publication>> publications({required int limit});
  Future<List<PublicationLog>> logs(String publicationId);

  /// [when] null = assim que possível. A mesma [idempotencyKey] devolve o mesmo agendamento.
  Future<Publication> schedule(String postId, {DateTime? when, required String idempotencyKey});
  Future<void> cancel(String publicationId);
  Future<void> retry(String publicationId);
  Future<void> disconnect();

  /// Link da página oficial de autorização da Meta (gerado pelo serviço do Instagram).
  Future<Uri> connectUrl();
}

final instagramRepositoryProvider = Provider<InstagramRepository>(
  (ref) => throw UnimplementedError('instagramRepositoryProvider precisa ser configurado no main.dart'),
);

class SupabaseInstagramRepository implements InstagramRepository {
  SupabaseInstagramRepository(this._client, {required this.storeId, this.serviceUrl, http.Client? httpClient})
      : _http = httpClient ?? http.Client();

  final SupabaseClient _client;
  final String storeId;
  final String? serviceUrl;
  final http.Client _http;

  Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } catch (e) {
      throw toFailure(e);
    }
  }

  @override
  Future<InstagramAccount> account() => _guard(() async {
        final row = await _client
            .from('instagram_accounts')
            .select('username,status,account_type,token_expira_em,ultimo_erro')
            .eq('confeitaria_id', storeId)
            .maybeSingle();
        return row == null ? InstagramAccount.none : InstagramAccount.fromJson(row);
      });

  @override
  Future<List<Publication>> publications({required int limit}) => _guard(() async {
        final rows = await _client
            .from('instagram_publications')
            .select(Publication.columns)
            .eq('confeitaria_id', storeId)
            .order('created_at', ascending: false)
            .range(0, limit - 1);
        return rows.map(Publication.fromJson).toList();
      });

  @override
  Future<List<PublicationLog>> logs(String publicationId) => _guard(() async {
        final rows = await _client
            .from('instagram_publication_logs')
            .select('evento,detalhe,created_at')
            .eq('publication_id', publicationId)
            .order('id', ascending: true);
        return rows.map(PublicationLog.fromJson).toList();
      });

  @override
  Future<Publication> schedule(String postId, {DateTime? when, required String idempotencyKey}) => _guard(() async {
        final rows = await _client.rpc('agendar_publicacao_instagram', params: {
          'p_post_id': postId,
          'p_agendado_para': when?.toUtc().toIso8601String(),
          'p_idempotency_key': idempotencyKey,
        }) as List;
        if (rows.isEmpty) throw const AppFailure('O servidor não confirmou o agendamento. Tente novamente.');
        return Publication.fromJson((rows.first as Map).cast<String, dynamic>());
      });

  @override
  Future<void> cancel(String publicationId) =>
      _guard(() => _client.rpc('cancelar_publicacao_instagram', params: {'p_id': publicationId}));

  @override
  Future<void> retry(String publicationId) =>
      _guard(() => _client.rpc('tentar_publicacao_instagram_novamente', params: {'p_id': publicationId}));

  @override
  Future<void> disconnect() => _guard(() => _client.rpc('desconectar_instagram'));

  @override
  Future<Uri> connectUrl() async {
    final base = serviceUrl;
    if (base == null) {
      throw const AppFailure('A conexão com o Instagram ainda não foi configurada neste app.',
          kind: FailureKind.unavailable);
    }
    final token = _client.auth.currentSession?.accessToken;
    if (token == null) throw const AppFailure('Sua sessão terminou. Entre novamente.', kind: FailureKind.expired);
    final http.Response r;
    try {
      r = await _http
          .get(Uri.parse('$base/v1/instagram/conexao'), headers: {'Authorization': 'Bearer $token'})
          .timeout(const Duration(seconds: 20));
    } catch (e) {
      throw toFailure(e);
    }
    if (r.statusCode != 200) {
      throw AppFailure(r.statusCode == 401 || r.statusCode == 403
          ? 'Sua sessão terminou. Entre novamente.'
          : 'Não foi possível iniciar a conexão com o Instagram agora.');
    }
    final url = Uri.parse((jsonDecode(r.body) as Map)['url'] as String);
    if (url.scheme != 'https' || url.host != 'www.instagram.com') {
      throw const AppFailure('Endereço de autorização inesperado. Fale com o suporte.');
    }
    return url;
  }
}
