import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';

class DoceFlowApp extends ConsumerWidget {
  const DoceFlowApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Kika Cakes · DoceFlow',
      debugShowCheckedModeBanner: false,
      theme: buildKikaTheme(),
      routerConfig: ref.watch(routerProvider),
      locale: const Locale('pt', 'BR'),
      supportedLocales: const [Locale('pt', 'BR')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}

/// Mostrada quando o build não tem a configuração do Supabase (nunca há dados de exemplo).
class ConfigErrorApp extends StatelessWidget {
  const ConfigErrorApp(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildKikaTheme(),
      home: Scaffold(
        body: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(
                'O app não foi configurado corretamente.\n\n$message\n\nFale com o suporte do DoceFlow.',
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
