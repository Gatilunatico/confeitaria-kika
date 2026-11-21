import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/order.dart';

abstract interface class OrdersRepository {
  Future<List<Order>> list({String? status, required int limit});
  Future<Order> get(String id);
  Future<List<HistoryEntry>> history(String id);
  Future<void> update(String id, OrderUpdate update);
}

final ordersRepositoryProvider = Provider<OrdersRepository>(
  (ref) => throw UnimplementedError('ordersRepositoryProvider precisa ser configurado no main.dart'),
);

class SupabaseOrdersRepository implements OrdersRepository {
  SupabaseOrdersRepository(this._client, {required this.storeId});

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
  Future<List<Order>> list({String? status, required int limit}) => _guard(() async {
        var q = _client.from('orders').select('${Order.columns},order_items(${Order.itemColumns})').eq('confeitaria_id', storeId);
        if (status != null) q = q.eq('status', status);
        final rows = await q.order('created_at', ascending: false).range(0, limit - 1);
        return rows.map(Order.fromJson).toList();
      });

  @override
  Future<Order> get(String id) => _guard(() async {
        final row = await _client
            .from('orders')
            .select('${Order.columns},order_items(${Order.itemColumns})')
            .eq('id', id)
            .eq('confeitaria_id', storeId)
            .maybeSingle();
        if (row == null) throw const AppFailure('Pedido não encontrado nesta confeitaria.');
        return Order.fromJson(row);
      });

  @override
  Future<List<HistoryEntry>> history(String id) => _guard(() async {
        final rows = await _client
            .from('order_history')
            .select('campo,valor_anterior,valor_novo,alterado_por,alterado_em')
            .eq('order_id', id)
            .eq('confeitaria_id', storeId)
            .order('alterado_em', ascending: true);
        return rows.map(HistoryEntry.fromJson).toList();
      });

  /// O histórico é gravado pelo gatilho do banco; o app não escreve nele.
  @override
  Future<void> update(String id, OrderUpdate update) => _guard(() async {
        final cols = update.toColumns();
        if (cols.isEmpty) return;
        final rows = await _client.from('orders').update(cols).eq('id', id).eq('confeitaria_id', storeId).select('id');
        if (rows.isEmpty) throw const AppFailure('Pedido não encontrado nesta confeitaria.');
      });
}
