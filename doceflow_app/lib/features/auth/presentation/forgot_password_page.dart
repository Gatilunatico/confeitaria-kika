import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/router/app_router.dart';
import '../../../core/widgets/common.dart';
import '../application/auth_controller.dart';
import '../domain/validators.dart';

const recoverySentMessage = 'Se este e-mail tiver acesso ao painel, enviamos um código de 6 números. '
    'Ele vale por 1 hora. Confira também a caixa de spam.';

/// Recuperação em dois passos, no próprio app:
/// 1. informar o e-mail (resposta sempre igual, para não revelar quais e-mails têm acesso);
/// 2. digitar o código do e-mail e a nova senha. Depois, entrar de novo com a senha nova.
class ForgotPasswordPage extends ConsumerStatefulWidget {
  const ForgotPasswordPage({super.key});

  static const resendCooldown = Duration(seconds: 60);

  @override
  ConsumerState<ForgotPasswordPage> createState() => _ForgotPasswordPageState();
}

class _ForgotPasswordPageState extends ConsumerState<ForgotPasswordPage> {
  final _emailForm = GlobalKey<FormState>();
  final _resetForm = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _code = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _codeStep = false;
  bool _loading = false;
  String? _error;
  int _cooldown = 0;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    for (final c in [_email, _code, _password, _confirm]) {
      c.dispose();
    }
    super.dispose();
  }

  void _startCooldown() {
    _timer?.cancel();
    setState(() => _cooldown = ForgotPasswordPage.resendCooldown.inSeconds);
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => _cooldown = _cooldown > 0 ? _cooldown - 1 : 0);
      if (_cooldown == 0) t.cancel();
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await action();
    } on AppFailure catch (f) {
      if (mounted) setState(() => _error = f.message);
    } catch (e) {
      if (mounted) setState(() => _error = toFailure(e).message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sendEmail() async {
    final form = _emailForm.currentState; // null no passo do código (botão "Reenviar")
    if ((form != null && !form.validate()) || _cooldown > 0) return;
    await _run(() async {
      await ref.read(authRepositoryProvider).sendRecoveryEmail(_email.text);
      if (!mounted) return;
      _startCooldown();
      setState(() => _codeStep = true);
    });
  }

  Future<void> _reset() async {
    if (!_resetForm.currentState!.validate()) return;
    await _run(() async {
      await ref.read(authRepositoryProvider).resetPasswordWithCode(
            email: _email.text,
            code: _code.text,
            newPassword: _password.text,
          );
      if (!mounted) return;
      // Navega ANTES de mudar o estado: o aviso aparece no login, e esta tela não é recriada.
      final auth = ref.read(authControllerProvider.notifier);
      context.go(Routes.login);
      auth.passwordReset();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Nova senha')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
          child: FormWidth(child: _codeStep ? _codeView(context) : _emailView(context)),
        ),
      ),
    );
  }

  Widget _emailView(BuildContext context) {
    return Form(
      key: _emailForm,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Informe o e-mail da conta. Vamos enviar um código para criar uma nova senha.',
              style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: 20),
          if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 16)],
          TextFormField(
            key: const Key('forgot_email'),
            controller: _email,
            enabled: !_loading,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            autocorrect: false,
            inputFormatters: [FilteringTextInputFormatter.deny(RegExp(r'\s'))],
            decoration: const InputDecoration(labelText: 'E-mail', prefixIcon: Icon(Icons.mail_outline)),
            validator: Validators.email,
            onFieldSubmitted: (_) => _sendEmail(),
          ),
          const SizedBox(height: 20),
          LoadingButton(key: const Key('forgot_send'), label: 'Enviar código', loading: _loading, onPressed: _sendEmail),
        ],
      ),
    );
  }

  Widget _codeView(BuildContext context) {
    return Form(
      key: _resetForm,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const InlineMessage(recoverySentMessage, error: false),
          const SizedBox(height: 16),
          if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 16)],
          TextFormField(
            key: const Key('forgot_code'),
            controller: _code,
            enabled: !_loading,
            keyboardType: TextInputType.number,
            autofillHints: const [AutofillHints.oneTimeCode],
            maxLength: 6,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            decoration: const InputDecoration(labelText: 'Código de 6 números', prefixIcon: Icon(Icons.pin_outlined)),
            validator: Validators.recoveryCode,
          ),
          const SizedBox(height: 6),
          TextFormField(
            key: const Key('forgot_password'),
            controller: _password,
            enabled: !_loading,
            obscureText: true,
            autofillHints: const [AutofillHints.newPassword],
            decoration: const InputDecoration(
              labelText: 'Nova senha',
              helperText: 'Pelo menos ${Validators.minPassword} caracteres, com letras e números.',
              prefixIcon: Icon(Icons.lock_outline),
            ),
            validator: Validators.newPassword,
          ),
          const SizedBox(height: 14),
          TextFormField(
            key: const Key('forgot_confirm'),
            controller: _confirm,
            enabled: !_loading,
            obscureText: true,
            decoration: const InputDecoration(labelText: 'Repita a nova senha', prefixIcon: Icon(Icons.lock_outline)),
            validator: (v) => Validators.confirmPassword(v, _password.text),
          ),
          const SizedBox(height: 22),
          LoadingButton(key: const Key('forgot_reset'), label: 'Salvar nova senha', loading: _loading, onPressed: _reset),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _loading || _cooldown > 0 ? null : _sendEmail,
            child: Text(_cooldown > 0 ? 'Reenviar código em ${_cooldown}s' : 'Reenviar código'),
          ),
          TextButton(
            onPressed: _loading ? null : () => setState(() => _codeStep = false),
            child: const Text('Usar outro e-mail'),
          ),
        ],
      ),
    );
  }
}
