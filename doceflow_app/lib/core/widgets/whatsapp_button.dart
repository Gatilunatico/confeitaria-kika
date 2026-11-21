import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../theme/app_theme.dart';
import '../whatsapp.dart';
import 'states.dart';

/// Abre a conversa no WhatsApp com a mensagem escrita. Não envia nada sozinho e não
/// diz que enviou: a confeiteira revisa e toca em enviar no próprio WhatsApp.
class WhatsAppButton extends ConsumerWidget {
  const WhatsAppButton({super.key, required this.phone, required this.message});

  final String phone;
  final String message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return OutlinedButton.icon(
      key: const Key('whatsapp_open'),
      icon: const Icon(Icons.chat_outlined, color: KikaColors.marrom),
      label: const Text('Abrir conversa no WhatsApp'),
      onPressed: () async {
        final Uri uri;
        try {
          uri = buildWhatsAppUri(phone, message);
        } on FormatException {
          showMessage(context, 'Número de WhatsApp inválido.');
          return;
        }
        bool opened;
        try {
          opened = await ref.read(urlOpenerProvider)(uri);
        } catch (_) {
          opened = false;
        }
        if (!opened && context.mounted) {
          showMessage(context, 'Não foi possível abrir o WhatsApp neste celular.');
        }
      },
    );
  }
}
