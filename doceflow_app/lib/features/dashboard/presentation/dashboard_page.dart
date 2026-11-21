import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../auth/application/auth_controller.dart';
import '../data/dashboard_repository.dart';
import '../domain/dashboard_indicators.dart';

final dashboardPeriodProvider = StateProvider<DashboardPeriod>((ref) => DashboardPeriod.last30);

final dashboardProvider = FutureProvider.autoDispose<DashboardIndicators>((ref) async {
  final period = ref.watch(dashboardPeriodProvider);
  try {
    return await ref.watch(dashboardRepositoryProvider).load(period);
  } catch (e) {
    throw toFailure(e);
  }
});

final _money = NumberFormat.currency(locale: 'pt_BR', symbol: r'R$');

class DashboardPage extends ConsumerWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final storeName = auth is AuthSignedIn ? auth.account.storeName : '';
    final data = ref.watch(dashboardProvider);
    final period = ref.watch(dashboardPeriodProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Início'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Semantics(label: 'Logo Kika Cakes', child: Image.asset('assets/logo/logo-kika-cakes.png', height: 40)),
          ),
        ],
      ),
      body: RefreshIndicator(
        color: KikaColors.destaque,
        onRefresh: () => ref.refresh(dashboardProvider.future).catchError((_) => _emptyIndicators),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            Text('Olá! 👋', style: Theme.of(context).textTheme.headlineSmall),
            if (storeName.isNotEmpty)
              Text('Resumo da $storeName', style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: 14),
            _PeriodChips(selected: period),
            const SizedBox(height: 14),
            data.when(
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Center(child: CircularProgressIndicator(semanticsLabel: 'Carregando indicadores')),
              ),
              error: (e, _) => ErrorRetry(
                message: toFailure(e).message,
                onRetry: () => ref.invalidate(dashboardProvider),
              ),
              data: (d) => _Indicators(d),
            ),
          ],
        ),
      ),
    );
  }
}

const _emptyIndicators = DashboardIndicators(
  quotesTotal: 0,
  quotesNew: 0,
  quotesSold: 0,
  conversionRate: null,
  ordersTotal: 0,
  ordersWaiting: 0,
  ordersInProgress: 0,
  registeredValue: 0,
  deliveriesNext7Days: 0,
);

class _PeriodChips extends ConsumerWidget {
  const _PeriodChips({required this.selected});

  final DashboardPeriod selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final p in DashboardPeriod.values)
          ChoiceChip(
            label: Text(p.label),
            selected: p == selected,
            selectedColor: KikaColors.destaque.withValues(alpha: 0.25),
            side: const BorderSide(color: KikaColors.rosaBorda),
            labelStyle: const TextStyle(fontWeight: FontWeight.w700, color: KikaColors.marrom),
            onSelected: (_) => ref.read(dashboardPeriodProvider.notifier).state = p,
          ),
      ],
    );
  }
}

class _Indicators extends StatelessWidget {
  const _Indicators(this.d);

  final DashboardIndicators d;

  @override
  Widget build(BuildContext context) {
    final rate = d.conversionRate;
    final cards = [
      _Metric(Icons.mark_email_unread_outlined, 'Orçamentos novos', '${d.quotesNew}',
          'de ${d.quotesTotal} no período', highlight: d.quotesNew > 0),
      _Metric(Icons.hourglass_top_outlined, 'Pedidos para confirmar', '${d.ordersWaiting}',
          'de ${d.ordersTotal} no período', highlight: d.ordersWaiting > 0),
      _Metric(Icons.local_shipping_outlined, 'Entregas em 7 dias', '${d.deliveriesNext7Days}', 'a produzir ou entregar'),
      _Metric(Icons.cake_outlined, 'Pedidos em andamento', '${d.ordersInProgress}', 'confirmados, em produção ou prontos'),
      _Metric(Icons.trending_up, 'Taxa de conversão',
          rate == null ? '—' : '${(rate * 100).toStringAsFixed(1).replaceAll('.', ',')}%',
          '${d.quotesSold} venda(s) concluída(s)'),
      _Metric(Icons.payments_outlined, 'Valor registrado', _money.format(d.registeredValue),
          'estimado, sem cancelados (não é receita)'),
    ];
    return LayoutBuilder(
      builder: (context, c) {
        final columns = c.maxWidth >= 720 ? 3 : (c.maxWidth >= 340 ? 2 : 1);
        const gap = 12.0;
        final width = (c.maxWidth - gap * (columns - 1)) / columns;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [for (final m in cards) SizedBox(width: width, child: m)],
        );
      },
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric(this.icon, this.title, this.value, this.caption, {this.highlight = false});

  final IconData icon;
  final String title;
  final String value;
  final String caption;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Semantics(
      container: true,
      label: '$title: $value. $caption',
      excludeSemantics: true,
      child: Card(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: highlight ? KikaColors.destaque : KikaColors.rosaBorda, width: highlight ? 2 : 1),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: KikaColors.destaque),
              const SizedBox(height: 8),
              Text(title, style: t.labelLarge),
              const SizedBox(height: 4),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: t.headlineMedium),
              ),
              const SizedBox(height: 2),
              Text(caption, style: t.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}
