import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app.dart';
import 'core/config/app_config.dart';
import 'core/storage/secure_session_storage.dart';
import 'features/auth/application/auth_controller.dart';
import 'core/errors/app_failure.dart';
import 'features/auth/data/supabase_auth_repository.dart';
import 'features/marketing/data/instagram_repository.dart';
import 'features/marketing/data/marketing_api.dart';
import 'features/marketing/presentation/marketing_providers.dart';
import 'features/orders/data/orders_repository.dart';
import 'features/products/data/products_repository.dart';
import 'features/quotes/data/quotes_repository.dart';
import 'features/dashboard/data/dashboard_repository.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('pt_BR');

  final AppConfig config;
  try {
    config = AppConfig.fromEnvironment();
  } on AppConfigError catch (e) {
    runApp(ConfigErrorApp(e.message));
    return;
  }

  final sessionStorage = SecureSessionStorage();
  await Supabase.initialize(
    url: config.supabaseUrl,
    publishableKey: config.supabaseKey, // chave publishable: a proteção dos dados é o RLS
    authOptions: FlutterAuthClientOptions(
      localStorage: sessionStorage,
      autoRefreshToken: true,
    ),
    debug: false,
  );
  final client = Supabase.instance.client;

  runApp(
    ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(
          SupabaseAuthRepository(client, storeSlug: config.storeSlug, localStorage: sessionStorage),
        ),
        dashboardRepositoryProvider.overrideWithValue(SupabaseDashboardRepository(client)),
        // Repositórios da confeitaria do perfil logado (o banco confere de novo pelo RLS).
        productsRepositoryProvider.overrideWith((ref) => SupabaseProductsRepository(client, storeId: _storeId(ref))),
        quotesRepositoryProvider.overrideWith((ref) => SupabaseQuotesRepository(client, storeId: _storeId(ref))),
        ordersRepositoryProvider.overrideWith((ref) => SupabaseOrdersRepository(client, storeId: _storeId(ref))),
        // Marketing: a arte é gerada pela API (doceflow/api); o Instagram, só pelo serviço no servidor.
        marketingFeaturesProvider.overrideWithValue(
            (studio: config.apiUrl != null, instagram: config.apiUrl != null && config.instagramServiceUrl != null)),
        if (config.apiUrl != null)
          marketingApiProvider.overrideWithValue(
            HttpMarketingApi(baseUrl: config.apiUrl!, accessToken: () => client.auth.currentSession?.accessToken),
          ),
        instagramRepositoryProvider.overrideWith((ref) =>
            SupabaseInstagramRepository(client, storeId: _storeId(ref), serviceUrl: config.instagramServiceUrl)),
      ],
      child: const DoceFlowApp(),
    ),
  );
}

String _storeId(Ref ref) {
  final auth = ref.watch(authControllerProvider);
  if (auth is AuthSignedIn) return auth.account.storeId;
  throw const AppFailure('Sua sessão terminou. Entre novamente.', kind: FailureKind.expired);
}
