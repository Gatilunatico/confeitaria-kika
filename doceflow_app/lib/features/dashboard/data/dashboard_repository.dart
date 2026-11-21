import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/dashboard_indicators.dart';

abstract interface class DashboardRepository {
  Future<DashboardIndicators> load(DashboardPeriod period);
}

final dashboardRepositoryProvider = Provider<DashboardRepository>(
  (ref) => throw UnimplementedError('dashboardRepositoryProvider precisa ser configurado no main.dart'),
);

/// Dados reais do banco, sempre com o login da dona (RLS). Nada de dados de exemplo.
class SupabaseDashboardRepository implements DashboardRepository {
  SupabaseDashboardRepository(this._client, {DateTime Function()? now}) : _now = now ?? DateTime.now;

  final SupabaseClient _client;
  final DateTime Function() _now;

  String? _iso(DateTime? d) => d?.toIso8601String().substring(0, 10);

  @override
  Future<DashboardIndicators> load(DashboardPeriod period) async {
    final today = todayInBrasilia(_now());
    final (start, end) = period.range(today);
    try {
      final res = await _client.rpc('painel_indicadores', params: {'p_inicio': _iso(start), 'p_fim': _iso(end)});
      return DashboardIndicators.fromRpc((res as Map).cast<String, dynamic>());
    } on PostgrestException catch (e) {
      // Função da migração 012 ainda não aplicada: calcula com as tabelas (o RLS vale do mesmo jeito).
      if (e.code == 'PGRST202' || e.code == '42883') return _fromTables(today, start, end);
      throw toFailure(e);
    } catch (e) {
      throw toFailure(e);
    }
  }

  Future<DashboardIndicators> _fromTables(DateTime today, DateTime? start, DateTime? end) async {
    try {
      // created_at em UTC; o período é em datas de Brasília (UTC-3).
      String bound(DateTime d) => d.add(const Duration(hours: 3)).toIso8601String();
      var leads = _client.from('leads').select('status,created_at');
      var orders = _client.from('orders').select('status,valor_estimado,valor_final,data_entrega,created_at');
      if (start != null) {
        leads = leads.gte('created_at', '${bound(start)}Z');
        orders = orders.gte('created_at', '${bound(start)}Z');
      }
      if (end != null) {
        final next = end.add(const Duration(days: 1));
        leads = leads.lt('created_at', '${bound(next)}Z');
        orders = orders.lt('created_at', '${bound(next)}Z');
      }
      final rows = await Future.wait([leads, orders]);
      final indicators = DashboardIndicators.fromRows(
        leads: rows[0].cast<Map<String, dynamic>>(),
        orders: rows[1].cast<Map<String, dynamic>>(),
        today: today,
      );
      // A agenda dos próximos 7 dias não depende do período.
      if (start == null) return indicators;
      final upcoming = await _client
          .from('orders')
          .select('status,data_entrega')
          .gte('data_entrega', _iso(today)!)
          .lte('data_entrega', _iso(today.add(const Duration(days: 7)))!)
          .not('status', 'in', '("Entregue","Cancelado")');
      return DashboardIndicators(
        quotesTotal: indicators.quotesTotal,
        quotesNew: indicators.quotesNew,
        quotesSold: indicators.quotesSold,
        conversionRate: indicators.conversionRate,
        ordersTotal: indicators.ordersTotal,
        ordersWaiting: indicators.ordersWaiting,
        ordersInProgress: indicators.ordersInProgress,
        registeredValue: indicators.registeredValue,
        deliveriesNext7Days: upcoming.length,
        finalValue: indicators.finalValue,
        withoutEstimate: indicators.withoutEstimate,
        quotesInProgress: indicators.quotesInProgress,
        quotesLost: indicators.quotesLost,
        ordersCancelled: indicators.ordersCancelled,
        ordersDelivered: indicators.ordersDelivered,
      );
    } catch (e) {
      throw toFailure(e);
    }
  }
}
