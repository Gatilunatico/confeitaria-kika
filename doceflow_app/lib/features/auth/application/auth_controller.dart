import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/errors/app_failure.dart';
import '../domain/admin_account.dart';

/// Implementação real criada no main.dart (Supabase); os testes trocam por uma falsa.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => throw UnimplementedError('authRepositoryProvider precisa ser configurado no main.dart'),
);

/// Relógio injetável (testes do bloqueio por tentativas).
final clockProvider = Provider<DateTime Function()>((ref) => DateTime.now);

sealed class AuthState {
  const AuthState();
}

/// Abrindo o app: conferindo a sessão salva.
class AuthChecking extends AuthState {
  const AuthChecking();
}

class AuthSignedOut extends AuthState {
  const AuthSignedOut({this.notice});
  final String? notice; // ex.: "Sua sessão terminou" ou "Senha alterada"
}

class AuthSignedIn extends AuthState {
  const AuthSignedIn(this.account);
  final AdminAccount account;
}

/// Não deu para conferir a sessão (sem internet). A sessão fica guardada para tentar de novo.
class AuthRestoreFailed extends AuthState {
  const AuthRestoreFailed(this.message);
  final String message;
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);

class AuthController extends Notifier<AuthState> {
  static const maxAttempts = 5;
  static const lockDuration = Duration(minutes: 5);

  int _failures = 0;
  DateTime? _lockedUntil;
  StreamSubscription<void>? _sessionSub;

  AuthRepository get _repo => ref.read(authRepositoryProvider);

  @override
  AuthState build() {
    _sessionSub = _repo.sessionEnded.listen((_) {
      if (state is AuthSignedIn) {
        state = const AuthSignedOut(notice: 'Sua sessão terminou. Entre novamente.');
      }
    });
    ref.onDispose(() => _sessionSub?.cancel());
    Future.microtask(restore);
    return const AuthChecking();
  }

  Future<void> restore() async {
    state = const AuthChecking();
    try {
      final account = await _repo.restoreSession();
      state = account == null ? const AuthSignedOut() : AuthSignedIn(account);
    } on AppFailure catch (f) {
      state = f.kind == FailureKind.noAccess ? AuthSignedOut(notice: f.message) : AuthRestoreFailed(f.message);
    } catch (e) {
      state = AuthRestoreFailed(toFailure(e).message);
    }
  }

  /// Minutos restantes de bloqueio depois de muitas tentativas erradas (0 = liberado).
  int get lockedMinutes {
    final until = _lockedUntil;
    if (until == null) return 0;
    final left = until.difference(ref.read(clockProvider)());
    if (left.isNegative) {
      _lockedUntil = null;
      _failures = 0;
      return 0;
    }
    return (left.inSeconds / 60).ceil();
  }

  /// Lança [AppFailure] com a mensagem para a tela. Sucesso: estado vira [AuthSignedIn].
  Future<void> signIn({required String email, required String password}) async {
    final minutes = lockedMinutes;
    if (minutes > 0) {
      throw AppFailure('Muitas tentativas. Tente novamente em $minutes min.', kind: FailureKind.rateLimited);
    }
    try {
      final account = await _repo.signIn(email: email, password: password);
      _failures = 0;
      state = AuthSignedIn(account);
    } catch (e) {
      final failure = toFailure(e);
      if (failure.kind == FailureKind.invalidCredentials && ++_failures >= maxAttempts) {
        _lockedUntil = ref.read(clockProvider)().add(lockDuration);
      }
      throw failure;
    }
  }

  Future<void> signOut({String? notice}) async {
    await _repo.signOut();
    state = AuthSignedOut(notice: notice);
  }

  /// Depois de trocar a senha pela recuperação: volta ao login com aviso.
  void passwordReset() => state = const AuthSignedOut(notice: 'Senha alterada! Entre com a nova senha.');
}
