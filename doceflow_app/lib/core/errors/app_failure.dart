import 'dart:async';
import 'dart:io';

import 'package:supabase_flutter/supabase_flutter.dart';

/// Erro já traduzido para a tela. Nunca carrega token, SQL ou detalhe técnico.
class AppFailure implements Exception {
  const AppFailure(this.message, {this.kind = FailureKind.unknown});

  final String message;
  final FailureKind kind;

  @override
  String toString() => message;
}

enum FailureKind { offline, invalidCredentials, noAccess, rateLimited, expired, validation, unavailable, unknown }

const offlineMessage = 'Sem conexão com a internet. Confira o Wi-Fi ou os dados móveis e tente de novo.';

/// Converte qualquer erro do Supabase, da rede ou do app em [AppFailure].
AppFailure toFailure(Object error) {
  if (error is AppFailure) return error;
  if (error is SocketException || error is TimeoutException || error is HandshakeException) {
    return const AppFailure(offlineMessage, kind: FailureKind.offline);
  }
  if (error is AuthException) return _auth(error);
  if (error is PostgrestException) return _postgrest(error);
  final text = error.toString();
  if (text.contains('SocketException') || text.contains('Failed host lookup') || text.contains('ClientException')) {
    return const AppFailure(offlineMessage, kind: FailureKind.offline);
  }
  return const AppFailure('Algo deu errado. Tente novamente em instantes.');
}

AppFailure _auth(AuthException e) {
  final code = (e.code ?? '').toLowerCase();
  final status = e.statusCode ?? '';
  final msg = e.message.toLowerCase();
  if (code == 'invalid_credentials' || msg.contains('invalid login credentials')) {
    return const AppFailure('E-mail ou senha incorretos.', kind: FailureKind.invalidCredentials);
  }
  if (code == 'email_not_confirmed') {
    return const AppFailure('Este e-mail ainda não foi confirmado. Fale com o suporte do DoceFlow.',
        kind: FailureKind.noAccess);
  }
  if (code.contains('rate_limit') || status == '429') {
    return const AppFailure('Muitas tentativas. Aguarde alguns minutos e tente de novo.',
        kind: FailureKind.rateLimited);
  }
  if (code == 'otp_expired' || msg.contains('expired') || (msg.contains('invalid') && msg.contains('otp'))) {
    return const AppFailure('Código inválido ou vencido. Peça um novo código.', kind: FailureKind.expired);
  }
  if (code == 'weak_password') {
    return const AppFailure('Senha fraca. Use pelo menos 10 caracteres, com letras e números.',
        kind: FailureKind.validation);
  }
  if (code == 'same_password') {
    return const AppFailure('A nova senha precisa ser diferente da atual.', kind: FailureKind.validation);
  }
  if (code == 'session_not_found' || code == 'refresh_token_not_found' || status == '401') {
    return const AppFailure('Sua sessão terminou. Entre novamente.', kind: FailureKind.expired);
  }
  if (e is AuthRetryableFetchException) {
    return const AppFailure(offlineMessage, kind: FailureKind.offline);
  }
  return const AppFailure('Não foi possível concluir agora. Tente novamente.');
}

AppFailure _postgrest(PostgrestException e) {
  final code = e.code ?? '';
  if (code == '42501' || code == 'PGRST301' || e.message.contains('sem_permissao')) {
    return const AppFailure('Sem permissão. Entre novamente.', kind: FailureKind.noAccess);
  }
  if (code == 'PGRST202' || code == '42883') {
    return const AppFailure('Esta função ainda não está disponível no servidor.', kind: FailureKind.unavailable);
  }
  return const AppFailure('Não foi possível carregar os dados agora. Tente novamente.',
      kind: FailureKind.unavailable);
}
