/// Números do Início. Mesmas definições do painel web e da função `painel_indicadores`
/// (migração 012): período pela data de registro no horário de Brasília.
class DashboardIndicators {
  const DashboardIndicators({
    required this.quotesTotal,
    required this.quotesNew,
    required this.quotesSold,
    required this.conversionRate,
    required this.ordersTotal,
    required this.ordersWaiting,
    required this.ordersInProgress,
    required this.registeredValue,
    required this.deliveriesNext7Days,
    this.finalValue = 0,
    this.withoutEstimate = 0,
    this.quotesInProgress = 0,
    this.quotesLost = 0,
    this.ordersCancelled = 0,
    this.ordersDelivered = 0,
  });

  final int quotesTotal;
  final int quotesNew;
  final int quotesSold;
  final double? conversionRate; // 0..1; null sem orçamentos no período
  final int ordersTotal;
  final int ordersWaiting; // Aguardando confirmação
  final int ordersInProgress; // Confirmado + Em produção + Pronto
  final double registeredValue; // estimados dos pedidos não cancelados (não é receita)
  final int deliveriesNext7Days;
  final double finalValue; // soma dos valores FINAIS combinados (pedidos não cancelados)
  final int withoutEstimate; // pedidos sem valor estimado (item sob consulta)
  final int quotesInProgress; // Em atendimento + Orçamento enviado
  final int quotesLost;
  final int ordersCancelled;
  final int ordersDelivered;

  /// Resposta JSON de `rpc('painel_indicadores')`.
  factory DashboardIndicators.fromRpc(Map<String, dynamic> json) {
    final q = (json['orcamentos'] as Map).cast<String, dynamic>();
    final o = (json['pedidos'] as Map).cast<String, dynamic>();
    int i(Map<String, dynamic> m, String k) => (m[k] as num?)?.toInt() ?? 0;
    return DashboardIndicators(
      quotesTotal: i(q, 'total'),
      quotesNew: i(q, 'novos'),
      quotesSold: i(q, 'vendas_concluidas'),
      conversionRate: (q['taxa_conversao'] as num?)?.toDouble(),
      ordersTotal: i(o, 'total'),
      ordersWaiting: i(o, 'aguardando_confirmacao'),
      ordersInProgress: i(o, 'confirmados') + i(o, 'em_producao') + i(o, 'prontos'),
      registeredValue: (o['valor_registrado'] as num?)?.toDouble() ?? 0,
      deliveriesNext7Days: (json['entregas_proximos_7_dias'] as num?)?.toInt() ?? 0,
      finalValue: (o['valor_final_combinado'] as num?)?.toDouble() ?? 0,
      withoutEstimate: i(o, 'sem_valor_estimado'),
      quotesInProgress: i(q, 'em_atendimento') + i(q, 'orcamentos_enviados'),
      quotesLost: i(q, 'perdidos'),
      ordersCancelled: i(o, 'cancelados'),
      ordersDelivered: i(o, 'entregues'),
    );
  }

  /// Cálculo no aparelho a partir das linhas (usado enquanto a migração 012 não está no banco).
  factory DashboardIndicators.fromRows({
    required List<Map<String, dynamic>> leads,
    required List<Map<String, dynamic>> orders,
    required DateTime today,
  }) {
    int leadCount(String s) => leads.where((l) => l['status'] == s).length;
    int orderCount(Set<String> s) => orders.where((o) => s.contains(o['status'])).length;
    final active = orders.where((o) => o['status'] != 'Cancelado');
    final day = DateTime(today.year, today.month, today.day);
    final deliveries = orders.where((o) {
      if (o['status'] == 'Entregue' || o['status'] == 'Cancelado') return false;
      final d = DateTime.tryParse('${o['data_entrega']}');
      if (d == null) return false;
      final date = DateTime(d.year, d.month, d.day);
      return !date.isBefore(day) && !date.isAfter(day.add(const Duration(days: 7)));
    }).length;
    final sold = leadCount('Venda concluída');
    return DashboardIndicators(
      quotesTotal: leads.length,
      quotesNew: leadCount('Novo'),
      quotesSold: sold,
      conversionRate: leads.isEmpty ? null : sold / leads.length,
      ordersTotal: orders.length,
      ordersWaiting: orderCount({'Aguardando confirmação'}),
      ordersInProgress: orderCount({'Confirmado', 'Em produção', 'Pronto'}),
      registeredValue: active.fold<double>(0, (sum, o) => sum + ((o['valor_estimado'] as num?)?.toDouble() ?? 0)),
      deliveriesNext7Days: deliveries,
      finalValue: active.fold<double>(0, (sum, o) => sum + ((o['valor_final'] as num?)?.toDouble() ?? 0)),
      withoutEstimate: active.where((o) => o['valor_estimado'] == null).length,
      quotesInProgress: leadCount('Em atendimento') + leadCount('Orçamento enviado'),
      quotesLost: leadCount('Perdido'),
      ordersCancelled: orderCount({'Cancelado'}),
      ordersDelivered: orderCount({'Entregue'}),
    );
  }
}

/// Períodos do filtro do Início (igual ao painel web).
enum DashboardPeriod {
  last7('7 dias', 7),
  last30('30 dias', 30),
  last90('90 dias', 90),
  all('Tudo', null);

  const DashboardPeriod(this.label, this.days);
  final String label;
  final int? days;

  /// (início, fim) inclusivos, em datas de Brasília. `null` = sem limite.
  (DateTime?, DateTime?) range(DateTime todayBrt) {
    final d = days;
    if (d == null) return (null, null);
    final end = DateTime(todayBrt.year, todayBrt.month, todayBrt.day);
    return (end.subtract(Duration(days: d - 1)), end);
  }
}

/// "Hoje" no horário de Brasília (UTC-3, sem horário de verão), igual ao servidor.
DateTime todayInBrasilia(DateTime nowUtc) {
  final brt = nowUtc.toUtc().subtract(const Duration(hours: 3));
  return DateTime(brt.year, brt.month, brt.day);
}
