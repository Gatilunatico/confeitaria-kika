/// Configuração do app, lida no build com `--dart-define-from-file=config/local.json`.
///
/// Só a URL do projeto e a chave **publishable** do Supabase. Nunca a `service_role`: o app
/// roda no celular e qualquer valor aqui pode ser extraído do APK. A proteção dos dados é o
/// RLS do banco, com o login da dona.
class AppConfig {
  const AppConfig({required this.supabaseUrl, required this.supabaseKey, required this.storeSlug});

  final String supabaseUrl;
  final String supabaseKey;
  final String storeSlug;

  static const _url = String.fromEnvironment('SUPABASE_URL');
  static const _key = String.fromEnvironment('SUPABASE_KEY');
  static const _slug = String.fromEnvironment('STORE_SLUG', defaultValue: 'kika-cakes');

  /// Configuração do build atual. Lança [AppConfigError] se faltar algo ou se a chave for privilegiada.
  static AppConfig fromEnvironment() => validate(supabaseUrl: _url, supabaseKey: _key, storeSlug: _slug);

  static AppConfig validate({required String supabaseUrl, required String supabaseKey, required String storeSlug}) {
    final url = supabaseUrl.trim();
    final key = supabaseKey.trim();
    if (url.isEmpty || key.isEmpty) {
      throw const AppConfigError('SUPABASE_URL e SUPABASE_KEY não foram informados no build.');
    }
    final uri = Uri.tryParse(url);
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const AppConfigError('SUPABASE_URL precisa ser um endereço https.');
    }
    if (key.startsWith('sb_secret') || _isServiceRoleJwt(key)) {
      throw const AppConfigError('A chave informada é privilegiada. Use a chave publishable.');
    }
    return AppConfig(supabaseUrl: url, supabaseKey: key, storeSlug: storeSlug.trim());
  }

  /// Chaves JWT antigas: o papel fica no meio do token (base64). `service_role` nunca vai para o app.
  static bool _isServiceRoleJwt(String key) {
    final parts = key.split('.');
    if (parts.length != 3) return false;
    try {
      final payload = String.fromCharCodes(_decodeBase64Url(parts[1]));
      return payload.contains('"service_role"');
    } catch (_) {
      return false;
    }
  }

  static List<int> _decodeBase64Url(String input) {
    var s = input.replaceAll('-', '+').replaceAll('_', '/');
    while (s.length % 4 != 0) {
      s += '=';
    }
    return Uri.parse('data:application/octet-stream;base64,$s').data!.contentAsBytes();
  }
}

class AppConfigError implements Exception {
  const AppConfigError(this.message);
  final String message;

  @override
  String toString() => message;
}
