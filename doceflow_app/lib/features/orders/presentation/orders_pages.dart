import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/format.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../../core/widgets/states.dart';
import '../../../core/widgets/whatsapp_button.dart';
import '../../auth/application/auth_controller.dart';
import '../../dashboard/presentation/dashboard_page.dart';
import '../../quotes/presentation/quotes_pages.dart' show StatusFilter, pageSize;
import '../data/orders_repository.dart';
import '../domain/order.dart';

final orderFilterProvider = StateProvider<String?>((ref) => null);
final orderLimitProvider = StateProvider<int>((ref) => pageSize);

final ordersListProvider = FutureProvider.autoDispose<List<Order>>((ref) {
  final status = ref.watch(orderFilterProvider);
  final limit = ref.watch(orderLimitProvider);
  return ref.watch(ordersRepositoryProvider).list(status: status, limit: limit);
});

final orderProvider = FutureProvider.autoDispose.family<Order, String>(
  (ref, id) => ref.watch(ordersRepositoryProvider).get(id),
);

final orderHistoryProvider = FutureProvider.autoDispose.family<List<HistoryEntry>, String>(
  (ref, id) => ref.watch(ordersRepositoryProvider).history(id),
);

class OrdersPage extends ConsumerWidget {
  const OrdersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(orderFilterProvider);
    final limit = ref.watch(orderLimitProvider);
    final orders = ref.watch(ordersListProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Pedidos')),
      body: RefreshIndicator(
        color: KikaColors.destaque,
        onRefresh: () async => ref.invalidate(ordersListProvider),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            StatusFilter(
              options: OrderStatus.all,
              selected: filter,
              onChanged: (s) {
                ref.read(orderFilterProvider.notifier).state = s;
                ref.read(orderLimitProvider.notifier).state = pageSize;
              },
            ),
            const SizedBox(height: 12),
            AsyncBody(
              value: orders,
              onRetry: () => ref.invalidate(ordersListProvider),
              data: (list) {
                if (list.isEmpty) {
                  return EmptyState(
                    icon: Icons.receipt_long_outlined,
                    title: filter == null ? 'Nenhum pedido ainda' : 'Nenhum pedido "$filter"',
                    message: filter == null
                        ? 'Pedidos do site e orçamentos convertidos aparecem aqui.'
                        : 'Escolha outro filtro.',
                  );
                }
                return Column(children: [
                  for (final o in list) ...[_OrderTile(o), const SizedBox(height: 10)],
                  if (list.length >= limit)
                    OutlinedButton(
                      key: const Key('orders_more'),
                      onPressed: () => ref.read(orderLimitProvider.notifier).state = limit + pageSize,
                      child: const Text('Carregar mais'),
                    ),
                ]);
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _OrderTile extends StatelessWidget {
  const _OrderTile(this.o);

  final Order o;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final value = o.finalValue != null ? 'Final ${formatMoney(o.finalValue)}' : 'Estimado ${formatMoney(o.estimatedValue, empty: 'sob consulta')}';
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/pedidos/${o.id}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(o.customerName, style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700))),
              const SizedBox(width: 8),
              Flexible(child: StatusChip(o.status, icon: OrderStatus.icon(o.status), color: OrderStatus.color(o.status))),
            ]),
            const SizedBox(height: 4),
            Text(o.items.map((i) => '${i.name} (${i.quantity})').join(', '), maxLines: 2, overflow: TextOverflow.ellipsis),
            Text('Entrega ${formatDate(o.deliveryDate)} (${o.fulfillment.toLowerCase()}) · $value', style: t.bodySmall),
            Text(o.protocol, style: t.bodySmall),
          ]),
        ),
      ),
    );
  }
}

class OrderDetailPage extends ConsumerStatefulWidget {
  const OrderDetailPage({super.key, required this.orderId});

  final String orderId;

  @override
  ConsumerState<OrderDetailPage> createState() => _OrderDetailPageState();
}

class _OrderDetailPageState extends ConsumerState<OrderDetailPage> {
  bool _saving = false;

  void _refresh() {
    ref.invalidate(orderProvider(widget.orderId));
    ref.invalidate(orderHistoryProvider(widget.orderId));
    ref.invalidate(ordersListProvider);
    ref.invalidate(dashboardProvider);
  }

  Future<bool> _apply(String orderId, OrderUpdate update, String done) async {
    if (_saving || update.isEmpty) return false;
    setState(() => _saving = true);
    try {
      await ref.read(ordersRepositoryProvider).update(orderId, update);
      _refresh();
      if (mounted) showMessage(context, done);
      return true;
    } catch (e) {
      if (mounted) showMessage(context, toFailure(e).message);
      return false;
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _setStatus(Order o, String status) async {
    if (status == o.status) return;
    if (status == OrderStatus.cancelado &&
        !await confirmAction(context,
            title: 'Cancelar o pedido ${o.protocol}?',
            message: 'O pedido fica registrado como cancelado e sai do valor registrado.',
            confirm: 'Cancelar pedido',
            danger: true)) {
      return;
    }
    await _apply(o.id, OrderUpdate(status: status), 'Status alterado para "$status".');
  }

  Future<void> _edit(Order o) async {
    final update = await showModalBottomSheet<OrderUpdate>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: KikaColors.branco,
      builder: (_) => _EditSheet(order: o),
    );
    if (update != null && mounted) await _apply(o.id, update, 'Pedido atualizado.');
  }

  @override
  Widget build(BuildContext context) {
    final order = ref.watch(orderProvider(widget.orderId));
    final auth = ref.watch(authControllerProvider);
    final storeName = auth is AuthSignedIn ? auth.account.storeName : 'confeitaria';
    return Scaffold(
      appBar: AppBar(title: const Text('Pedido')),
      body: AsyncBody(
        value: order,
        onRetry: () => ref.invalidate(orderProvider(widget.orderId)),
        data: (o) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
          children: [
            FormWidth(
              maxWidth: 680,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  Expanded(child: Text(o.customerName, style: Theme.of(context).textTheme.headlineSmall)),
                  const SizedBox(width: 8),
                  Flexible(child: StatusChip(o.status, icon: OrderStatus.icon(o.status), color: OrderStatus.color(o.status))),
                ]),
                Text(o.protocol),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Status',
                  trailing: _saving ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : null,
                  child: Wrap(spacing: 8, runSpacing: 8, children: [
                    for (final s in OrderStatus.all)
                      ChoiceChip(
                        key: Key('order_status_$s'),
                        avatar: Icon(OrderStatus.icon(s), size: 18),
                        label: Text(s),
                        selected: o.status == s,
                        onSelected: _saving ? null : (_) => _setStatus(o, s),
                      ),
                  ]),
                ),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Itens',
                  child: Column(children: [
                    for (final i in o.items)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(i.name),
                        subtitle: Text('${i.quantity} × ${i.unit} · '
                            '${i.unitPrice == null ? 'sob consulta' : 'a partir de ${formatMoney(i.unitPrice)}'}'),
                        trailing: Text(formatMoney(i.subtotal, empty: '—'), style: const TextStyle(fontWeight: FontWeight.w700)),
                      ),
                  ]),
                ),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Valores',
                  trailing: TextButton(
                    key: const Key('order_edit'),
                    onPressed: _saving ? null : () => _edit(o),
                    child: const Text('Editar'),
                  ),
                  child: Column(children: [
                    InfoRow('Estimado', formatMoney(o.estimatedValue, empty: 'sob consulta'), icon: Icons.calculate_outlined),
                    InfoRow('Final', formatMoney(o.finalValue, empty: 'a combinar'), icon: Icons.payments_outlined),
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Text('O estimado é calculado pelo sistema ("a partir de"). O final é o combinado com a cliente.'),
                    ),
                  ]),
                ),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Entrega',
                  child: Column(children: [
                    InfoRow('Data', formatDate(o.deliveryDate), icon: Icons.event),
                    InfoRow('Modalidade', o.fulfillment, icon: Icons.local_shipping_outlined),
                    if (o.fulfillment == 'Entrega') InfoRow('Endereço', o.address.isEmpty ? '—' : o.address, icon: Icons.place_outlined),
                    InfoRow('Obs. da cliente', o.notes.isEmpty ? '—' : o.notes, icon: Icons.notes),
                    InfoRow('Obs. internas', o.internalNotes.isEmpty ? '—' : o.internalNotes, icon: Icons.lock_outline),
                  ]),
                ),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Cliente',
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    InfoRow('WhatsApp', formatPhone(o.whatsapp), icon: Icons.phone_outlined),
                    InfoRow('Pedido em', formatDateTimeBrt(o.createdAt), icon: Icons.schedule),
                    InfoRow('Origem', o.leadId != null ? 'orçamento convertido' : o.origin, icon: Icons.campaign_outlined),
                    const SizedBox(height: 8),
                    WhatsAppButton(phone: o.whatsapp, message: o.whatsappMessage(storeName)),
                  ]),
                ),
                const SizedBox(height: 12),
                _History(orderId: o.id),
              ]),
            ),
          ],
        ),
      ),
    );
  }
}

class _History extends ConsumerWidget {
  const _History({required this.orderId});

  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(orderHistoryProvider(orderId));
    return SectionCard(
      title: 'Histórico',
      child: AsyncBody(
        value: history,
        onRetry: () => ref.invalidate(orderHistoryProvider(orderId)),
        data: (list) => list.isEmpty
            ? const Text('Sem alterações registradas.')
            : Column(children: [
                for (final h in list.reversed)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(h.byAdmin ? Icons.edit_note : Icons.public, color: KikaColors.destaque),
                    title: Text(h.text),
                    subtitle: Text(formatDateTimeBrt(h.at)),
                  ),
              ]),
      ),
    );
  }
}

/// Valor final, data de entrega e observações internas (os campos que o banco deixa mudar).
class _EditSheet extends StatefulWidget {
  const _EditSheet({required this.order});

  final Order order;

  @override
  State<_EditSheet> createState() => _EditSheetState();
}

class _EditSheetState extends State<_EditSheet> {
  final _form = GlobalKey<FormState>();
  late final _value = TextEditingController(text: moneyInput(widget.order.finalValue));
  late final _notes = TextEditingController(text: widget.order.internalNotes);
  late DateTime _date = widget.order.deliveryDate;

  @override
  void dispose() {
    _value.dispose();
    _notes.dispose();
    super.dispose();
  }

  void _save() {
    if (!_form.currentState!.validate()) return;
    final o = widget.order;
    final value = parseMoney(_value.text);
    final clear = _value.text.trim().isEmpty && o.finalValue != null;
    Navigator.pop(
      context,
      OrderUpdate(
        finalValue: value != null && value != o.finalValue ? value : null,
        clearFinalValue: clear,
        deliveryDate: _date != o.deliveryDate ? _date : null,
        internalNotes: _notes.text.trim() != o.internalNotes ? _notes.text : null,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Form(
          key: _form,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('Editar pedido', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 14),
            TextFormField(
              key: const Key('order_final_value'),
              controller: _value,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
              decoration: const InputDecoration(labelText: 'Valor final combinado', prefixText: 'R\$ ', helperText: 'Vazio = a combinar'),
              validator: (v) {
                if ((v ?? '').trim().isEmpty) return null;
                final n = parseMoney(v!);
                return n == null || n < 0 ? 'Valor inválido.' : null;
              },
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              key: const Key('order_date'),
              icon: const Icon(Icons.event),
              label: Text('Entrega: ${formatDate(_date)}'),
              onPressed: () async {
                final now = DateTime.now();
                final d = await showDatePicker(
                  context: context,
                  initialDate: _date,
                  firstDate: _date.isBefore(now) ? _date : DateTime(now.year, now.month, now.day),
                  lastDate: now.add(const Duration(days: 365)),
                );
                if (d != null) setState(() => _date = d);
              },
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('order_notes'),
              controller: _notes,
              maxLength: 1000,
              maxLines: 4,
              minLines: 2,
              decoration: const InputDecoration(labelText: 'Observações internas (só a confeitaria vê)'),
            ),
            const SizedBox(height: 12),
            FilledButton(key: const Key('order_edit_save'), onPressed: _save, child: const Text('Salvar')),
          ]),
        ),
      ),
    );
  }
}
