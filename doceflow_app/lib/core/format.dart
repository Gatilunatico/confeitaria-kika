import 'package:intl/intl.dart';

final _money = NumberFormat.currency(locale: 'pt_BR', symbol: r'R$');
final _date = DateFormat('dd/MM/yyyy', 'pt_BR');
final _dateTime = DateFormat("dd/MM/yyyy 'às' HH:mm", 'pt_BR');

String formatMoney(num? value, {String empty = '—'}) => value == null ? empty : _money.format(value);

/// Data "pura" do banco (`date`), sem fuso: 2026-11-30 → 30/11/2026.
String formatDate(DateTime? value) => value == null ? '—' : _date.format(value);

/// Momento do banco (`timestamptz`, UTC) mostrado no horário de Brasília (UTC-3).
String formatDateTimeBrt(DateTime? utc) =>
    utc == null ? '—' : _dateTime.format(utc.toUtc().subtract(const Duration(hours: 3)));

DateTime? parseDate(Object? v) => v == null ? null : DateTime.tryParse('$v');

/// `date` do Postgres: '2026-11-30'.
String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// WhatsApp do banco (55 + DDD + número) → (11) 98765-4321.
String formatPhone(String digits) {
  final d = digits.replaceAll(RegExp(r'\D'), '');
  final local = d.startsWith('55') && d.length >= 12 ? d.substring(2) : d;
  if (local.length == 11) return '(${local.substring(0, 2)}) ${local.substring(2, 7)}-${local.substring(7)}';
  if (local.length == 10) return '(${local.substring(0, 2)}) ${local.substring(2, 6)}-${local.substring(6)}';
  return digits;
}

/// "12,50" ou "12.50" → 12.5 (null se vazio ou inválido).
double? parseMoney(String text) {
  final t = text.trim().replaceAll(RegExp(r'[R$\s]'), '');
  if (t.isEmpty) return null;
  final normalized = t.contains(',') ? t.replaceAll('.', '').replaceAll(',', '.') : t;
  return double.tryParse(normalized);
}

String moneyInput(num? v) => v == null ? '' : v.toStringAsFixed(2).replaceAll('.', ',');
