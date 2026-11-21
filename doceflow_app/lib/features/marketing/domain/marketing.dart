import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Pedido de arte (mesmos campos da API: POST /v1/marketing/previa e /posts).
class ArtRequest {
  const ArtRequest({
    required this.productId,
    this.imageId,
    this.template = 'produto',
    this.format = 'feed',
    this.tone = 'amigavel',
    this.title,
    this.priceText,
    this.cta,
    this.extra = '',
    this.usePhoto = true,
    this.fit = 'cover',
  });

  final String productId;
  final String? imageId; // foto real escolhida; null = a principal
  final String template; // produto | promocao | novidade
  final String format; // feed (1080×1080) | story (1080×1920)
  final String tone; // amigavel | promocional | elegante
  final String? title;
  final String? priceText;
  final String? cta;
  final String extra;
  final bool usePhoto;
  final String fit; // cover | contain

  Map<String, dynamic> toJson() => {
        'produto_id': productId,
        if (imageId != null) 'imagem_id': imageId,
        'template': template,
        'formato': format,
        'tom': tone,
        if (title != null) 'titulo': title,
        if (priceText != null) 'preco_texto': priceText,
        if (cta != null) 'cta': cta,
        'extra': extra,
        'usar_foto': usePhoto,
        'ajuste_foto': fit,
      };
}

class ArtPreview {
  const ArtPreview({
    required this.png,
    required this.width,
    required this.height,
    required this.title,
    required this.priceText,
    required this.cta,
    required this.captionBody,
    required this.hashtags,
    required this.warnings,
  });

  final Uint8List png;
  final int width;
  final int height;
  final String title;
  final String priceText;
  final String cta;
  final String captionBody; // legenda sem as hashtags
  final List<String> hashtags;
  final List<String> warnings;
}

/// Junta o texto e as hashtags na legenda final (limite do Instagram e do banco: 2200).
String composeCaption(String body, List<String> hashtags) {
  final tags = hashtags.where((t) => t.trim().isNotEmpty).join(' ');
  final text = body.trim();
  if (tags.isEmpty) return text;
  return text.isEmpty ? tags : '$text\n\n$tags';
}

/// Normaliza uma hashtag digitada: "#Bolo de Pote" → "#bolodepote". null se ficar vazia.
String? normalizeHashtag(String raw) {
  final t = raw.trim().replaceAll(RegExp(r'^#+'), '').replaceAll(RegExp(r'[\s#]+'), '');
  if (t.isEmpty || t.length > 50) return null;
  return '#$t';
}

const maxCaption = 2200;
const maxHashtags = 30; // limite do Instagram

class MarketingPost {
  const MarketingPost({
    required this.id,
    required this.productId,
    required this.productName,
    required this.template,
    required this.format,
    required this.title,
    required this.priceText,
    required this.cta,
    required this.tone,
    required this.caption,
    required this.status,
    required this.createdAt,
  });

  final String id;
  final String? productId;
  final String productName;
  final String template;
  final String format;
  final String title;
  final String priceText;
  final String cta;
  final String tone;
  final String caption;
  final String status; // Rascunho | Pronto | Publicado manualmente
  final DateTime createdAt;

  factory MarketingPost.fromJson(Map<String, dynamic> j) => MarketingPost(
        id: j['id'] as String,
        productId: j['produto_id'] as String?,
        productName: (j['produto_nome'] as String?) ?? '',
        template: j['template'] as String,
        format: j['formato'] as String,
        title: (j['titulo'] as String?) ?? '',
        priceText: (j['preco_texto'] as String?) ?? '',
        cta: (j['cta'] as String?) ?? '',
        tone: (j['tom'] as String?) ?? 'amigavel',
        caption: (j['legenda'] as String?) ?? '',
        status: (j['status'] as String?) ?? 'Rascunho',
        createdAt: DateTime.tryParse('${j['created_at']}') ?? DateTime.now(),
      );

  String get formatLabel => format == 'story' ? 'Story 1080×1920' : 'Feed 1080×1080';
}

const postStatuses = ['Rascunho', 'Pronto', 'Publicado manualmente'];

// ============================================================== Instagram
class InstagramAccount {
  const InstagramAccount({required this.status, this.username, this.accountType, this.expiresAt, this.lastError});

  final String status; // desconectado | conectado | erro
  final String? username;
  final String? accountType;
  final DateTime? expiresAt;
  final String? lastError;

  bool get connected => status == 'conectado';

  static const none = InstagramAccount(status: 'desconectado');

  factory InstagramAccount.fromJson(Map<String, dynamic> j) => InstagramAccount(
        status: (j['status'] as String?) ?? 'desconectado',
        username: j['username'] as String?,
        accountType: j['account_type'] as String?,
        expiresAt: DateTime.tryParse('${j['token_expira_em']}'),
        lastError: j['ultimo_erro'] as String?,
      );
}

abstract final class PublicationStatus {
  static const agendado = 'agendado';
  static const publicando = 'publicando';
  static const publicado = 'publicado';
  static const falhou = 'falhou';
  static const cancelado = 'cancelado';
  static const verificar = 'verificar';

  static String label(String s) => switch (s) {
        agendado => 'Agendado',
        publicando => 'Publicando',
        publicado => 'Publicado',
        falhou => 'Falhou',
        cancelado => 'Cancelado',
        verificar => 'Conferir no Instagram',
        _ => s,
      };

  static IconData icon(String s) => switch (s) {
        agendado => Icons.schedule,
        publicando => Icons.cloud_upload_outlined,
        publicado => Icons.check_circle_outline,
        falhou => Icons.error_outline,
        cancelado => Icons.cancel_outlined,
        verificar => Icons.help_outline,
        _ => Icons.help_outline,
      };

  static Color color(String s) => switch (s) {
        publicado => const Color(0xFF2E7D32),
        falhou => KikaColors.erro,
        cancelado => const Color(0xFF8D6E63),
        verificar => const Color(0xFFB07A3B),
        _ => KikaColors.destaque,
      };
}

class Publication {
  const Publication({
    required this.id,
    required this.postId,
    required this.format,
    required this.caption,
    required this.status,
    required this.scheduledFor,
    required this.attempts,
    required this.maxAttempts,
    required this.createdAt,
    this.errorMessage,
    this.permalink,
    this.publishedAt,
    this.mediaId,
  });

  final String id;
  final String postId;
  final String format;
  final String caption;
  final String status;
  final DateTime scheduledFor;
  final int attempts;
  final int maxAttempts;
  final DateTime createdAt;
  final String? errorMessage;
  final String? permalink;
  final DateTime? publishedAt;
  final String? mediaId;

  static const columns = 'id,marketing_post_id,formato,legenda,status,agendado_para,tentativas,max_tentativas,'
      'erro_mensagem,permalink,publicado_em,ig_media_id,created_at';

  factory Publication.fromJson(Map<String, dynamic> j) => Publication(
        id: j['id'] as String,
        postId: j['marketing_post_id'] as String,
        format: j['formato'] as String,
        caption: (j['legenda'] as String?) ?? '',
        status: j['status'] as String,
        scheduledFor: DateTime.parse(j['agendado_para'] as String),
        attempts: (j['tentativas'] as num?)?.toInt() ?? 0,
        maxAttempts: (j['max_tentativas'] as num?)?.toInt() ?? 3,
        createdAt: DateTime.parse(j['created_at'] as String),
        errorMessage: j['erro_mensagem'] as String?,
        permalink: j['permalink'] as String?,
        publishedAt: DateTime.tryParse('${j['publicado_em']}'),
        mediaId: j['ig_media_id'] as String?,
      );

  bool get canCancel => status == PublicationStatus.agendado;
  bool get canRetry => status == PublicationStatus.falhou;

  /// "Publicado" só existe com o id da mídia devolvido pela Meta (o banco garante; aqui também).
  bool get confirmedByMeta => status == PublicationStatus.publicado && (mediaId ?? '').isNotEmpty;
}

class PublicationLog {
  const PublicationLog({required this.event, required this.detail, required this.at});

  final String event;
  final String? detail;
  final DateTime at;

  factory PublicationLog.fromJson(Map<String, dynamic> j) => PublicationLog(
        event: j['evento'] as String,
        detail: j['detalhe'] as String?,
        at: DateTime.parse(j['created_at'] as String),
      );

  String get label => switch (event) {
        'agendado' => 'Agendado',
        'container_criado' => 'Imagem enviada à Meta',
        'container_descartado' => 'Imagem recusada pela Meta; enviando de novo',
        'publicacao_pedida' => 'Publicação pedida à Meta',
        'publicado' => 'Publicado (confirmado pela Meta)',
        'nova_tentativa_agendada' => 'Nova tentativa automática agendada',
        'nova_tentativa' => 'Nova tentativa pedida pela confeitaria',
        'falhou' => 'Falhou',
        'cancelado' => 'Cancelado',
        'verificar' => 'Conferir no Instagram',
        _ => event,
      };
}
