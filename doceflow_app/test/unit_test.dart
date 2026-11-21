import 'dart:io';

import 'package:doceflow_app/core/config/app_config.dart';
import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/core/storage/secure_session_storage.dart';
import 'package:doceflow_app/features/auth/domain/validators.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Validators', () {
    test('e-mail', () {
      expect(Validators.email(''), isNotNull);
      expect(Validators.email('a@b'), isNotNull);
      expect(Validators.email(' dona@kika.com.br '), isNull);
    });
    test('nova senha: 10+ caracteres, letras e números', () {
      expect(Validators.newPassword('abc123'), isNotNull);
      expect(Validators.newPassword('somenteletras'), isNotNull);
      expect(Validators.newPassword('1234567890'), isNotNull);
      expect(Validators.newPassword('Kika2026doce'), isNull);
    });
    test('confirmação e código', () {
      expect(Validators.confirmPassword('a', 'b'), isNotNull);
      expect(Validators.confirmPassword('a', 'a'), isNull);
      expect(Validators.recoveryCode('12345'), isNotNull);
      expect(Validators.recoveryCode('12a456'), isNotNull);
      expect(Validators.recoveryCode('123456'), isNull);
    });
  });

  group('AppConfig', () {
    const publishable = 'sb_publishable_abcdefghijklmnop';
    test('exige URL https e chave', () {
      expect(() => AppConfig.validate(supabaseUrl: '', supabaseKey: '', storeSlug: 'x'), throwsA(isA<AppConfigError>()));
      expect(() => AppConfig.validate(supabaseUrl: 'http://x.supabase.co', supabaseKey: publishable, storeSlug: 'x'),
          throwsA(isA<AppConfigError>()));
      expect(AppConfig.validate(supabaseUrl: 'https://x.supabase.co', supabaseKey: publishable, storeSlug: 'kika-cakes')
          .storeSlug, 'kika-cakes');
    });
    test('recusa chave privilegiada (sb_secret ou JWT service_role)', () {
      expect(() => AppConfig.validate(supabaseUrl: 'https://x.supabase.co', supabaseKey: 'sb_secret_xyz', storeSlug: 'x'),
          throwsA(isA<AppConfigError>()));
      // payload {"role":"service_role"} em base64url
      const jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.assinatura';
      expect(() => AppConfig.validate(supabaseUrl: 'https://x.supabase.co', supabaseKey: jwt, storeSlug: 'x'),
          throwsA(isA<AppConfigError>()));
    });
  });

  group('toFailure', () {
    test('sem rede', () => expect(toFailure(const SocketException('x')).kind, FailureKind.offline));
    test('senha errada', () {
      final f = toFailure(const AuthException('Invalid login credentials', statusCode: '400', code: 'invalid_credentials'));
      expect(f.message, 'E-mail ou senha incorretos.');
    });
    test('sem permissão no banco', () {
      expect(toFailure(const PostgrestException(message: 'denied', code: '42501')).kind, FailureKind.noAccess);
    });
    test('erro desconhecido não vaza detalhes', () {
      final f = toFailure(Exception('postgres://usuario:senha@host'));
      expect(f.message.contains('senha@'), isFalse);
    });
  });

  group('SecureSessionStorage', () {
    test('guarda, lê e apaga a sessão no armazenamento seguro', () async {
      FlutterSecureStorage.setMockInitialValues({});
      final s = SecureSessionStorage();
      expect(await s.hasAccessToken(), isFalse);
      await s.persistSession('{"access_token":"x"}');
      expect(await s.hasAccessToken(), isTrue);
      expect(await s.accessToken(), '{"access_token":"x"}');
      await s.removePersistedSession();
      expect(await s.hasAccessToken(), isFalse);
    });
  });

  group('DashboardIndicators', () {
    test('lê a resposta da função painel_indicadores', () {
      final d = DashboardIndicators.fromRpc({
        'orcamentos': {'total': 4, 'novos': 1, 'vendas_concluidas': 1, 'taxa_conversao': 0.25},
        'pedidos': {
          'total': 6, 'aguardando_confirmacao': 2, 'confirmados': 1, 'em_producao': 1, 'prontos': 1,
          'valor_registrado': 580.5,
        },
        'entregas_proximos_7_dias': 3,
      });
      expect(d.ordersInProgress, 3);
      expect(d.registeredValue, 580.5);
      expect(d.conversionRate, 0.25);
      expect(d.deliveriesNext7Days, 3);
    });

    test('cálculo pelas linhas segue as mesmas regras', () {
      final today = DateTime(2026, 11, 21);
      final d = DashboardIndicators.fromRows(
        leads: [
          {'status': 'Novo'},
          {'status': 'Venda concluída'},
        ],
        orders: [
          {'status': 'Aguardando confirmação', 'valor_estimado': 100, 'data_entrega': '2026-11-23'},
          {'status': 'Cancelado', 'valor_estimado': 999, 'data_entrega': '2026-11-22'},
          {'status': 'Pronto', 'valor_estimado': null, 'data_entrega': '2026-12-30'},
          {'status': 'Entregue', 'valor_estimado': 50, 'data_entrega': '2026-11-21'},
        ],
        today: today,
      );
      expect(d.conversionRate, 0.5);
      expect(d.registeredValue, 150); // cancelado fora; sem estimativa conta 0
      expect(d.deliveriesNext7Days, 1); // entregue e cancelado não contam; 30/12 fora da janela
      expect(d.ordersInProgress, 1);
    });

    test('sem orçamentos a taxa fica vazia', () {
      final d = DashboardIndicators.fromRows(leads: const [], orders: const [], today: DateTime(2026, 1, 1));
      expect(d.conversionRate, isNull);
    });

    test('períodos em datas de Brasília', () {
      expect(todayInBrasilia(DateTime.utc(2026, 11, 22, 2, 0)), DateTime(2026, 11, 21)); // 23h em Brasília
      final (start, end) = DashboardPeriod.last7.range(DateTime(2026, 11, 21));
      expect(start, DateTime(2026, 11, 15));
      expect(end, DateTime(2026, 11, 21));
      expect(DashboardPeriod.all.range(DateTime(2026, 11, 21)), (null, null));
    });
  });
}
