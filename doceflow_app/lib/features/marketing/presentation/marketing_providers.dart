import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/instagram_repository.dart';
import '../data/marketing_api.dart';
import '../domain/marketing.dart';

/// O que está ativo neste build: o estúdio precisa da API de marketing (API_URL) e a publicação
/// precisa do serviço do Instagram (INSTAGRAM_SERVICE_URL). Sem eles, o app explica em vez de falhar.
final marketingFeaturesProvider = Provider<({bool studio, bool instagram})>((ref) => (studio: true, instagram: true));

const postsPageSize = 20;

final postsLimitProvider = StateProvider<int>((ref) => postsPageSize);

final marketingPostsProvider = FutureProvider.autoDispose<({List<MarketingPost> items, int total})>((ref) {
  final limit = ref.watch(postsLimitProvider);
  return ref.watch(marketingApiProvider).list(limit: limit);
});

final postImageProvider = FutureProvider.autoDispose.family<Uint8List, String>(
  (ref, id) => ref.watch(marketingApiProvider).image(id),
);

final instagramAccountProvider = FutureProvider.autoDispose<InstagramAccount>(
  (ref) => ref.watch(instagramRepositoryProvider).account(),
);

final publicationsProvider = FutureProvider.autoDispose<List<Publication>>(
  (ref) => ref.watch(instagramRepositoryProvider).publications(limit: 50),
);

final publicationLogsProvider = FutureProvider.autoDispose.family<List<PublicationLog>, String>(
  (ref, id) => ref.watch(instagramRepositoryProvider).logs(id),
);

void refreshMarketing(WidgetRef ref) {
  ref.invalidate(marketingPostsProvider);
  ref.invalidate(publicationsProvider);
  ref.invalidate(instagramAccountProvider);
}

const templateLabels = {'produto': 'Produto', 'promocao': 'Promoção', 'novidade': 'Novidade'};
const formatLabels = {'feed': 'Feed 1080×1080', 'story': 'Story 1080×1920'};
const toneLabels = {'amigavel': 'Amigável', 'promocional': 'Promocional', 'elegante': 'Elegante'};

String warningText(String w) => switch (w) {
      'sem_foto' => 'O produto não tem foto: a arte usa o logo.',
      'foto_pequena' => 'A foto é pequena para a arte e pode ficar borrada.',
      _ when w.startsWith('texto_abreviado:') => 'Um texto não coube e foi abreviado (${w.split(':').last}).',
      _ => w,
    };
