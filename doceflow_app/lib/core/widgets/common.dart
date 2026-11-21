import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Logo oficial, exibido inteiro (sem recorte, filtro ou recoloração) e só redimensionado.
class KikaLogo extends StatelessWidget {
  const KikaLogo({super.key, this.size = 160});

  static const asset = 'assets/logo/logo-kika-cakes.png';
  final double size;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Logo Kika Cakes Confeitaria',
      image: true,
      child: Image.asset(asset, width: size, height: size, fit: BoxFit.contain, filterQuality: FilterQuality.medium),
    );
  }
}

/// Botão principal com estado de carregamento (evita toque duplo enquanto envia).
class LoadingButton extends StatelessWidget {
  const LoadingButton({super.key, required this.label, required this.loading, required this.onPressed});

  final String label;
  final bool loading;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: loading ? null : onPressed,
      child: loading
          ? const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2.4, color: KikaColors.branco),
            )
          : Text(label),
    );
  }
}

/// Aviso em destaque dentro do formulário (erro ou sucesso).
class InlineMessage extends StatelessWidget {
  const InlineMessage(this.text, {super.key, this.error = true});

  final String text;
  final bool error;

  @override
  Widget build(BuildContext context) {
    final color = error ? KikaColors.erro : KikaColors.marrom;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: error ? const Color(0xFFFCE4E4) : KikaColors.branco,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: error ? KikaColors.erro : KikaColors.destaque),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(error ? Icons.error_outline : Icons.check_circle_outline, color: color),
            const SizedBox(width: 10),
            Expanded(child: Text(text, style: TextStyle(color: color, fontWeight: FontWeight.w600))),
          ],
        ),
      ),
    );
  }
}

/// Tela de erro com botão de tentar de novo.
class ErrorRetry extends StatelessWidget {
  const ErrorRetry({super.key, required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, size: 48, color: KikaColors.destaque),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: 16),
            OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Tentar de novo')),
          ],
        ),
      ),
    );
  }
}

/// Conteúdo centralizado com largura máxima: fica bom em celular pequeno, grande e deitado.
class FormWidth extends StatelessWidget {
  const FormWidth({super.key, required this.child, this.maxWidth = 460});

  final Widget child;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: ConstrainedBox(constraints: BoxConstraints(maxWidth: maxWidth), child: child),
    );
  }
}
