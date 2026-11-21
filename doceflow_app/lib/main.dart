import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'app.dart';
import 'core/config/app_config.dart';
import 'core/storage/secure_session_storage.dart';
import 'features/auth/application/auth_controller.dart';
import 'features/auth/data/supabase_auth_repository.dart';
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
      ],
      child: const DoceFlowApp(),
    ),
  );
}
