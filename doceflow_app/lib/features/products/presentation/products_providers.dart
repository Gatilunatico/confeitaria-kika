import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/products_repository.dart';
import '../domain/product.dart';

final productsListProvider = FutureProvider.autoDispose<List<Product>>(
  (ref) => ref.watch(productsRepositoryProvider).list(),
);

final productProvider = FutureProvider.autoDispose.family<Product, String>(
  (ref, id) => ref.watch(productsRepositoryProvider).get(id),
);

final productImagesProvider = FutureProvider.autoDispose.family<List<ProductImage>, String>(
  (ref, id) => ref.watch(productsRepositoryProvider).images(id),
);

enum ProductFilter { todos, publicados, ocultos, indisponiveis }
