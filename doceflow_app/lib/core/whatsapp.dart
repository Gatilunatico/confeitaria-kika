import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

/// Abre o WhatsApp (link wa.me) com a mensagem já escrita. Quem envia é a confeiteira, no
/// próprio WhatsApp: o app nunca diz que a mensagem "foi enviada". Mesma regra do painel web
/// (doceflow/services/whatsapp_service.py).
Uri buildWhatsAppUri(String phone, String message) {
  final digits = phone.replaceAll(RegExp(r'\D'), '');
  if (digits.length < 10) throw const FormatException('Número de WhatsApp inválido.');
  return Uri.https('wa.me', '/$digits', message.isEmpty ? null : {'text': message});
}

String firstName(String name) {
  final parts = name.trim().split(RegExp(r'\s+'));
  return parts.isEmpty || parts.first.isEmpty ? 'tudo bem' : parts.first;
}

/// Trocável nos testes: devolve true se o WhatsApp (ou o navegador) abriu.
typedef UrlOpener = Future<bool> Function(Uri uri);

final urlOpenerProvider = Provider<UrlOpener>(
  (ref) => (uri) => launchUrl(uri, mode: LaunchMode.externalApplication),
);
