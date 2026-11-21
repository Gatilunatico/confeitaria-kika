/// Validações dos formulários de entrada e de senha (o servidor valida de novo).
abstract final class Validators {
  /// Igual ao painel web (services/auth_service.py: MIN_PASSWORD).
  static const minPassword = 10;
  static final _email = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$');

  static String? email(String? value) {
    final v = (value ?? '').trim();
    if (v.isEmpty) return 'Informe o e-mail.';
    if (v.length > 254 || !_email.hasMatch(v)) return 'E-mail inválido.';
    return null;
  }

  /// No login, só exige que a senha exista: a regra de força vale ao criar senha nova.
  static String? loginPassword(String? value) => (value ?? '').isEmpty ? 'Informe a senha.' : null;

  static String? newPassword(String? value) {
    final v = value ?? '';
    if (v.length < minPassword) return 'Use pelo menos $minPassword caracteres.';
    if (v.length > 72) return 'Use no máximo 72 caracteres.';
    if (!RegExp(r'[A-Za-z]').hasMatch(v) || !RegExp(r'[0-9]').hasMatch(v)) {
      return 'Use letras e números.';
    }
    return null;
  }

  static String? confirmPassword(String? value, String original) =>
      (value ?? '') == original ? null : 'As senhas não são iguais.';

  static String? recoveryCode(String? value) {
    final v = (value ?? '').trim();
    if (!RegExp(r'^[0-9]{6}$').hasMatch(v)) return 'O código tem 6 números.';
    return null;
  }
}
