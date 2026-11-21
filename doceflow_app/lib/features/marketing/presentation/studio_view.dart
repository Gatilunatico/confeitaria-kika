import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:uuid/uuid.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../../core/widgets/states.dart';
import '../../products/domain/product.dart';
import '../../products/presentation/products_page.dart' show ProductThumb;
import '../../products/presentation/products_providers.dart';
import '../data/marketing_api.dart';
import '../domain/marketing.dart';
import 'marketing_providers.dart';

/// Estúdio: produto e foto reais → arte (Feed/Story) com a identidade da Kika → textos,
/// legenda e hashtags → prévia → salvar rascunho. Com [editing], atualiza um post existente.
class StudioView extends ConsumerStatefulWidget {
  const StudioView({super.key, this.editing});

  final MarketingPost? editing;

  @override
  ConsumerState<StudioView> createState() => _StudioViewState();
}

class _StudioViewState extends ConsumerState<StudioView> {
  late String? _productId = widget.editing?.productId;
  String? _imageId; // null = principal
  bool _usePhoto = true;
  late String _template = widget.editing?.template ?? 'produto';
  late String _format = widget.editing?.format ?? 'feed';
  late String _tone = widget.editing?.tone ?? 'amigavel';
  late final _title = TextEditingController(text: widget.editing?.title);
  late final _price = TextEditingController(text: widget.editing?.priceText);
  late final _cta = TextEditingController(text: widget.editing?.cta);
  final _extra = TextEditingController();
  final _caption = TextEditingController();
  final _newTag = TextEditingController();
  List<String> _tags = [];
  ArtPreview? _preview;
  bool _loading = false;
  bool _saving = false;
  String? _error;
  String _saveKey = const Uuid().v4(); // mesma chave enquanto este rascunho não for salvo

  @override
  void initState() {
    super.initState();
    final e = widget.editing;
    if (e != null) {
      final parts = e.caption.split('\n\n');
      final last = parts.isEmpty ? '' : parts.last.trim();
      if (parts.length > 1 && last.split(RegExp(r'\s+')).every((t) => t.startsWith('#'))) {
        _tags = last.split(RegExp(r'\s+'));
        _caption.text = parts.sublist(0, parts.length - 1).join('\n\n');
      } else {
        _caption.text = e.caption;
      }
    }
  }

  @override
  void dispose() {
    for (final c in [_title, _price, _cta, _extra, _caption, _newTag]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _opt(TextEditingController c) => c.text.trim().isEmpty ? null : c.text.trim();

  ArtRequest _request() => ArtRequest(
        productId: _productId!,
        imageId: _usePhoto ? _imageId : null,
        usePhoto: _usePhoto,
        template: _template,
        format: _format,
        tone: _tone,
        title: _opt(_title),
        priceText: _opt(_price),
        cta: _opt(_cta),
        extra: _extra.text.trim(),
      );

  String get _finalCaption => composeCaption(_caption.text, _tags);

  Future<void> _generate() async {
    if (_productId == null) {
      setState(() => _error = 'Escolha um produto.');
      return;
    }
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final p = await ref.read(marketingApiProvider).preview(_request());
      if (!mounted) return;
      setState(() {
        _preview = p;
        if (_title.text.isEmpty) _title.text = p.title;
        if (_price.text.isEmpty) _price.text = p.priceText;
        if (_cta.text.isEmpty) _cta.text = p.cta;
        if (_caption.text.trim().isEmpty) _caption.text = p.captionBody;
        if (_tags.isEmpty) _tags = List.of(p.hashtags);
      });
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save({String status = 'Rascunho'}) async {
    if (_saving || _productId == null) return;
    final caption = _finalCaption;
    if (caption.length > maxCaption) {
      setState(() => _error = 'A legenda passou de $maxCaption caracteres.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final api = ref.read(marketingApiProvider);
    try {
      final post = widget.editing == null
          ? await api.save(_request(), caption: caption, idempotencyKey: _saveKey)
          : await api.update(widget.editing!.id, _request(), caption: caption, status: status);
      ref.invalidate(marketingPostsProvider);
      ref.invalidate(postImageProvider(post.id));
      if (!mounted) return;
      _saveKey = const Uuid().v4();
      showMessage(context, widget.editing == null ? 'Post salvo nos rascunhos.' : 'Post atualizado.');
      if (widget.editing == null) {
        context.push('/marketing/posts/${post.id}', extra: post);
      } else {
        context.pop(post);
      }
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _addTag() {
    final t = normalizeHashtag(_newTag.text);
    if (t == null) return;
    setState(() {
      if (!_tags.contains(t) && _tags.length < maxHashtags) _tags.add(t);
      _newTag.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(productsListProvider);
    final t = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      children: [
        FormWidth(
          maxWidth: 680,
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 12)],
            AsyncBody(
              value: products,
              onRetry: () => ref.invalidate(productsListProvider),
              data: (list) => list.isEmpty
                  ? const EmptyState(icon: Icons.cake_outlined, title: 'Cadastre um produto primeiro')
                  : DropdownButtonFormField<String>(
                      key: const Key('studio_product'),
                      initialValue: list.any((p) => p.id == _productId) ? _productId : null,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'Produto'),
                      items: [for (final p in list) DropdownMenuItem(value: p.id, child: Text(p.name, overflow: TextOverflow.ellipsis))],
                      onChanged: (v) => setState(() {
                        _productId = v;
                        _imageId = null;
                        _preview = null;
                        _title.clear();
                        _price.clear();
                      }),
                    ),
            ),
            if (_productId != null) ...[const SizedBox(height: 12), _PhotoPicker(
              productId: _productId!,
              selected: _imageId,
              usePhoto: _usePhoto,
              onChanged: (id, use) => setState(() {
                _imageId = id;
                _usePhoto = use;
              }),
            )],
            const SizedBox(height: 14),
            _Choice(label: 'Modelo', keyPrefix: 'studio_template', options: templateLabels, value: _template,
                onChanged: (v) => setState(() => _template = v)),
            _Choice(label: 'Formato', keyPrefix: 'studio_format', options: formatLabels, value: _format,
                onChanged: (v) => setState(() => _format = v)),
            _Choice(label: 'Tom da legenda', keyPrefix: 'studio_tone', options: toneLabels, value: _tone,
                onChanged: (v) => setState(() => _tone = v)),
            const SizedBox(height: 8),
            TextField(key: const Key('studio_title'), controller: _title, maxLength: 120,
                decoration: const InputDecoration(labelText: 'Título da arte', helperText: 'Vazio = sugestão do DoceFlow')),
            TextField(key: const Key('studio_price'), controller: _price, maxLength: 80,
                decoration: const InputDecoration(labelText: 'Texto do preço')),
            TextField(key: const Key('studio_cta'), controller: _cta, maxLength: 60,
                decoration: const InputDecoration(labelText: 'Chamada (ex.: Peça seu orçamento)')),
            TextField(key: const Key('studio_extra'), controller: _extra, maxLength: 300,
                decoration: const InputDecoration(labelText: 'Frase extra na legenda (opcional)')),
            const SizedBox(height: 8),
            LoadingButton(key: const Key('studio_preview'), label: 'Gerar prévia', loading: _loading, onPressed: _generate),
            if (_preview != null) ...[
              const SizedBox(height: 16),
              Text('Prévia (${_preview!.width}×${_preview!.height})', style: t.titleMedium),
              const SizedBox(height: 8),
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 460),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: Image.memory(_preview!.png, key: const Key('studio_image'), fit: BoxFit.contain,
                        semanticLabel: 'Prévia da arte'),
                  ),
                ),
              ),
              for (final w in _preview!.warnings) Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('⚠ ${warningText(w)}', style: t.bodySmall),
              ),
            ],
            if (_preview != null || widget.editing != null) ...[
              const SizedBox(height: 16),
              TextField(
                key: const Key('studio_caption'),
                controller: _caption,
                minLines: 4,
                maxLines: 10,
                onChanged: (_) => setState(() {}),
                decoration: InputDecoration(
                  labelText: _format == 'story' ? 'Legenda (Stories não mostram legenda; fica para copiar)' : 'Legenda',
                  helperText: '${_finalCaption.length}/$maxCaption caracteres com as hashtags',
                ),
              ),
              const SizedBox(height: 10),
              Text('Hashtags (${_tags.length}/$maxHashtags)', style: t.titleMedium),
              Wrap(spacing: 6, runSpacing: 6, children: [
                for (final tag in _tags)
                  InputChip(
                    key: Key('tag_$tag'),
                    label: Text(tag),
                    onDeleted: () => setState(() => _tags.remove(tag)),
                    deleteButtonTooltipMessage: 'Remover $tag',
                  ),
              ]),
              Row(children: [
                Expanded(
                  child: TextField(
                    key: const Key('studio_new_tag'),
                    controller: _newTag,
                    decoration: const InputDecoration(labelText: 'Nova hashtag'),
                    onSubmitted: (_) => _addTag(),
                  ),
                ),
                IconButton(key: const Key('studio_add_tag'), tooltip: 'Adicionar hashtag', onPressed: _addTag,
                    icon: const Icon(Icons.add_circle_outline, color: KikaColors.marrom)),
              ]),
              const SizedBox(height: 16),
              if (_preview == null && widget.editing != null)
                const Text('Gere a prévia para conferir a arte antes de salvar.'),
              LoadingButton(
                key: const Key('studio_save'),
                label: widget.editing == null ? 'Salvar rascunho' : 'Salvar alterações',
                loading: _saving,
                onPressed: _preview == null ? null : () => _save(status: widget.editing?.status ?? 'Rascunho'),
              ),
            ],
          ]),
        ),
      ],
    );
  }
}

class _Choice extends StatelessWidget {
  const _Choice({required this.label, required this.keyPrefix, required this.options, required this.value, required this.onChanged});

  final String label;
  final String keyPrefix;
  final Map<String, String> options;
  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Wrap(spacing: 8, runSpacing: 6, children: [
          for (final e in options.entries)
            ChoiceChip(key: Key('${keyPrefix}_${e.key}'), label: Text(e.value), selected: value == e.key,
                onSelected: (_) => onChanged(e.key)),
        ]),
      ]),
    );
  }
}

/// Fotos REAIS do produto (bucket product-images) ou "sem foto" (arte com o logo).
class _PhotoPicker extends ConsumerWidget {
  const _PhotoPicker({required this.productId, required this.selected, required this.usePhoto, required this.onChanged});

  final String productId;
  final String? selected;
  final bool usePhoto;
  final void Function(String? imageId, bool usePhoto) onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final images = ref.watch(productImagesProvider(productId));
    return AsyncBody<List<ProductImage>>(
      value: images,
      onRetry: () => ref.invalidate(productImagesProvider(productId)),
      data: (list) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Foto', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        if (list.isEmpty) const Text('Este produto ainda não tem fotos: a arte usa o logo.'),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final img in list)
            InkWell(
              key: Key('studio_photo_${img.id}'),
              onTap: () => onChanged(img.id, true),
              child: Container(
                padding: const EdgeInsets.all(3),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    width: 3,
                    color: usePhoto && (selected == img.id || (selected == null && img.principal))
                        ? KikaColors.destaque
                        : Colors.transparent,
                  ),
                ),
                child: ProductThumb(url: img.url, size: 64),
              ),
            ),
          ChoiceChip(key: const Key('studio_no_photo'), label: const Text('Sem foto (logo)'), selected: !usePhoto,
              onSelected: (_) => onChanged(null, false)),
        ]),
      ]),
    );
  }
}
