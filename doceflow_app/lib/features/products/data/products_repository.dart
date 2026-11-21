import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:uuid/uuid.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/product.dart';

abstract interface class ProductsRepository {
  Future<List<Product>> list();
  Future<Product> get(String id);
  Future<String> create(ProductDraft draft);
  Future<void> update(String id, ProductDraft draft);
  Future<void> delete(String id);
  Future<List<ProductImage>> images(String productId);

  /// [jpeg] já comprimido e sem metadados (ver image_preparer.dart).
  Future<ProductImage> addImage(String productId, Uint8List jpeg);
  Future<void> setPrincipal(String imageId);
  Future<void> deleteImage(ProductImage image);
}

final productsRepositoryProvider = Provider<ProductsRepository>(
  (ref) => throw UnimplementedError('productsRepositoryProvider precisa ser configurado no main.dart'),
);

/// Tudo com o login da dona: o RLS do banco e as políticas do Storage decidem o que pode.
class SupabaseProductsRepository implements ProductsRepository {
  SupabaseProductsRepository(this._client, {required this.storeId});

  static const bucket = 'product-images';
  static const _imageColumns = 'id,produto_id,storage_path,principal,ordem';

  final SupabaseClient _client;
  final String storeId;

  Future<T> _guard<T>(Future<T> Function() action) async {
    try {
      return await action();
    } catch (e) {
      throw toFailure(e);
    }
  }

  String _url(String path) => _client.storage.from(bucket).getPublicUrl(path);

  ProductImage _image(Map<String, dynamic> r) => ProductImage(
        id: r['id'] as String,
        path: r['storage_path'] as String,
        url: _url(r['storage_path'] as String),
        principal: r['principal'] as bool? ?? false,
        order: (r['ordem'] as num?)?.toInt() ?? 0,
      );

  /// Foto principal de cada produto (sem principal marcada: a primeira pela ordem).
  Map<String, String> _covers(List<Map<String, dynamic>> rows) {
    final best = <String, Map<String, dynamic>>{};
    for (final r in rows) {
      final pid = r['produto_id'] as String;
      final cur = best[pid];
      final better = cur == null ||
          ((r['principal'] == true) && cur['principal'] != true) ||
          ((r['principal'] == true) == (cur['principal'] == true) &&
              ((r['ordem'] as num) < (cur['ordem'] as num)));
      if (better) best[pid] = r;
    }
    return {for (final e in best.entries) e.key: _url(e.value['storage_path'] as String)};
  }

  @override
  Future<List<Product>> list() => _guard(() async {
        final rows = await _client
            .from('produtos')
            .select(Product.columns)
            .eq('confeitaria_id', storeId)
            .order('ordem', ascending: true)
            .order('nome', ascending: true);
        final imgs = await _client.from('product_images').select(_imageColumns).eq('confeitaria_id', storeId);
        final covers = _covers(imgs);
        return [for (final r in rows) Product.fromJson(r, photoUrl: covers[r['id']])];
      });

  @override
  Future<Product> get(String id) => _guard(() async {
        final row = await _client.from('produtos').select(Product.columns).eq('id', id).eq('confeitaria_id', storeId).maybeSingle();
        if (row == null) throw const AppFailure('Produto não encontrado nesta confeitaria.');
        return Product.fromJson(row);
      });

  @override
  Future<String> create(ProductDraft draft) => _guard(() async {
        // Sem slug: o banco gera a partir do nome, sem repetir (gatilho da migração 012).
        final row = await _client
            .from('produtos')
            .insert({'confeitaria_id': storeId, ...draft.toColumns()})
            .select('id')
            .single();
        return row['id'] as String;
      });

  @override
  Future<void> update(String id, ProductDraft draft) => _guard(() async {
        final rows = await _client
            .from('produtos')
            .update(draft.toColumns())
            .eq('id', id)
            .eq('confeitaria_id', storeId)
            .select('id');
        if (rows.isEmpty) throw const AppFailure('Produto não encontrado nesta confeitaria.');
      });

  @override
  Future<void> delete(String id) => _guard(() async {
        final paths = (await images(id)).map((i) => i.path).toList();
        // Com orçamentos ou pedidos, o banco recusa (23503) e nada é apagado.
        final rows = await _client.from('produtos').delete().eq('id', id).eq('confeitaria_id', storeId).select('id');
        if (rows.isEmpty) throw const AppFailure('Produto não encontrado nesta confeitaria.');
        if (paths.isNotEmpty) {
          try {
            await _client.storage.from(bucket).remove(paths); // registros já saíram em cascata
          } catch (_) {
            // arquivo órfão no Storage não quebra nada; o registro já foi apagado
          }
        }
      });

  @override
  Future<List<ProductImage>> images(String productId) => _guard(() async {
        final rows = await _client
            .from('product_images')
            .select(_imageColumns)
            .eq('produto_id', productId)
            .eq('confeitaria_id', storeId)
            .order('ordem', ascending: true);
        return rows.map(_image).toList();
      });

  @override
  Future<ProductImage> addImage(String productId, Uint8List jpeg) => _guard(() async {
        if (jpeg.lengthInBytes > ProductRules.maxImageBytes) {
          throw const AppFailure('Foto grande demais (máximo 5 MB).', kind: FailureKind.validation);
        }
        final current = await images(productId);
        if (current.length >= ProductRules.maxImages) {
          throw const AppFailure('Cada produto pode ter no máximo 10 fotos.', kind: FailureKind.validation);
        }
        final imageId = const Uuid().v4();
        final path = '$storeId/$productId/$imageId.jpg';
        await _client.storage.from(bucket).uploadBinary(
              path,
              jpeg,
              fileOptions: const FileOptions(contentType: 'image/jpeg', upsert: false),
            );
        try {
          final row = await _client
              .from('product_images')
              .insert({
                'id': imageId,
                'confeitaria_id': storeId,
                'produto_id': productId,
                'storage_path': path,
                'alt_text': '',
                'principal': !current.any((i) => i.principal),
                'ordem': current.fold<int>(0, (m, i) => i.order > m ? i.order : m) + 1,
              })
              .select(_imageColumns)
              .single();
          return _image(row);
        } catch (e) {
          // registro recusado (limite, permissão): não deixa o arquivo sozinho no Storage
          try {
            await _client.storage.from(bucket).remove([path]);
          } catch (_) {}
          rethrow;
        }
      });

  @override
  Future<void> setPrincipal(String imageId) =>
      _guard(() => _client.rpc('definir_foto_principal', params: {'p_image_id': imageId}));

  @override
  Future<void> deleteImage(ProductImage image) => _guard(() async {
        final rows = await _client.from('product_images').delete().eq('id', image.id).eq('confeitaria_id', storeId).select('id,produto_id');
        if (rows.isEmpty) throw const AppFailure('Foto não encontrada nesta confeitaria.');
        try {
          await _client.storage.from(bucket).remove([image.path]);
        } catch (_) {}
        if (image.principal) {
          final rest = await images(rows.first['produto_id'] as String);
          if (rest.isNotEmpty) await setPrincipal(rest.first.id); // promove a próxima
        }
      });
}
