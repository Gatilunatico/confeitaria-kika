import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../application/auth_controller.dart';

/// Abertura: mostra o logo enquanto confere a sessão salva no servidor.
class SplashPage extends ConsumerWidget {
  const SplashPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const KikaLogo(size: 200),
                const SizedBox(height: 16),
                Text('Painel da confeitaria', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 28),
                if (auth is AuthRestoreFailed) ...[
                  InlineMessage(auth.message),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: 240,
                    child: FilledButton.icon(
                      onPressed: () => ref.read(authControllerProvider.notifier).restore(),
                      icon: const Icon(Icons.refresh),
                      label: const Text('Tentar de novo'),
                    ),
                  ),
                  TextButton(
                    onPressed: () => ref.read(authControllerProvider.notifier).signOut(),
                    child: const Text('Entrar com outra conta'),
                  ),
                ] else
                  Semantics(
                    label: 'Carregando',
                    child: const CircularProgressIndicator(color: KikaColors.destaque),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
