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
  if (error is StorageException) {
    final status = '${error.statusCode}';
    if (status == '403' || status == '401') {
      return const AppFailure('Sem permissão para enviar a foto. Entre novamente.', kind: FailureKind.noAccess);
    }
    if (status == '413') {
      return const AppFailure('Foto grande demais (máximo 5 MB).', kind: FailureKind.validation);
    }
    return const AppFailure('Não foi possível enviar a foto agora. Tente novamente.', kind: FailureKind.unavailable);
  }
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

/// Motivos devolvidos pelas funções e gatilhos do banco → mensagem para a tela.
/// A regra fica no banco; o app só traduz o motivo.
const businessMessages = {
  'orcamento_nao_encontrado': 'Orçamento não encontrado nesta confeitaria.',
  'orcamento_perdido': 'Este orçamento está como "Perdido". Mude o status antes de converter.',
  'data_invalida': 'Data inválida: escolha hoje ou uma data futura (até 1 ano).',
  'endereco_obrigatorio': 'Informe o endereço de entrega (pelo menos 10 caracteres).',
  'endereco_invalido': 'Endereço muito longo (máximo 300 caracteres).',
  'valor_invalido': 'Valor inválido.',
  'observacoes_invalidas': 'Observações internas: no máximo 1000 caracteres.',
  'limite_fotos': 'Cada produto pode ter no máximo 10 fotos.',
  'periodo_invalido': 'Período inválido.',
  'instagram_desconectado': 'Conecte o Instagram antes de agendar.',
  'publicacao_ja_agendada': 'Este post já está agendado no Instagram.',
  'post_sem_imagem': 'Este post não tem arte salva. Gere a arte de novo.',
  'post_nao_encontrado': 'Post não encontrado nesta confeitaria.',
  'publicacao_nao_encontrada': 'Publicação não encontrada.',
  'publicacao_em_andamento': 'A publicação já está sendo enviada ao Instagram e não pode ser cancelada.',
  'publicacao_nao_cancelavel': 'Só dá para cancelar o que ainda está agendado.',
  'publicacao_nao_falhou': 'Só dá para tentar de novo o que falhou.',
  'chave_invalida': 'Pedido inválido. Tente novamente.',
};

AppFailure _postgrest(PostgrestException e) {
  final code = e.code ?? '';
  for (final entry in businessMessages.entries) {
    if (e.message.contains(entry.key)) return AppFailure(entry.value, kind: FailureKind.validation);
  }
  if (code == '42501' || code == 'PGRST301' || e.message.contains('sem_permissao')) {
    return const AppFailure('Sem permissão. Entre novamente.', kind: FailureKind.noAccess);
  }
  if (code == '23503') {
    return const AppFailure(
        'Este produto tem orçamentos ou pedidos registrados e não pode ser excluído. '
        'Despublique-o para tirá-lo da vitrine.',
        kind: FailureKind.validation);
  }
  if (code == '23505') {
    return const AppFailure('Este registro já existe.', kind: FailureKind.validation);
  }
  if (code == '23514' || code == '22023' || code == '22P02' || code == '23502') {
    return const AppFailure('O servidor recusou os dados. Confira os campos.', kind: FailureKind.validation);
  }
  if (code == 'PGRST202' || code == '42883') {
    return const AppFailure('Esta função ainda não está disponível no servidor.', kind: FailureKind.unavailable);
  }
  return const AppFailure('Não foi possível carregar os dados agora. Tente novamente.',
      kind: FailureKind.unavailable);
}
