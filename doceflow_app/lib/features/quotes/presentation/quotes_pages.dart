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
import '../../orders/presentation/orders_pages.dart';
import '../data/quotes_repository.dart';
import '../domain/quote.dart';

const pageSize = 30;

final quoteFilterProvider = StateProvider<String?>((ref) => null);
final quoteLimitProvider = StateProvider<int>((ref) => pageSize);

final quotesListProvider = FutureProvider.autoDispose<List<Quote>>((ref) {
  final status = ref.watch(quoteFilterProvider);
  final limit = ref.watch(quoteLimitProvider);
  return ref.watch(quotesRepositoryProvider).list(status: status, limit: limit);
});

final quoteProvider = FutureProvider.autoDispose.family<Quote, String>(
  (ref, id) => ref.watch(quotesRepositoryProvider).get(id),
);

class QuotesPage extends ConsumerWidget {
  const QuotesPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filter = ref.watch(quoteFilterProvider);
    final limit = ref.watch(quoteLimitProvider);
    final quotes = ref.watch(quotesListProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Orçamentos')),
      body: RefreshIndicator(
        color: KikaColors.destaque,
        onRefresh: () async => ref.invalidate(quotesListProvider),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            StatusFilter(
              options: QuoteStatus.all,
              selected: filter,
              onChanged: (s) {
                ref.read(quoteFilterProvider.notifier).state = s;
                ref.read(quoteLimitProvider.notifier).state = pageSize;
              },
            ),
            const SizedBox(height: 12),
            AsyncBody(
              value: quotes,
              onRetry: () => ref.invalidate(quotesListProvider),
              data: (list) {
                if (list.isEmpty) {
                  return EmptyState(
                    icon: Icons.request_quote_outlined,
                    title: filter == null ? 'Nenhum orçamento ainda' : 'Nenhum orçamento "$filter"',
                    message: filter == null ? 'Os pedidos de orçamento do site aparecem aqui.' : 'Escolha outro filtro.',
                  );
                }
                return Column(children: [
                  for (final q in list) ...[_QuoteTile(q), const SizedBox(height: 10)],
                  if (list.length >= limit)
                    OutlinedButton(
                      key: const Key('quotes_more'),
                      onPressed: () => ref.read(quoteLimitProvider.notifier).state = limit + pageSize,
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

class _QuoteTile extends StatelessWidget {
  const _QuoteTile(this.q);

  final Quote q;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/orcamentos/${q.id}'),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(q.customerName, style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700))),
              const SizedBox(width: 8),
              Flexible(child: StatusChip(q.status, icon: QuoteStatus.icon(q.status), color: QuoteStatus.color(q.status))),
            ]),
            const SizedBox(height: 4),
            Text('${q.productName} · ${q.quantity} ${q.unit}', style: t.bodyMedium),
            Text('Para ${formatDate(q.desiredDate)} (${q.fulfillment.toLowerCase()}) · ${q.protocol}', style: t.bodySmall),
          ]),
        ),
      ),
    );
  }
}

/// Chips "Todos" + cada status, roláveis na horizontal.
class StatusFilter extends StatelessWidget {
  const StatusFilter({super.key, required this.options, required this.selected, required this.onChanged});

  final List<String> options;
  final String? selected;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(children: [
        for (final s in [null, ...options])
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(s ?? 'Todos'),
              selected: selected == s,
              onSelected: (_) => onChanged(s),
            ),
          ),
      ]),
    );
  }
}

class QuoteDetailPage extends ConsumerStatefulWidget {
  const QuoteDetailPage({super.key, required this.quoteId});

  final String quoteId;

  @override
  ConsumerState<QuoteDetailPage> createState() => _QuoteDetailPageState();
}

class _QuoteDetailPageState extends ConsumerState<QuoteDetailPage> {
  bool _saving = false;

  void _refresh() {
    ref.invalidate(quoteProvider(widget.quoteId));
    ref.invalidate(quotesListProvider);
    ref.invalidate(dashboardProvider);
  }

  Future<void> _setStatus(Quote q, String status) async {
    if (_saving || status == q.status) return;
    setState(() => _saving = true);
    try {
      await ref.read(quotesRepositoryProvider).updateStatus(q.id, status);
      _refresh();
      if (mounted) showMessage(context, 'Status alterado para "$status".');
    } catch (e) {
      if (mounted) showMessage(context, toFailure(e).message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _convert(Quote q) async {
    final result = await showModalBottomSheet<ConversionResult>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: KikaColors.branco,
      builder: (_) => ConvertSheet(quote: q),
    );
    if (result == null || !mounted) return;
    _refresh();
    ref.invalidate(ordersListProvider);
    showMessage(context, result.created ? 'Pedido ${result.protocol} criado.' : 'Este orçamento já era o pedido ${result.protocol}.');
    context.push('/pedidos/${result.orderId}');
  }

  @override
  Widget build(BuildContext context) {
    final quote = ref.watch(quoteProvider(widget.quoteId));
    final auth = ref.watch(authControllerProvider);
    final storeName = auth is AuthSignedIn ? auth.account.storeName : 'confeitaria';
    return Scaffold(
      appBar: AppBar(title: const Text('Orçamento')),
      body: AsyncBody(
        value: quote,
        onRetry: () => ref.invalidate(quoteProvider(widget.quoteId)),
        data: (q) => ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
          children: [
            FormWidth(
              maxWidth: 680,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  Expanded(child: Text(q.customerName, style: Theme.of(context).textTheme.headlineSmall)),
                  const SizedBox(width: 8),
                  Flexible(child: StatusChip(q.status, icon: QuoteStatus.icon(q.status), color: QuoteStatus.color(q.status))),
                ]),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Pedido de orçamento',
                  child: Column(children: [
                    InfoRow('Protocolo', q.protocol, icon: Icons.tag),
                    InfoRow('Produto', q.productName, icon: Icons.cake_outlined),
                    InfoRow('Quantidade', '${q.quantity} ${q.unit}', icon: Icons.numbers),
                    InfoRow('Data desejada', formatDate(q.desiredDate), icon: Icons.event),
                    InfoRow('Modalidade', q.fulfillment, icon: Icons.local_shipping_outlined),
                    InfoRow('Observações', q.notes.isEmpty ? '—' : q.notes, icon: Icons.notes),
                    InfoRow('Recebido em', formatDateTimeBrt(q.createdAt), icon: Icons.schedule),
                    InfoRow('Origem', q.origin, icon: Icons.campaign_outlined),
                  ]),
                ),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Cliente',
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    InfoRow('WhatsApp', formatPhone(q.whatsapp), icon: Icons.phone_outlined),
                    const SizedBox(height: 8),
                    WhatsAppButton(phone: q.whatsapp, message: q.whatsappMessage(storeName)),
                  ]),
                ),
                const SizedBox(height: 12),
                SectionCard(
                  title: 'Status',
                  trailing: _saving ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : null,
                  child: Wrap(spacing: 8, runSpacing: 8, children: [
                    for (final s in QuoteStatus.all)
                      ChoiceChip(
                        key: Key('quote_status_$s'),
                        avatar: Icon(QuoteStatus.icon(s), size: 18),
                        label: Text(s),
                        selected: q.status == s,
                        onSelected: _saving ? null : (_) => _setStatus(q, s),
                      ),
                  ]),
                ),
                const SizedBox(height: 16),
                if (q.orderId != null)
                  OutlinedButton.icon(
                    key: const Key('quote_open_order'),
                    onPressed: () => context.push('/pedidos/${q.orderId}'),
                    icon: const Icon(Icons.receipt_long_outlined),
                    label: const Text('Ver o pedido deste orçamento'),
                  )
                else
                  FilledButton.icon(
                    key: const Key('quote_convert'),
                    onPressed: q.canConvert && !_saving ? () => _convert(q) : null,
                    icon: const Icon(Icons.swap_horiz),
                    label: const Text('Converter em pedido'),
                  ),
                if (q.status == QuoteStatus.perdido && q.orderId == null)
                  const Padding(
                    padding: EdgeInsets.only(top: 8),
                    child: Text('Orçamento perdido não vira pedido. Mude o status antes, se a cliente voltou.'),
                  ),
              ]),
            ),
          ],
        ),
      ),
    );
  }
}

/// Conversão explícita: a dona confere data, endereço e valor e confirma.
class ConvertSheet extends ConsumerStatefulWidget {
  const ConvertSheet({super.key, required this.quote});

  final Quote quote;

  @override
  ConsumerState<ConvertSheet> createState() => _ConvertSheetState();
}

class _ConvertSheetState extends ConsumerState<ConvertSheet> {
  final _form = GlobalKey<FormState>();
  final _address = TextEditingController();
  final _value = TextEditingController();
  final _notes = TextEditingController();
  late DateTime _date = widget.quote.desiredDate;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _address.dispose();
    _value.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final today = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: _date.isBefore(today) ? today : _date,
      firstDate: DateTime(today.year, today.month, today.day),
      lastDate: today.add(const Duration(days: 365)),
    );
    if (d != null) setState(() => _date = d);
  }

  Future<void> _submit() async {
    if (_loading || !_form.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await ref.read(quotesRepositoryProvider).convert(
            widget.quote.id,
            ConversionInput(
              deliveryDate: _date,
              address: _address.text,
              finalValue: parseMoney(_value.text),
              internalNotes: _notes.text,
            ),
          );
      if (mounted) Navigator.pop(context, result);
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final q = widget.quote;
    final delivery = q.fulfillment == 'Entrega';
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Form(
          key: _form,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('Converter em pedido', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text('${q.productName} · ${q.quantity} ${q.unit} · ${q.customerName}. '
                'O pedido nasce "Confirmado" e o orçamento vira "Venda concluída".'),
            const SizedBox(height: 14),
            if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 12)],
            OutlinedButton.icon(
              key: const Key('convert_date'),
              onPressed: _loading ? null : _pickDate,
              icon: const Icon(Icons.event),
              label: Text('Entrega: ${formatDate(_date)}'),
            ),
            const SizedBox(height: 12),
            if (delivery) ...[
              TextFormField(
                key: const Key('convert_address'),
                controller: _address,
                enabled: !_loading,
                maxLength: 300,
                decoration: const InputDecoration(labelText: 'Endereço de entrega *'),
                validator: (v) => (v ?? '').trim().length < 10 ? 'Informe o endereço (pelo menos 10 caracteres).' : null,
              ),
              const SizedBox(height: 4),
            ],
            TextFormField(
              key: const Key('convert_value'),
              controller: _value,
              enabled: !_loading,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
              decoration: const InputDecoration(
                  labelText: 'Valor final combinado (opcional)', prefixText: 'R\$ ', helperText: 'Vazio: combine depois'),
              validator: (v) {
                if ((v ?? '').trim().isEmpty) return null;
                final n = parseMoney(v!);
                return n == null || n < 0 ? 'Valor inválido.' : null;
              },
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('convert_notes'),
              controller: _notes,
              enabled: !_loading,
              maxLength: 1000,
              maxLines: 3,
              minLines: 1,
              decoration: const InputDecoration(labelText: 'Observações internas (só a confeitaria vê)'),
            ),
            const SizedBox(height: 12),
            LoadingButton(key: const Key('convert_submit'), label: 'Criar pedido', loading: _loading, onPressed: _submit),
          ]),
        ),
      ),
    );
  }
}
