import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/exporter.dart';
import '../../../core/format.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/whatsapp.dart' show urlOpenerProvider;
import '../../../core/widgets/common.dart';
import '../../../core/widgets/states.dart';
import '../data/instagram_repository.dart';
import '../data/marketing_api.dart';
import '../domain/marketing.dart';
import 'marketing_providers.dart';
import 'studio_view.dart';

class MarketingPage extends ConsumerWidget {
  const MarketingPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final features = ref.watch(marketingFeaturesProvider);
    if (!features.studio) {
      return Scaffold(
        appBar: AppBar(title: const Text('Marketing')),
        body: const EmptyState(
          icon: Icons.campaign_outlined,
          title: 'Estúdio de marketing ainda não ativado',
          message: 'As artes e a publicação no Instagram serão liberadas quando o serviço de marketing do DoceFlow '
              'estiver no ar. Enquanto isso, use o Estúdio de Marketing do painel web.',
        ),
      );
    }
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Marketing'),
          bottom: const TabBar(
            labelColor: KikaColors.marrom,
            indicatorColor: KikaColors.destaque,
            tabs: [Tab(text: 'Criar'), Tab(text: 'Posts'), Tab(text: 'Instagram')],
          ),
        ),
        body: const TabBarView(children: [StudioView(), PostsView(), InstagramView()]),
      ),
    );
  }
}

// ============================================================== posts (rascunhos e histórico)
class PostsView extends ConsumerWidget {
  const PostsView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = ref.watch(marketingPostsProvider);
    final limit = ref.watch(postsLimitProvider);
    return RefreshIndicator(
      color: KikaColors.destaque,
      onRefresh: () async => refreshMarketing(ref),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          AsyncBody(
            value: posts,
            onRetry: () => ref.invalidate(marketingPostsProvider),
            data: (page) {
              if (page.items.isEmpty) {
                return const EmptyState(
                  icon: Icons.photo_library_outlined,
                  title: 'Nenhum post ainda',
                  message: 'Crie uma arte na aba "Criar" e salve como rascunho.',
                );
              }
              return Column(children: [
                for (final p in page.items) ...[
                  Card(
                    child: ListTile(
                      key: Key('post_${p.id}'),
                      leading: Icon(p.format == 'story' ? Icons.stay_current_portrait : Icons.crop_square,
                          color: KikaColors.destaque),
                      title: Text(p.productName),
                      // selo embaixo (e não à direita): com a fonte ampliada do Android não cabia na linha
                      subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${p.formatLabel} · ${formatDateTimeBrt(p.createdAt)}'),
                        const SizedBox(height: 4),
                        StatusChip(p.status, icon: Icons.label_outline, color: KikaColors.destaque),
                      ]),
                      onTap: () => context.push('/marketing/posts/${p.id}', extra: p),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                if (page.items.length < page.total)
                  OutlinedButton(
                    key: const Key('posts_more'),
                    onPressed: () => ref.read(postsLimitProvider.notifier).state = limit + postsPageSize,
                    child: const Text('Carregar mais'),
                  ),
              ]);
            },
          ),
        ],
      ),
    );
  }
}

class PostDetailPage extends ConsumerStatefulWidget {
  const PostDetailPage({super.key, required this.post});

  final MarketingPost? post; // chega pela lista (extra do go_router)

  @override
  ConsumerState<PostDetailPage> createState() => _PostDetailPageState();
}

class _PostDetailPageState extends ConsumerState<PostDetailPage> {
  late MarketingPost? _post = widget.post;
  bool _busy = false;

  Future<void> _run(Future<void> Function() action, String done) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      if (mounted && done.isNotEmpty) showMessage(context, done);
    } catch (e) {
      if (mounted) showMessage(context, toFailure(e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _export(MarketingPost p) => _run(() async {
        final bytes = await ref.read(postImageProvider(p.id).future);
        final name = 'kika-${p.productName.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-')}-${p.format}.png';
        await ref.read(fileExporterProvider).exportPng(bytes, name);
      }, '');

  Future<void> _status(MarketingPost p, String s) => _run(() async {
        await ref.read(marketingApiProvider).setStatus(p.id, s);
        ref.invalidate(marketingPostsProvider);
        setState(() => _post = MarketingPost.fromJson({..._json(p), 'status': s}));
      }, 'Status alterado para "$s".');

  Map<String, dynamic> _json(MarketingPost p) => {
        'id': p.id, 'produto_id': p.productId, 'produto_nome': p.productName, 'template': p.template,
        'formato': p.format, 'titulo': p.title, 'preco_texto': p.priceText, 'cta': p.cta, 'tom': p.tone,
        'legenda': p.caption, 'status': p.status, 'created_at': p.createdAt.toIso8601String(),
      };

  Future<void> _schedule(MarketingPost p) async {
    final result = await showModalBottomSheet<Publication>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: KikaColors.branco,
      builder: (_) => ScheduleSheet(post: p),
    );
    if (result != null && mounted) {
      ref.invalidate(publicationsProvider);
      showMessage(context, result.status == PublicationStatus.agendado
          ? 'Agendado para ${formatDateTimeBrt(result.scheduledFor)}. O status aparece na aba Instagram.'
          : 'Situação: ${PublicationStatus.label(result.status)}.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = _post;
    if (p == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Post')),
        body: const EmptyState(icon: Icons.photo_outlined, title: 'Abra o post pela lista de posts'),
      );
    }
    final image = ref.watch(postImageProvider(p.id));
    final pubs = ref.watch(publicationsProvider).valueOrNull?.where((x) => x.postId == p.id).toList() ?? const [];
    final active = pubs.any((x) => x.status == PublicationStatus.agendado || x.status == PublicationStatus.publicando);
    return Scaffold(
      appBar: AppBar(title: Text(p.productName)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
        children: [
          FormWidth(
            maxWidth: 680,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 460),
                  child: AsyncBody(
                    value: image,
                    onRetry: () => ref.invalidate(postImageProvider(p.id)),
                    data: (bytes) => ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Image.memory(bytes, fit: BoxFit.contain, semanticLabel: 'Arte do post'),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text('${p.formatLabel} · ${templateLabels[p.template] ?? p.template}', textAlign: TextAlign.center),
              if (_busy) const LinearProgressIndicator(),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: OutlinedButton.icon(
                    key: const Key('post_export'),
                    onPressed: _busy ? null : () => _export(p),
                    icon: const Icon(Icons.download_outlined),
                    label: const Text('Exportar PNG'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    key: const Key('post_edit'),
                    onPressed: _busy || active
                        ? null
                        : () async {
                            final updated = await context.push<MarketingPost>('/marketing/editar/${p.id}', extra: p);
                            if (updated != null && mounted) setState(() => _post = updated);
                          },
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('Editar'),
                  ),
                ),
              ]),
              if (active) const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('Agendado no Instagram: cancele o agendamento para editar.'),
              ),
              const SizedBox(height: 12),
              SectionCard(
                title: 'Legenda',
                trailing: IconButton(
                  key: const Key('post_copy_caption'),
                  tooltip: 'Copiar legenda',
                  icon: const Icon(Icons.copy),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: p.caption));
                    if (context.mounted) showMessage(context, 'Legenda copiada.');
                  },
                ),
                child: SelectableText(p.caption.isEmpty ? '—' : p.caption),
              ),
              const SizedBox(height: 12),
              SectionCard(
                title: 'Situação',
                child: Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final s in postStatuses)
                    ChoiceChip(
                      key: Key('post_status_$s'),
                      label: Text(s),
                      selected: p.status == s,
                      onSelected: _busy ? null : (_) => _status(p, s),
                    ),
                ]),
              ),
              const SizedBox(height: 12),
              if (ref.watch(marketingFeaturesProvider).instagram)
              FilledButton.icon(
                key: const Key('post_schedule'),
                onPressed: _busy || active ? null : () => _schedule(p),
                icon: const Icon(Icons.schedule_send),
                label: const Text('Publicar no Instagram'),
              ),
              for (final pub in pubs) ...[const SizedBox(height: 10), PublicationCard(pub)],
            ]),
          ),
        ],
      ),
    );
  }
}

/// Agora ou numa data e hora. A chave de idempotência nasce ao abrir: tocar duas vezes em
/// "Agendar" (ou a rede repetir o pedido) devolve o mesmo agendamento.
class ScheduleSheet extends ConsumerStatefulWidget {
  const ScheduleSheet({super.key, required this.post});

  final MarketingPost post;

  @override
  ConsumerState<ScheduleSheet> createState() => _ScheduleSheetState();
}

class _ScheduleSheetState extends ConsumerState<ScheduleSheet> {
  final _key = const Uuid().v4();
  DateTime? _when; // null = agora
  bool _loading = false;
  String? _error;

  Future<void> _pick() async {
    final now = DateTime.now();
    final d = await showDatePicker(context: context, initialDate: now, firstDate: now, lastDate: now.add(const Duration(days: 75)));
    if (d == null || !mounted) return;
    final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(now.add(const Duration(hours: 1))));
    if (t == null) return;
    setState(() => _when = DateTime(d.year, d.month, d.day, t.hour, t.minute));
  }

  Future<void> _submit() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final pub = await ref.read(instagramRepositoryProvider).schedule(widget.post.id, when: _when, idempotencyKey: _key);
      if (mounted) Navigator.pop(context, pub);
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final account = ref.watch(instagramAccountProvider);
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: AsyncBody<InstagramAccount>(
        value: account,
        onRetry: () => ref.invalidate(instagramAccountProvider),
        data: (acc) => Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Publicar no Instagram', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          if (!acc.connected) ...[
            const InlineMessage('O Instagram não está conectado. Conecte na aba Instagram do Marketing.'),
          ] else ...[
            Text('Conta @${acc.username ?? ''} · ${widget.post.formatLabel}'),
            if (widget.post.format == 'story')
              const Text('Stories não mostram legenda: só a arte é publicada.'),
            const SizedBox(height: 12),
            if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 12)],
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: true, label: Text('Agora')),
                ButtonSegment(value: false, label: Text('Agendar')),
              ],
              selected: {_when == null},
              onSelectionChanged: (s) => s.first ? setState(() => _when = null) : _pick(),
            ),
            if (_when != null) Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text('Para ${formatDate(_when)} às ${_when!.hour.toString().padLeft(2, '0')}:${_when!.minute.toString().padLeft(2, '0')}'),
            ),
            const SizedBox(height: 14),
            LoadingButton(
              key: const Key('schedule_submit'),
              label: _when == null ? 'Publicar agora' : 'Agendar',
              loading: _loading,
              onPressed: _submit,
            ),
            const SizedBox(height: 6),
            Text('A publicação é feita pelo serviço do DoceFlow com a API oficial da Meta. '
                '"Publicado" só aparece quando a Meta confirma.', style: Theme.of(context).textTheme.bodySmall),
          ],
        ]),
      ),
    );
  }
}

// ============================================================== Instagram
class InstagramView extends ConsumerStatefulWidget {
  const InstagramView({super.key});

  @override
  ConsumerState<InstagramView> createState() => _InstagramViewState();
}

class _InstagramViewState extends ConsumerState<InstagramView> {
  bool _busy = false;

  Future<void> _run(Future<void> Function() action, String done) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      refreshMarketing(ref);
      if (mounted && done.isNotEmpty) showMessage(context, done);
    } catch (e) {
      if (mounted) showMessage(context, toFailure(e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connect() => _run(() async {
        final url = await ref.read(instagramRepositoryProvider).connectUrl();
        final opened = await ref.read(urlOpenerProvider)(url);
        if (!opened) throw const AppFailure('Não foi possível abrir a página da Meta neste celular.');
      }, 'Autorize na página da Meta e depois volte aqui e toque em Atualizar.');

  Future<void> _disconnect() async {
    if (!await confirmAction(context,
        title: 'Desconectar o Instagram?',
        message: 'O DoceFlow apaga a autorização e cancela o que estiver agendado.',
        confirm: 'Desconectar',
        danger: true)) {
      return;
    }
    await _run(() => ref.read(instagramRepositoryProvider).disconnect(), 'Instagram desconectado.');
  }

  @override
  Widget build(BuildContext context) {
    if (!ref.watch(marketingFeaturesProvider).instagram) {
      return const EmptyState(
        icon: Icons.schedule_send_outlined,
        title: 'Publicação automática ainda não ativada',
        message: 'Por enquanto, exporte a arte (aba Posts), copie a legenda e publique pelo app do Instagram.',
      );
    }
    final account = ref.watch(instagramAccountProvider);
    final pubs = ref.watch(publicationsProvider);
    return RefreshIndicator(
      color: KikaColors.destaque,
      onRefresh: () async => refreshMarketing(ref),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          AsyncBody<InstagramAccount>(
            value: account,
            onRetry: () => ref.invalidate(instagramAccountProvider),
            data: (acc) => SectionCard(
              title: 'Conta',
              trailing: IconButton(key: const Key('ig_refresh'), tooltip: 'Atualizar', icon: const Icon(Icons.refresh),
                  onPressed: () => refreshMarketing(ref)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (acc.connected) ...[
                  InfoRow('Conta', '@${acc.username ?? ''}', icon: Icons.camera_alt_outlined),
                  InfoRow('Tipo', acc.accountType == 'business' ? 'Empresa' : 'Criador de conteúdo', icon: Icons.badge_outlined),
                  if (acc.expiresAt != null)
                    InfoRow('Autorização', 'renovada automaticamente (vale até ${formatDate(acc.expiresAt!.toLocal())})',
                        icon: Icons.lock_clock_outlined),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(key: const Key('ig_disconnect'), onPressed: _busy ? null : _disconnect,
                      icon: const Icon(Icons.link_off), label: const Text('Desconectar')),
                ] else ...[
                  if (acc.status == 'erro')
                    InlineMessage(acc.lastError ?? 'A autorização do Instagram precisa ser refeita.')
                  else
                    const Text('Para publicar pelo DoceFlow, conecte a conta PROFISSIONAL (Empresa ou Criador) da '
                        'confeitaria. A autorização é feita na página oficial da Meta; o DoceFlow nunca pede a senha '
                        'do Instagram.'),
                  const SizedBox(height: 10),
                  FilledButton.icon(key: const Key('ig_connect'), onPressed: _busy ? null : _connect,
                      icon: const Icon(Icons.link), label: Text(acc.status == 'erro' ? 'Conectar de novo' : 'Conectar Instagram')),
                ],
              ]),
            ),
          ),
          const SizedBox(height: 16),
          Text('Publicações', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          AsyncBody<List<Publication>>(
            value: pubs,
            onRetry: () => ref.invalidate(publicationsProvider),
            data: (list) => list.isEmpty
                ? const EmptyState(icon: Icons.schedule_send_outlined, title: 'Nada agendado ainda',
                    message: 'Abra um post e toque em "Publicar no Instagram".')
                : Column(children: [for (final p in list) ...[PublicationCard(p), const SizedBox(height: 10)]]),
          ),
        ],
      ),
    );
  }
}

class PublicationCard extends ConsumerStatefulWidget {
  const PublicationCard(this.pub, {super.key});

  final Publication pub;

  @override
  ConsumerState<PublicationCard> createState() => _PublicationCardState();
}

class _PublicationCardState extends ConsumerState<PublicationCard> {
  bool _busy = false;
  bool _showLogs = false;

  Future<void> _act(Future<void> Function() action, String done) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      refreshMarketing(ref);
      ref.invalidate(publicationLogsProvider(widget.pub.id));
      if (mounted) showMessage(context, done);
    } catch (e) {
      if (mounted) showMessage(context, toFailure(e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.pub;
    final repo = ref.read(instagramRepositoryProvider);
    final t = Theme.of(context).textTheme;
    return Card(
      key: Key('pub_${p.id}'),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Expanded(child: Text(p.format == 'story' ? 'Story' : 'Feed', style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700))),
            Flexible(child: StatusChip(PublicationStatus.label(p.status), icon: PublicationStatus.icon(p.status),
                color: PublicationStatus.color(p.status))),
          ]),
          const SizedBox(height: 4),
          Text(p.confirmedByMeta
              ? 'Publicado em ${formatDateTimeBrt(p.publishedAt)}'
              : 'Para ${formatDateTimeBrt(p.scheduledFor)} · tentativas ${p.attempts}/${p.maxAttempts}'),
          if (p.errorMessage != null && p.status != PublicationStatus.publicado)
            Padding(padding: const EdgeInsets.only(top: 4), child: Text(p.errorMessage!, style: t.bodySmall)),
          if (p.status == PublicationStatus.verificar)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text('Abra o Instagram e confira se o post saiu antes de publicar de novo.'),
            ),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 4, children: [
            if (p.confirmedByMeta && p.permalink != null)
              TextButton.icon(
                key: Key('pub_open_${p.id}'),
                onPressed: () => ref.read(urlOpenerProvider)(Uri.parse(p.permalink!)),
                icon: const Icon(Icons.open_in_new),
                label: const Text('Ver no Instagram'),
              ),
            if (p.canCancel)
              TextButton(key: Key('pub_cancel_${p.id}'), onPressed: _busy ? null : () => _act(() => repo.cancel(p.id), 'Agendamento cancelado.'),
                  child: const Text('Cancelar')),
            if (p.canRetry)
              TextButton(key: Key('pub_retry_${p.id}'), onPressed: _busy ? null : () => _act(() => repo.retry(p.id), 'Nova tentativa agendada.'),
                  child: const Text('Tentar de novo')),
            TextButton(key: Key('pub_logs_${p.id}'), onPressed: () => setState(() => _showLogs = !_showLogs),
                child: Text(_showLogs ? 'Esconder histórico' : 'Histórico')),
          ]),
          if (_showLogs)
            AsyncBody<List<PublicationLog>>(
              value: ref.watch(publicationLogsProvider(p.id)),
              onRetry: () => ref.invalidate(publicationLogsProvider(p.id)),
              data: (logs) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                for (final l in logs)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text('${formatDateTimeBrt(l.at)} · ${l.label}', style: t.bodySmall),
                  ),
              ]),
            ),
        ]),
      ),
    );
  }
}
