import 'dart:async';

import 'package:supabase_flutter/supabase_flutter.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/admin_account.dart';

const noAccessMessage = 'Esta conta não tem acesso ao painel da confeitaria.';

class SupabaseAuthRepository implements AuthRepository {
  SupabaseAuthRepository(this._client, {required this.storeSlug, LocalStorage? localStorage})
      : _localStorage = localStorage;

  final SupabaseClient _client;
  final String storeSlug;
  final LocalStorage? _localStorage;

  GoTrueClient get _auth => _client.auth;

  @override
  Stream<void> get sessionEnded =>
      _auth.onAuthStateChange.where((s) => s.event == AuthChangeEvent.signedOut).map((_) {});

  @override
  Future<AdminAccount?> restoreSession() async {
    final user = _auth.currentUser;
    if (_auth.currentSession == null || user == null) return null;
    try {
      // getUser confere o token NO SERVIDOR: sessão revogada ou conta removida não passa.
      final fresh = await _auth.getUser();
      return await _loadAccount(fresh.user ?? user);
    } catch (e) {
      final failure = toFailure(e);
      // Sem rede ou servidor fora do ar: mantém a sessão e deixa tentar de novo.
      if (failure.kind == FailureKind.offline || failure.kind == FailureKind.unavailable) throw failure;
      await signOut(); // sessão vencida/revogada ou conta sem acesso: sai do aparelho
      if (failure.kind == FailureKind.noAccess) throw failure;
      return null;
    }
  }

  @override
  Future<AdminAccount> signIn({required String email, required String password}) async {
    try {
      final res = await _auth.signInWithPassword(email: email.trim(), password: password);
      final user = res.user;
      if (user == null) throw const AppFailure('Não foi possível entrar agora. Tente novamente.');
      return await _loadAccount(user);
    } catch (e) {
      final failure = toFailure(e);
      if (failure.kind == FailureKind.noAccess) await signOut();
      throw failure;
    }
  }

  /// Só entra quem tem perfil administrativo ATIVO nesta confeitaria. O RLS garante o resto.
  Future<AdminAccount> _loadAccount(User user) async {
    final profile = await _client
        .from('admin_profiles')
        .select('confeitaria_id,papel')
        .eq('user_id', user.id)
        .eq('ativo', true)
        .maybeSingle();
    if (profile == null) throw const AppFailure(noAccessMessage, kind: FailureKind.noAccess);
    final store = await _client
        .from('confeitarias')
        .select('id,nome,slug')
        .eq('id', profile['confeitaria_id'] as String)
        .eq('ativo', true)
        .maybeSingle();
    if (store == null || store['slug'] != storeSlug) {
      throw const AppFailure(noAccessMessage, kind: FailureKind.noAccess);
    }
    return AdminAccount(
      userId: user.id,
      email: user.email ?? '',
      storeId: store['id'] as String,
      storeName: store['nome'] as String,
      storeSlug: store['slug'] as String,
      role: profile['papel'] as String? ?? 'equipe',
    );
  }

  @override
  Future<void> sendRecoveryEmail(String email) async {
    try {
      await _auth.resetPasswordForEmail(email.trim());
    } catch (e) {
      final failure = toFailure(e);
      // Rede e limite de envios aparecem para a pessoa; o resto vira a resposta genérica.
      if (failure.kind == FailureKind.offline || failure.kind == FailureKind.rateLimited) throw failure;
    }
  }

  @override
  Future<void> resetPasswordWithCode({
    required String email,
    required String code,
    required String newPassword,
  }) async {
    try {
      await _auth.verifyOTP(type: OtpType.recovery, email: email.trim(), token: code.trim());
      await _auth.updateUser(UserAttributes(password: newPassword));
    } catch (e) {
      throw toFailure(e);
    } finally {
      // Recuperar a senha nunca abre o painel direto: a pessoa entra de novo com a senha nova,
      // e o login confere o perfil de administradora.
      await signOut();
    }
  }

  @override
  Future<void> changePassword(String newPassword) async {
    try {
      await _auth.updateUser(UserAttributes(password: newPassword));
    } catch (e) {
      throw toFailure(e);
    }
  }

  @override
  Future<void> signOut() async {
    try {
      await _auth.signOut();
    } catch (_) {
      // Sem rede o servidor não é avisado, mas a sessão sai do aparelho do mesmo jeito.
      await _localStorage?.removePersistedSession();
    }
  }
}
