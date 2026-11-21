import 'package:doceflow_app/core/errors/app_failure.dart';
import 'package:doceflow_app/features/auth/presentation/forgot_password_page.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fakes.dart';

void main() {
  testWidgets('sem sessão salva, abre no login (sem botão de cadastro)', (tester) async {
    await pumpApp(tester, auth: FakeAuthRepository());
    expect(find.text('Entrar no painel'), findsOneWidget);
    expect(find.textContaining('Cadastr'), findsNothing);
    expect(find.textContaining('Criar conta'), findsNothing);
  });

  testWidgets('sessão salva e válida vai direto para o Início', (tester) async {
    await pumpApp(tester, auth: FakeAuthRepository(saved: testAccount));
    expect(find.text('Início'), findsWidgets);
    expect(find.text('Resumo da Kika Cakes'), findsOneWidget);
  });

  testWidgets('sem internet ao abrir: mostra erro e tenta de novo', (tester) async {
    final auth = FakeAuthRepository(saved: testAccount, restoreError: const AppFailure(offlineMessage, kind: FailureKind.offline));
    await pumpApp(tester, auth: auth);
    expect(find.text(offlineMessage), findsOneWidget);
    auth.restoreError = null;
    await tester.tap(find.text('Tentar de novo'));
    await tester.pumpAndSettle();
    expect(find.text('Resumo da Kika Cakes'), findsOneWidget);
  });

  testWidgets('valida e-mail e senha antes de chamar o servidor', (tester) async {
    final auth = FakeAuthRepository();
    await pumpApp(tester, auth: auth);
    await tester.tap(field('login_submit'));
    await tester.pumpAndSettle();
    expect(find.text('Informe o e-mail.'), findsOneWidget);
    expect(find.text('Informe a senha.'), findsOneWidget);
    await tester.enterText(field('login_email'), 'nao-e-email');
    await tester.tap(field('login_submit'));
    await tester.pumpAndSettle();
    expect(find.text('E-mail inválido.'), findsOneWidget);
    expect(auth.signInCalls, 0);
  });

  testWidgets('senha errada mostra mensagem e fica no login', (tester) async {
    await pumpApp(tester, auth: FakeAuthRepository());
    await tester.enterText(field('login_email'), 'dona@teste.dev');
    await tester.enterText(field('login_password'), 'errada');
    await tester.tap(field('login_submit'));
    await tester.pumpAndSettle();
    expect(find.text('E-mail ou senha incorretos.'), findsOneWidget);
    expect(find.text('Entrar no painel'), findsOneWidget);
  });

  testWidgets('conta sem perfil administrativo não entra', (tester) async {
    final auth = FakeAuthRepository()..noAccess = true;
    await pumpApp(tester, auth: auth);
    await tester.enterText(field('login_email'), 'outra@teste.dev');
    await tester.enterText(field('login_password'), 'senha-certa-123');
    await tester.tap(field('login_submit'));
    await tester.pumpAndSettle();
    expect(find.textContaining('não tem acesso'), findsOneWidget);
    expect(find.text('Entrar no painel'), findsOneWidget);
  });

  testWidgets('login certo abre o Início; Sair pede confirmação e volta ao login', (tester) async {
    final auth = FakeAuthRepository();
    await pumpApp(tester, auth: auth);
    await tester.enterText(field('login_email'), 'dona@teste.dev');
    await tester.enterText(field('login_password'), 'senha-certa-123');
    await tester.tap(field('login_submit'));
    await tester.pumpAndSettle();
    expect(find.text('Resumo da Kika Cakes'), findsOneWidget);

    await tester.tap(find.text('Perfil'));
    await tester.pumpAndSettle();
    expect(find.text('dona@teste.dev'), findsOneWidget);
    await tester.tap(field('logout'));
    await tester.pumpAndSettle();
    await tester.tap(field('logout_confirm'));
    await tester.pumpAndSettle();
    expect(auth.signOutCalls, 1);
    expect(find.text('Entrar no painel'), findsOneWidget);
  });

  testWidgets('sessão encerrada pelo servidor volta ao login com aviso', (tester) async {
    final auth = FakeAuthRepository(saved: testAccount);
    await pumpApp(tester, auth: auth);
    auth.endSession();
    await tester.pumpAndSettle();
    expect(find.text('Sua sessão terminou. Entre novamente.'), findsOneWidget);
  });

  testWidgets('bloqueia por alguns minutos depois de 5 senhas erradas', (tester) async {
    final auth = FakeAuthRepository();
    await pumpApp(tester, auth: auth);
    await tester.enterText(field('login_email'), 'dona@teste.dev');
    for (var i = 0; i < 6; i++) {
      await tester.enterText(field('login_password'), 'errada$i');
      await tester.tap(field('login_submit'));
      await tester.pumpAndSettle();
    }
    expect(auth.signInCalls, 5); // a 6ª nem chega ao servidor
    expect(find.textContaining('Muitas tentativas'), findsOneWidget);
  });

  testWidgets('recuperação: e-mail, código e nova senha; depois volta ao login', (tester) async {
    final auth = FakeAuthRepository();
    await pumpApp(tester, auth: auth);
    await tester.tap(find.text('Esqueceu a senha?'));
    await tester.pumpAndSettle();
    await tester.enterText(field('forgot_email'), 'dona@teste.dev');
    await tester.tap(field('forgot_send'));
    await tester.pumpAndSettle();
    expect(auth.recoveryEmails, ['dona@teste.dev']);
    expect(find.text(recoverySentMessage), findsOneWidget);

    await tester.enterText(field('forgot_code'), '123456');
    await tester.enterText(field('forgot_password'), 'curta');
    await tester.enterText(field('forgot_confirm'), 'curta');
    await tester.tap(field('forgot_reset'));
    await tester.pumpAndSettle();
    expect(find.text('Use pelo menos 10 caracteres.'), findsOneWidget);
    expect(auth.resets, isEmpty);

    await tester.enterText(field('forgot_password'), 'NovaSenha2026');
    await tester.enterText(field('forgot_confirm'), 'NovaSenha2026');
    await tester.tap(field('forgot_reset'));
    await tester.pumpAndSettle();
    expect(auth.resets.single.$3, 'NovaSenha2026');
    expect(find.text('Senha alterada! Entre com a nova senha.'), findsOneWidget);
    expect(find.text('Entrar no painel'), findsOneWidget);
  });

  testWidgets('código errado mostra erro e não troca a senha', (tester) async {
    final auth = FakeAuthRepository();
    await pumpApp(tester, auth: auth);
    await tester.tap(find.text('Esqueceu a senha?'));
    await tester.pumpAndSettle();
    await tester.enterText(field('forgot_email'), 'dona@teste.dev');
    await tester.tap(field('forgot_send'));
    await tester.pumpAndSettle();
    await tester.enterText(field('forgot_code'), '000000');
    await tester.enterText(field('forgot_password'), 'NovaSenha2026');
    await tester.enterText(field('forgot_confirm'), 'NovaSenha2026');
    await tester.tap(field('forgot_reset'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Código inválido'), findsOneWidget);
    expect(auth.resets, isEmpty);
    expect(find.byType(ForgotPasswordPage), findsOneWidget);
  });
}
