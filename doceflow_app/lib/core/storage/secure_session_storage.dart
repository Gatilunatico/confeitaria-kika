import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

/// Guarda a sessão do Supabase no armazenamento seguro do Android (Keystore), e não no
/// SharedPreferences em texto puro, que é o padrão do supabase_flutter.
///
/// A sessão contém o token de acesso e o de renovação: quem tiver os dois entra como a dona.
class SecureSessionStorage extends LocalStorage {
  SecureSessionStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(aOptions: AndroidOptions(encryptedSharedPreferences: true));

  static const sessionKey = 'doceflow.supabase.session';
  final FlutterSecureStorage _storage;

  @override
  Future<void> initialize() async {}

  @override
  Future<bool> hasAccessToken() => _storage.containsKey(key: sessionKey);

  @override
  Future<String?> accessToken() => _storage.read(key: sessionKey);

  @override
  Future<void> persistSession(String persistSessionString) =>
      _storage.write(key: sessionKey, value: persistSessionString);

  @override
  Future<void> removePersistedSession() => _storage.delete(key: sessionKey);
}
