import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/states.dart';
import '../domain/product.dart';
import 'products_providers.dart';

class ProductsPage extends ConsumerStatefulWidget {
  const ProductsPage({super.key});

  @override
  ConsumerState<ProductsPage> createState() => _ProductsPageState();
}

class _ProductsPageState extends ConsumerState<ProductsPage> {
  String _search = '';
  ProductFilter _filter = ProductFilter.todos;

  List<Product> _apply(List<Product> all) {
    final q = _search.trim().toLowerCase();
    return all.where((p) {
      final okFilter = switch (_filter) {
        ProductFilter.todos => true,
        ProductFilter.publicados => p.published,
        ProductFilter.ocultos => !p.published,
        ProductFilter.indisponiveis => !p.available,
      };
      return okFilter && (q.isEmpty || p.name.toLowerCase().contains(q) || p.category.toLowerCase().contains(q));
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(productsListProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Produtos')),
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('product_new'),
        backgroundColor: KikaColors.marrom,
        foregroundColor: KikaColors.branco,
        onPressed: () => context.push('/produtos/novo'),
        icon: const Icon(Icons.add),
        label: const Text('Novo produto'),
      ),
      body: RefreshIndicator(
        color: KikaColors.destaque,
        onRefresh: () async => ref.invalidate(productsListProvider),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 96),
          children: [
            TextField(
              key: const Key('product_search'),
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), labelText: 'Buscar por nome ou categoria'),
              onChanged: (v) => setState(() => _search = v),
            ),
            const SizedBox(height: 10),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final f in ProductFilter.values)
                ChoiceChip(
                  label: Text(switch (f) {
                    ProductFilter.todos => 'Todos',
                    ProductFilter.publicados => 'Na vitrine',
                    ProductFilter.ocultos => 'Ocultos',
                    ProductFilter.indisponiveis => 'Indisponíveis',
                  }),
                  selected: _filter == f,
                  onSelected: (_) => setState(() => _filter = f),
                ),
            ]),
            const SizedBox(height: 12),
            AsyncBody(
              value: products,
              onRetry: () => ref.invalidate(productsListProvider),
              data: (all) {
                if (all.isEmpty) {
                  return const EmptyState(
                    icon: Icons.cake_outlined,
                    title: 'Nenhum produto cadastrado',
                    message: 'Toque em "Novo produto" para cadastrar o primeiro.',
                  );
                }
                final shown = _apply(all);
                if (shown.isEmpty) {
                  return const EmptyState(icon: Icons.search_off, title: 'Nada encontrado', message: 'Mude a busca ou o filtro.');
                }
                return Column(children: [
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text('${shown.length} de ${all.length} produto(s)', style: Theme.of(context).textTheme.bodySmall),
                  ),
                  const SizedBox(height: 6),
                  for (final p in shown) ...[_ProductTile(p), const SizedBox(height: 10)],
                ]);
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _ProductTile extends StatelessWidget {
  const _ProductTile(this.p);

  final Product p;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/produtos/${p.id}'),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(children: [
            ProductThumb(url: p.photoUrl, size: 64),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(p.name, style: t.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                Text(p.category, style: t.bodySmall),
                const SizedBox(height: 2),
                Text(p.priceLabel, style: t.bodyMedium),
                const SizedBox(height: 6),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  if (!p.published) const StatusChip('Oculto', icon: Icons.visibility_off_outlined, color: Color(0xFF8D6E63)),
                  if (!p.available) const StatusChip('Indisponível', icon: Icons.block, color: Color(0xFF8D6E63)),
                  if (p.featured) const StatusChip('Destaque', icon: Icons.star_outline, color: KikaColors.destaque),
                ]),
              ]),
            ),
            const Icon(Icons.chevron_right),
          ]),
        ),
      ),
    );
  }
}

class ProductThumb extends StatelessWidget {
  const ProductThumb({super.key, required this.url, this.size = 64});

  final String? url;
  final double size;

  @override
  Widget build(BuildContext context) {
    final placeholder = Container(
      width: size,
      height: size,
      color: KikaColors.rosa,
      child: const Icon(Icons.cake_outlined, color: KikaColors.destaque),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: url == null
          ? placeholder
          : Image.network(url!, width: size, height: size, fit: BoxFit.cover, errorBuilder: (_, __, ___) => placeholder),
    );
  }
}
