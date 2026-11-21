import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/format.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../../../core/widgets/states.dart';
import '../../dashboard/presentation/dashboard_page.dart';
import '../data/image_preparer.dart';
import '../data/products_repository.dart';
import '../domain/product.dart';
import 'products_page.dart';
import 'products_providers.dart';

/// Cadastro (id == null) ou edição de produto, com fotos e exclusão.
class ProductFormPage extends ConsumerWidget {
  const ProductFormPage({super.key, this.productId});

  final String? productId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = productId;
    if (id == null) {
      return Scaffold(appBar: AppBar(title: const Text('Novo produto')), body: const _ProductForm(product: null));
    }
    final product = ref.watch(productProvider(id));
    return Scaffold(
      appBar: AppBar(title: const Text('Editar produto')),
      body: AsyncBody(
        value: product,
        onRetry: () => ref.invalidate(productProvider(id)),
        data: (p) => _ProductForm(key: ValueKey(p.id), product: p),
      ),
    );
  }
}

class _ProductForm extends ConsumerStatefulWidget {
  const _ProductForm({super.key, required this.product});

  final Product? product;

  @override
  ConsumerState<_ProductForm> createState() => _ProductFormState();
}

class _ProductFormState extends ConsumerState<_ProductForm> {
  final _form = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.product?.name);
  late final _category = TextEditingController(text: widget.product?.category);
  late final _description = TextEditingController(text: widget.product?.description);
  late final _unit = TextEditingController(text: widget.product?.unit);
  late final _price = TextEditingController(text: moneyInput(widget.product?.price));
  late final _min = TextEditingController(text: '${widget.product?.minQty ?? 1}');
  late final _max = TextEditingController(text: '${widget.product?.maxQty ?? 50}');
  late final _days = TextEditingController(text: widget.product?.productionDays?.toString() ?? '');
  late String _priceType = widget.product?.priceType ?? priceFrom;
  late bool _published = widget.product?.published ?? true;
  late bool _available = widget.product?.available ?? true;
  late bool _featured = widget.product?.featured ?? false;
  bool _saving = false;
  bool _deleting = false;
  String? _error;

  bool get _editing => widget.product != null;

  @override
  void dispose() {
    for (final c in [_name, _category, _description, _unit, _price, _min, _max, _days]) {
      c.dispose();
    }
    super.dispose();
  }

  ProductDraft _draft() => ProductDraft(
        name: _name.text.trim().replaceAll(RegExp(r'\s+'), ' '),
        category: _category.text.trim().replaceAll(RegExp(r'\s+'), ' '),
        description: _description.text.trim(),
        unit: _unit.text.trim().replaceAll(RegExp(r'\s+'), ' '),
        price: parseMoney(_price.text),
        priceType: _priceType,
        available: _available,
        published: _published,
        featured: _featured,
        minQty: int.tryParse(_min.text.trim()) ?? 0,
        maxQty: int.tryParse(_max.text.trim()) ?? 0,
        productionDays: _days.text.trim().isEmpty ? null : int.tryParse(_days.text.trim()) ?? -1,
      );

  void _refreshLists() {
    ref.invalidate(productsListProvider);
    ref.invalidate(dashboardProvider);
  }

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    if (_saving || !_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final repo = ref.read(productsRepositoryProvider);
    try {
      if (_editing) {
        await repo.update(widget.product!.id, _draft());
        ref.invalidate(productProvider(widget.product!.id));
        _refreshLists();
        if (mounted) showMessage(context, 'Produto salvo.');
      } else {
        final id = await repo.create(_draft());
        _refreshLists();
        if (!mounted) return;
        showMessage(context, 'Produto criado. Agora adicione as fotos.');
        context.pushReplacement('/produtos/$id');
      }
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _delete() async {
    final p = widget.product!;
    final ok = await confirmAction(context,
        title: 'Excluir "${p.name}"?',
        message: 'O produto e as fotos saem do catálogo. Esta ação não pode ser desfeita.',
        confirm: 'Excluir',
        danger: true);
    if (!ok || !mounted) return;
    setState(() {
      _deleting = true;
      _error = null;
    });
    try {
      await ref.read(productsRepositoryProvider).delete(p.id);
      _refreshLists();
      if (!mounted) return;
      showMessage(context, 'Produto excluído.');
      context.pop();
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _deleting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final categories = ref.watch(productsListProvider).valueOrNull?.map((p) => p.category).toSet().toList() ?? const [];
    final busy = _saving || _deleting;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      children: [
        FormWidth(
          maxWidth: 640,
          child: Form(
            key: _form,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 12)],
              if (_editing) ...[_PhotosSection(productId: widget.product!.id), const SizedBox(height: 16)],
              TextFormField(
                key: const Key('product_name'),
                controller: _name,
                enabled: !busy,
                maxLength: 120,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(labelText: 'Nome *'),
                validator: (v) => ProductRules.name(v ?? ''),
              ),
              TextFormField(
                key: const Key('product_category'),
                controller: _category,
                enabled: !busy,
                maxLength: 60,
                textCapitalization: TextCapitalization.sentences,
                decoration: InputDecoration(
                  labelText: 'Categoria *',
                  helperText: 'Escolha uma existente ou digite uma nova',
                  suffixIcon: categories.isEmpty
                      ? null
                      : PopupMenuButton<String>(
                          tooltip: 'Categorias existentes',
                          icon: const Icon(Icons.arrow_drop_down),
                          onSelected: (c) => setState(() => _category.text = c),
                          itemBuilder: (_) => [for (final c in categories..sort()) PopupMenuItem(value: c, child: Text(c))],
                        ),
                ),
                validator: (v) => ProductRules.category(v ?? ''),
              ),
              const SizedBox(height: 8),
              TextFormField(
                key: const Key('product_description'),
                controller: _description,
                enabled: !busy,
                maxLength: 500,
                maxLines: 4,
                minLines: 2,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(labelText: 'Descrição'),
                validator: (v) => ProductRules.description(v ?? ''),
              ),
              TextFormField(
                key: const Key('product_unit'),
                controller: _unit,
                enabled: !busy,
                maxLength: 40,
                decoration: const InputDecoration(labelText: 'Unidade *', helperText: 'Ex.: kg, unidade, caixa com 6'),
                validator: (v) => ProductRules.unit(v ?? ''),
              ),
              const SizedBox(height: 8),
              Text('Preço', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(height: 6),
              SegmentedButton<String>(
                key: const Key('product_price_type'),
                segments: [for (final e in priceTypes.entries) ButtonSegment(value: e.key, label: Text(e.value))],
                selected: {_priceType},
                onSelectionChanged: busy ? null : (s) => setState(() => _priceType = s.first),
              ),
              const SizedBox(height: 10),
              if (_priceType != priceOnRequest)
                TextFormField(
                  key: const Key('product_price'),
                  controller: _price,
                  enabled: !busy,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
                  decoration: const InputDecoration(labelText: 'Preço (R\$) *', prefixText: 'R\$ '),
                  validator: (v) => ProductRules.price(parseMoney(v ?? ''), _priceType),
                ),
              const SizedBox(height: 14),
              Row(children: [
                Expanded(
                  child: TextFormField(
                    key: const Key('product_min'),
                    controller: _min,
                    enabled: !busy,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: const InputDecoration(labelText: 'Qtd. mínima *'),
                    validator: (_) => ProductRules.quantities(int.tryParse(_min.text), int.tryParse(_max.text)),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    key: const Key('product_max'),
                    controller: _max,
                    enabled: !busy,
                    keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: const InputDecoration(labelText: 'Qtd. máxima *'),
                  ),
                ),
              ]),
              const SizedBox(height: 14),
              TextFormField(
                key: const Key('product_days'),
                controller: _days,
                enabled: !busy,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(labelText: 'Tempo de produção (dias)', helperText: 'Vazio = não mostrar; 0 = pronta entrega'),
                validator: (v) => ProductRules.productionDays(v == null || v.isEmpty ? null : int.tryParse(v)),
              ),
              const SizedBox(height: 10),
              Card(
                child: Column(children: [
                  SwitchListTile(
                    key: const Key('product_published'),
                    title: const Text('Mostrar na vitrine'),
                    subtitle: const Text('Desligado: o produto some do site, mas continua aqui.'),
                    value: _published,
                    onChanged: busy ? null : (v) => setState(() => _published = v),
                  ),
                  const Divider(height: 1),
                  SwitchListTile(
                    key: const Key('product_available'),
                    title: const Text('Disponível para pedidos'),
                    value: _available,
                    onChanged: busy ? null : (v) => setState(() => _available = v),
                  ),
                  const Divider(height: 1),
                  SwitchListTile(
                    key: const Key('product_featured'),
                    title: const Text('Destaque no catálogo'),
                    value: _featured,
                    onChanged: busy ? null : (v) => setState(() => _featured = v),
                  ),
                ]),
              ),
              const SizedBox(height: 20),
              LoadingButton(
                key: const Key('product_save'),
                label: _editing ? 'Salvar alterações' : 'Cadastrar produto',
                loading: _saving,
                onPressed: _deleting ? null : _save,
              ),
              if (_editing) ...[
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  key: const Key('product_delete'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: KikaColors.erro,
                    side: const BorderSide(color: KikaColors.erro),
                  ),
                  onPressed: busy ? null : _delete,
                  icon: _deleting
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.delete_outline),
                  label: const Text('Excluir produto'),
                ),
              ],
            ]),
          ),
        ),
      ],
    );
  }
}

class _PhotosSection extends ConsumerStatefulWidget {
  const _PhotosSection({required this.productId});

  final String productId;

  @override
  ConsumerState<_PhotosSection> createState() => _PhotosSectionState();
}

class _PhotosSectionState extends ConsumerState<_PhotosSection> {
  bool _busy = false;

  void _refresh() {
    ref.invalidate(productImagesProvider(widget.productId));
    ref.invalidate(productsListProvider);
  }

  Future<void> _run(Future<void> Function() action, String done) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await action();
      _refresh();
      if (mounted && done.isNotEmpty) showMessage(context, done);
    } catch (e) {
      if (mounted) showMessage(context, toFailure(e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _add(PhotoSource source) => _run(() async {
        final jpeg = await ref.read(photoPickerProvider).pick(source);
        if (jpeg == null) return; // cancelou
        await ref.read(productsRepositoryProvider).addImage(widget.productId, jpeg);
      }, 'Foto enviada.');

  Future<void> _options(ProductImage img) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      backgroundColor: KikaColors.branco,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (!img.principal)
            ListTile(
              key: const Key('photo_make_principal'),
              leading: const Icon(Icons.star_outline),
              title: const Text('Usar como foto principal'),
              onTap: () => Navigator.pop(ctx, 'principal'),
            ),
          ListTile(
            key: const Key('photo_delete'),
            leading: const Icon(Icons.delete_outline, color: KikaColors.erro),
            title: const Text('Apagar foto'),
            onTap: () => Navigator.pop(ctx, 'apagar'),
          ),
        ]),
      ),
    );
    if (!mounted || action == null) return;
    final repo = ref.read(productsRepositoryProvider);
    if (action == 'principal') {
      await _run(() => repo.setPrincipal(img.id), 'Foto principal alterada.');
    } else if (await confirmAction(context,
        title: 'Apagar esta foto?', message: 'Ela sai do catálogo.', confirm: 'Apagar', danger: true)) {
      await _run(() => repo.deleteImage(img), 'Foto apagada.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final images = ref.watch(productImagesProvider(widget.productId));
    final count = images.valueOrNull?.length ?? 0;
    final full = count >= ProductRules.maxImages;
    return SectionCard(
      title: 'Fotos',
      trailing: Text('$count/${ProductRules.maxImages}'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        AsyncBody(
          value: images,
          onRetry: () => ref.invalidate(productImagesProvider(widget.productId)),
          data: (list) => list.isEmpty
              ? const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text('Sem fotos: a vitrine mostra a ilustração padrão.'),
                )
              : Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final img in list)
                    Semantics(
                      button: true,
                      label: img.principal ? 'Foto principal. Toque para opções' : 'Foto. Toque para opções',
                      child: InkWell(
                        key: Key('photo_${img.id}'),
                        onTap: _busy ? null : () => _options(img),
                        child: Stack(children: [
                          ProductThumb(url: img.url, size: 88),
                          if (img.principal)
                            const Positioned(
                              right: 4,
                              top: 4,
                              child: CircleAvatar(
                                radius: 12,
                                backgroundColor: KikaColors.destaque,
                                child: Icon(Icons.star, size: 14, color: KikaColors.branco),
                              ),
                            ),
                        ]),
                      ),
                    ),
                ]),
        ),
        const SizedBox(height: 12),
        if (_busy) const LinearProgressIndicator(),
        if (full) const Text('Limite de 10 fotos atingido. Apague uma para enviar outra.'),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(
            child: OutlinedButton.icon(
              key: const Key('photo_camera'),
              onPressed: _busy || full ? null : () => _add(PhotoSource.camera),
              icon: const Icon(Icons.photo_camera_outlined),
              label: const Text('Câmera'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton.icon(
              key: const Key('photo_gallery'),
              onPressed: _busy || full ? null : () => _add(PhotoSource.gallery),
              icon: const Icon(Icons.photo_library_outlined),
              label: const Text('Galeria'),
            ),
          ),
        ]),
        const SizedBox(height: 6),
        Text('As fotos são reduzidas e enviadas sem a localização do celular.',
            style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}
