import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/errors/app_failure.dart';
import '../../../core/router/app_router.dart';
import '../../../core/widgets/common.dart';
import '../application/auth_controller.dart';
import '../domain/validators.dart';

/// Entrada da dona. Não há cadastro: contas são criadas pela equipe no Supabase
/// (procedimento em database/schema_reference.md, seção 6).
class LoginPage extends ConsumerStatefulWidget {
  const LoginPage({super.key});

  @override
  ConsumerState<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends ConsumerState<LoginPage> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_form.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider.notifier).signIn(email: _email.text, password: _password.text);
      // o roteador leva para o Início quando o estado vira "logado"
    } on AppFailure catch (f) {
      if (mounted) setState(() => _error = f.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    final notice = auth is AuthSignedOut ? auth.notice : null;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
          child: FormWidth(
            child: AutofillGroup(
              child: Form(
                key: _form,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(child: KikaLogo(size: 150)),
                    const SizedBox(height: 12),
                    Text('Entrar no painel', textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineMedium),
                    const SizedBox(height: 6),
                    Text('Use o e-mail e a senha da confeitaria.', textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyMedium),
                    const SizedBox(height: 24),
                    if (notice != null && _error == null) ...[
                      InlineMessage(notice, error: !notice.startsWith('Senha alterada')),
                      const SizedBox(height: 16),
                    ],
                    if (_error != null) ...[InlineMessage(_error!), const SizedBox(height: 16)],
                    TextFormField(
                      key: const Key('login_email'),
                      controller: _email,
                      enabled: !_loading,
                      keyboardType: TextInputType.emailAddress,
                      autofillHints: const [AutofillHints.email],
                      textInputAction: TextInputAction.next,
                      autocorrect: false,
                      inputFormatters: [FilteringTextInputFormatter.deny(RegExp(r'\s'))],
                      decoration: const InputDecoration(labelText: 'E-mail', prefixIcon: Icon(Icons.mail_outline)),
                      validator: Validators.email,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      key: const Key('login_password'),
                      controller: _password,
                      enabled: !_loading,
                      obscureText: _obscure,
                      autofillHints: const [AutofillHints.password],
                      textInputAction: TextInputAction.done,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Senha',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          tooltip: _obscure ? 'Mostrar senha' : 'Esconder senha',
                          icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                          onPressed: () => setState(() => _obscure = !_obscure),
                        ),
                      ),
                      validator: Validators.loginPassword,
                    ),
                    const SizedBox(height: 22),
                    LoadingButton(key: const Key('login_submit'), label: 'Entrar', loading: _loading, onPressed: _submit),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: _loading ? null : () => context.go(Routes.forgot),
                      child: const Text('Esqueceu a senha?'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
