import 'dart:async';

import 'package:doceflow_app/app.dart';
import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/auth/application/auth_controller.dart';
import 'package:doceflow_app/features/auth/domain/admin_account.dart';
import 'package:doceflow_app/features/dashboard/data/dashboard_repository.dart';
import 'package:doceflow_app/features/dashboard/domain/dashboard_indicators.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Conta usada SÓ nos testes (nunca entra no app de produção).
const testAccount = AdminAccount(
  userId: '00000000-0000-0000-0000-00000000000a',
  email: 'dona@teste.dev',
  storeId: '00000000-0000-0000-0000-0000000000c1',
  storeName: 'Kika Cakes',
  storeSlug: 'kika-cakes',
  role: 'proprietaria',
);

class FakeAuthRepository implements AuthRepository {
  FakeAuthRepository({this.saved, this.restoreError});

  AdminAccount? saved; // sessão "guardada no aparelho"
  Object? restoreError;
  String password = 'senha-certa-123';
  bool noAccess = false;
  int signInCalls = 0;
  int signOutCalls = 0;
  final List<String> recoveryEmails = [];
  final List<(String, String, String)> resets = [];
  final _ended = StreamController<void>.broadcast();

  void endSession() => _ended.add(null);

  @override
  Stream<void> get sessionEnded => _ended.stream;

  @override
  Future<AdminAccount?> restoreSession() async {
    if (restoreError != null) throw restoreError!;
    return saved;
  }

  @override
  Future<AdminAccount> signIn({required String email, required String password}) async {
    signInCalls++;
    if (password != this.password) {
      throw const AppFailure('E-mail ou senha incorretos.', kind: FailureKind.invalidCredentials);
    }
    if (noAccess) {
      throw const AppFailure('Esta conta não tem acesso ao painel da confeitaria.', kind: FailureKind.noAccess);
    }
    saved = testAccount;
    return testAccount;
  }

  @override
  Future<void> sendRecoveryEmail(String email) async => recoveryEmails.add(email);

  @override
  Future<void> resetPasswordWithCode({required String email, required String code, required String newPassword}) async {
    if (code != '123456') throw const AppFailure('Código inválido ou vencido. Peça um novo código.');
    resets.add((email, code, newPassword));
  }

  @override
  Future<void> changePassword(String newPassword) async => password = newPassword;

  @override
  Future<void> signOut() async {
    signOutCalls++;
    saved = null;
  }
}

class FakeDashboardRepository implements DashboardRepository {
  FakeDashboardRepository({this.error});

  Object? error;
  final List<DashboardPeriod> calls = [];

  @override
  Future<DashboardIndicators> load(DashboardPeriod period) async {
    calls.add(period);
    if (error != null) throw error!;
    return const DashboardIndicators(
      quotesTotal: 8,
      quotesNew: 3,
      quotesSold: 2,
      conversionRate: 0.25,
      ordersTotal: 5,
      ordersWaiting: 1,
      ordersInProgress: 2,
      registeredValue: 1234.5,
      deliveriesNext7Days: 4,
    );
  }
}

Future<void> pumpApp(
  WidgetTester tester, {
  required FakeAuthRepository auth,
  FakeDashboardRepository? dashboard,
  Size size = const Size(390, 844), // celular comum
}) async {
  tester.view.physicalSize = size * tester.view.devicePixelRatio;
  addTearDown(tester.view.resetPhysicalSize);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(auth),
        dashboardRepositoryProvider.overrideWithValue(dashboard ?? FakeDashboardRepository()),
      ],
      child: const DoceFlowApp(),
    ),
  );
  await tester.pumpAndSettle();
}

Finder field(String key) => find.byKey(Key(key));
