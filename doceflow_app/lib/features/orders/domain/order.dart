import 'package:flutter/material.dart';

import '../../../core/format.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/whatsapp.dart';

/// Status aceitos pelo CHECK de `orders` (migração 010).
abstract final class OrderStatus {
  static const aguardando = 'Aguardando confirmação';
  static const confirmado = 'Confirmado';
  static const emProducao = 'Em produção';
  static const pronto = 'Pronto';
  static const entregue = 'Entregue';
  static const cancelado = 'Cancelado';
  static const all = [aguardando, confirmado, emProducao, pronto, entregue, cancelado];

  static IconData icon(String s) => switch (s) {
        aguardando => Icons.hourglass_top_outlined,
        confirmado => Icons.thumb_up_alt_outlined,
        emProducao => Icons.cake_outlined,
        pronto => Icons.inventory_2_outlined,
        entregue => Icons.check_circle_outline,
        cancelado => Icons.cancel_outlined,
        _ => Icons.help_outline,
      };

  static Color color(String s) => switch (s) {
        aguardando => KikaColors.destaque,
        entregue => const Color(0xFF2E7D32),
        cancelado => const Color(0xFF8D6E63),
        _ => const Color(0xFFB07A3B),
      };

  /// Frase para o WhatsApp da cliente, conforme o status atual.
  static String customerLine(String s) => switch (s) {
        aguardando => 'Recebemos o seu pedido e já vamos confirmar a disponibilidade e o valor.',
        confirmado => 'Seu pedido está confirmado!',
        emProducao => 'Seu pedido já está em produção.',
        pronto => 'Seu pedido está pronto!',
        entregue => 'Obrigada pela preferência! Esperamos que tenha gostado.',
        cancelado => 'Sobre o cancelamento do seu pedido:',
        _ => '',
      };
}

class OrderItem {
  const OrderItem({required this.name, required this.unit, required this.quantity, required this.unitPrice, required this.subtotal, required this.priceType});

  final String name;
  final String unit;
  final int quantity;
  final double? unitPrice; // registrado no momento do pedido ("a partir de")
  final double? subtotal; // calculado pelo banco
  final String priceType;

  factory OrderItem.fromJson(Map<String, dynamic> j) => OrderItem(
        name: j['produto_nome'] as String,
        unit: j['unidade'] as String,
        quantity: (j['quantidade'] as num).toInt(),
        unitPrice: (j['preco_unitario'] as num?)?.toDouble(),
        subtotal: (j['subtotal'] as num?)?.toDouble(),
        priceType: j['tipo_preco'] as String,
      );
}

class HistoryEntry {
  const HistoryEntry({required this.field, required this.before, required this.after, required this.byAdmin, required this.at});

  final String field;
  final String? before;
  final String? after;
  final bool byAdmin; // false = criado pela cliente no site
  final DateTime at;

  factory HistoryEntry.fromJson(Map<String, dynamic> j) => HistoryEntry(
        field: j['campo'] as String,
        before: j['valor_anterior'] as String?,
        after: j['valor_novo'] as String?,
        byAdmin: j['alterado_por'] != null,
        at: DateTime.parse(j['alterado_em'] as String),
      );

  String get text {
    String money(String? v) => v == null ? 'vazio' : formatMoney(double.tryParse(v));
    String date(String? v) => v == null ? 'vazia' : formatDate(DateTime.tryParse(v));
    return switch (field) {
      'criado' => byAdmin ? 'Pedido criado pela confeitaria ($after)' : 'Pedido feito pela cliente no site ($after)',
      'status' => 'Status: ${before ?? '—'} → ${after ?? '—'}',
      'valor_final' => 'Valor final: ${money(before)} → ${money(after)}',
      'data_entrega' => 'Data de entrega: ${date(before)} → ${date(after)}',
      'observacoes_internas' => 'Observações internas alteradas',
      _ => field,
    };
  }
}

class Order {
  const Order({
    required this.id,
    required this.protocol,
    required this.createdAt,
    required this.status,
    required this.customerName,
    required this.whatsapp,
    required this.deliveryDate,
    required this.fulfillment,
    required this.address,
    required this.notes,
    required this.internalNotes,
    required this.estimatedValue,
    required this.finalValue,
    required this.origin,
    required this.leadId,
    this.items = const [],
  });

  final String id;
  final String protocol;
  final DateTime createdAt;
  final String status;
  final String customerName;
  final String whatsapp;
  final DateTime deliveryDate;
  final String fulfillment;
  final String address;
  final String notes; // da cliente
  final String internalNotes; // só da confeitaria
  final double? estimatedValue; // calculado pelo banco ("a partir de")
  final double? finalValue; // combinado pela dona
  final String origin;
  final String? leadId;
  final List<OrderItem> items;

  static const columns = 'id,protocolo,created_at,status,cliente_nome,cliente_whatsapp,data_entrega,modalidade,'
      'endereco_entrega,observacoes,observacoes_internas,valor_estimado,valor_final,origem,lead_id';
  static const itemColumns = 'produto_nome,unidade,quantidade,preco_unitario,subtotal,tipo_preco';

  factory Order.fromJson(Map<String, dynamic> j) => Order(
        id: j['id'] as String,
        protocol: j['protocolo'] as String,
        createdAt: DateTime.parse(j['created_at'] as String),
        status: j['status'] as String,
        customerName: j['cliente_nome'] as String,
        whatsapp: j['cliente_whatsapp'] as String,
        deliveryDate: DateTime.parse(j['data_entrega'] as String),
        fulfillment: j['modalidade'] as String,
        address: (j['endereco_entrega'] as String?) ?? '',
        notes: (j['observacoes'] as String?) ?? '',
        internalNotes: (j['observacoes_internas'] as String?) ?? '',
        estimatedValue: (j['valor_estimado'] as num?)?.toDouble(),
        finalValue: (j['valor_final'] as num?)?.toDouble(),
        origin: (j['origem'] as String?) ?? 'site',
        leadId: j['lead_id'] as String?,
        items: [for (final i in (j['order_items'] as List? ?? const [])) OrderItem.fromJson((i as Map).cast())],
      );

  String whatsappMessage(String storeName) {
    final line = OrderStatus.customerLine(status);
    return 'Olá, ${firstName(customerName)}! Aqui é da $storeName, sobre o seu pedido $protocol. $line'.trim();
  }
}


/// Só os 4 campos que o banco deixa a dona alterar (permissão por coluna, migração 007).
class OrderUpdate {
  const OrderUpdate({this.status, this.finalValue, this.clearFinalValue = false, this.deliveryDate, this.internalNotes});

  final String? status;
  final double? finalValue;
  final bool clearFinalValue;
  final DateTime? deliveryDate;
  final String? internalNotes;

  Map<String, dynamic> toColumns() => {
        if (status != null) 'status': status,
        if (finalValue != null || clearFinalValue) 'valor_final': clearFinalValue ? null : finalValue,
        if (deliveryDate != null) 'data_entrega': isoDate(deliveryDate!),
        if (internalNotes != null) 'observacoes_internas': internalNotes!.trim(),
      };

  bool get isEmpty => toColumns().isEmpty;
}
