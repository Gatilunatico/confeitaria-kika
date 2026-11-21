import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/whatsapp.dart';

/// Orçamento (tabela `leads`). Status aceitos pelo CHECK do banco (migração 002).
abstract final class QuoteStatus {
  static const novo = 'Novo';
  static const emAtendimento = 'Em atendimento';
  static const enviado = 'Orçamento enviado';
  static const vendido = 'Venda concluída';
  static const perdido = 'Perdido';
  static const all = [novo, emAtendimento, enviado, vendido, perdido];

  static IconData icon(String s) => switch (s) {
        novo => Icons.fiber_new_outlined,
        emAtendimento => Icons.support_agent,
        enviado => Icons.request_quote_outlined,
        vendido => Icons.check_circle_outline,
        perdido => Icons.cancel_outlined,
        _ => Icons.help_outline,
      };

  static Color color(String s) => switch (s) {
        novo => KikaColors.destaque,
        vendido => const Color(0xFF2E7D32),
        perdido => const Color(0xFF8D6E63),
        _ => const Color(0xFFB07A3B),
      };
}

class Quote {
  const Quote({
    required this.id,
    required this.protocol,
    required this.createdAt,
    required this.status,
    required this.customerName,
    required this.whatsapp,
    required this.productName,
    required this.quantity,
    required this.unit,
    required this.desiredDate,
    required this.fulfillment,
    required this.notes,
    required this.origin,
    this.orderId,
  });

  final String id;
  final String protocol;
  final DateTime createdAt;
  final String status;
  final String customerName;
  final String whatsapp;
  final String productName;
  final int quantity;
  final String unit;
  final DateTime desiredDate;
  final String fulfillment; // Retirada | Entrega
  final String notes;
  final String origin;
  final String? orderId; // pedido criado a partir deste orçamento (se já convertido)

  static const columns = 'id,protocolo,created_at,status,cliente_nome,cliente_whatsapp,produto_nome,quantidade,'
      'unidade,data_desejada,modalidade,observacoes,origem';

  factory Quote.fromJson(Map<String, dynamic> j, {String? orderId}) => Quote(
        id: j['id'] as String,
        protocol: j['protocolo'] as String,
        createdAt: DateTime.parse(j['created_at'] as String),
        status: j['status'] as String,
        customerName: j['cliente_nome'] as String,
        whatsapp: j['cliente_whatsapp'] as String,
        productName: j['produto_nome'] as String,
        quantity: (j['quantidade'] as num).toInt(),
        unit: j['unidade'] as String,
        desiredDate: DateTime.parse(j['data_desejada'] as String),
        fulfillment: j['modalidade'] as String,
        notes: (j['observacoes'] as String?) ?? '',
        origin: (j['origem'] as String?) ?? 'site',
        orderId: orderId,
      );

  bool get canConvert => orderId == null && status != QuoteStatus.perdido;

  String whatsappMessage(String storeName) =>
      'Olá, ${firstName(customerName)}! Aqui é da $storeName, sobre o seu orçamento $protocol '
      '($productName, $quantity $unit, para ${formatDate(desiredDate)}).';
}


/// Dados da conversão em pedido (vão para a função converter_orcamento_em_pedido).
class ConversionInput {
  const ConversionInput({this.deliveryDate, this.address = '', this.finalValue, this.internalNotes = ''});

  final DateTime? deliveryDate; // null = data desejada do orçamento
  final String address; // obrigatório se o orçamento for de Entrega (o banco confere)
  final double? finalValue;
  final String internalNotes;
}

class ConversionResult {
  const ConversionResult({required this.orderId, required this.protocol, required this.created});

  final String orderId;
  final String protocol;
  final bool created; // false = já tinha sido convertido (mesmo pedido devolvido)
}
