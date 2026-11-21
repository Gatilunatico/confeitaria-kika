/// Conta logada que administra a confeitaria (perfil ativo em `admin_profiles`).
class AdminAccount {
  const AdminAccount({
    required this.userId,
    required this.email,
    required this.storeId,
    required this.storeName,
    required this.storeSlug,
    required this.role,
  });

  final String userId;
  final String email;
  final String storeId;
  final String storeName;
  final String storeSlug;
  final String role; // proprietaria | equipe

  String get roleLabel => role == 'proprietaria' ? 'Proprietária' : 'Equipe';
}

/// Operações de conta. A implementação real usa o Supabase Auth; os testes usam uma falsa.
abstract interface class AuthRepository {
  /// Sessão salva no aparelho, conferida no servidor. `null` se não houver sessão.
  Future<AdminAccount?> restoreSession();

  Future<AdminAccount> signIn({required String email, required String password});

  /// Envia o e-mail com o link e o código de 6 dígitos. A resposta é sempre a mesma,
  /// exista ou não a conta (não revela quais e-mails têm acesso).
  Future<void> sendRecoveryEmail(String email);

  /// Valida o código do e-mail, troca a senha e encerra a sessão de recuperação.
  Future<void> resetPasswordWithCode({required String email, required String code, required String newPassword});

  Future<void> changePassword(String newPassword);

  Future<void> signOut();

  /// Avisa quando o Supabase encerra a sessão (token revogado ou renovação recusada).
  Stream<void> get sessionEnded;
}
