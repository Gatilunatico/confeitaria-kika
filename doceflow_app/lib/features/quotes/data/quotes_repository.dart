import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/format.dart';
import '../domain/quote.dart';

abstract interface class QuotesRepository {
  /// Mais novos primeiro; [limit] cresce com "Carregar mais".
  Future<List<Quote>> list({String? status, required int limit});
  Future<Quote> get(String id);
  Future<void> updateStatus(String id, String status);
  Future<ConversionResult> convert(String id, ConversionInput input);
}

final quotesRepositoryProvider = Provider<QuotesRepository>(
  (ref) => throw UnimplementedError('quotesRepositoryProvider precisa ser configurado no main.dart'),
);

class SupabaseQuotesRepository implements QuotesRepository {
  SupabaseQuotesRepository(this._client, {required this.storeId});

  final SupabaseClient _client;
  final String storeId;

  Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } catch (e) {
      throw toFailure(e);
    }
  }

  @override
  Future<List<Quote>> list({String? status, required int limit}) => _guard(() async {
        var q = _client.from('leads').select(Quote.columns).eq('confeitaria_id', storeId);
        if (status != null) q = q.eq('status', status);
        final rows = await q.order('created_at', ascending: false).range(0, limit - 1);
        return rows.map(Quote.fromJson).toList();
      });

  @override
  Future<Quote> get(String id) => _guard(() async {
        final row = await _client.from('leads').select(Quote.columns).eq('id', id).eq('confeitaria_id', storeId).maybeSingle();
        if (row == null) throw const AppFailure('Orçamento não encontrado nesta confeitaria.');
        final order = await _client.from('orders').select('id').eq('lead_id', id).maybeSingle();
        return Quote.fromJson(row, orderId: order?['id'] as String?);
      });

  @override
  Future<void> updateStatus(String id, String status) => _guard(() async {
        final rows =
            await _client.from('leads').update({'status': status}).eq('id', id).eq('confeitaria_id', storeId).select('id');
        if (rows.isEmpty) throw const AppFailure('Orçamento não encontrado nesta confeitaria.');
      });

  /// A regra (validações, preço, um pedido por orçamento, histórico) está toda no banco:
  /// função converter_orcamento_em_pedido (migração 012). Repetir devolve o mesmo pedido.
  @override
  Future<ConversionResult> convert(String id, ConversionInput input) => _guard(() async {
        final rows = await _client.rpc('converter_orcamento_em_pedido', params: {
          'p_lead_id': id,
          'p_data_entrega': input.deliveryDate == null ? null : isoDate(input.deliveryDate!),
          'p_endereco_entrega': input.address.trim(),
          'p_valor_final': input.finalValue,
          'p_observacoes_internas': input.internalNotes.trim(),
        }) as List;
        if (rows.isEmpty) throw const AppFailure('O servidor não confirmou a conversão. Tente novamente.');
        final r = (rows.first as Map).cast<String, dynamic>();
        return ConversionResult(orderId: r['id'] as String, protocol: r['protocolo'] as String, created: r['criado'] as bool);
      });
}
