/// Produto da tabela `produtos`. Os limites espelham os CHECKs do banco (migrações 001/009),
/// que validam de novo: aqui é só para a dona ver o erro antes de enviar.
class Product {
  const Product({
    required this.id,
    required this.slug,
    required this.name,
    required this.category,
    required this.description,
    required this.unit,
    required this.price,
    required this.priceType,
    required this.available,
    required this.published,
    required this.featured,
    required this.minQty,
    required this.maxQty,
    required this.order,
    required this.productionDays,
    this.photoUrl,
  });

  final String id;
  final String slug;
  final String name;
  final String category;
  final String description;
  final String unit;
  final double? price;
  final String priceType; // a_partir_de | estimado | sob_consulta
  final bool available;
  final bool published;
  final bool featured;
  final int minQty;
  final int maxQty;
  final int order;
  final int? productionDays;
  final String? photoUrl; // foto principal (bucket público product-images)

  static const columns = 'id,slug,nome,categoria,descricao,unidade,preco,tipo_preco,disponivel,publicado,destaque,'
      'qtd_min,qtd_max,ordem,prazo_producao_dias';

  factory Product.fromJson(Map<String, dynamic> j, {String? photoUrl}) => Product(
        id: j['id'] as String,
        slug: j['slug'] as String,
        name: j['nome'] as String,
        category: j['categoria'] as String,
        description: (j['descricao'] as String?) ?? '',
        unit: j['unidade'] as String,
        price: (j['preco'] as num?)?.toDouble(),
        priceType: j['tipo_preco'] as String,
        available: j['disponivel'] as bool? ?? true,
        published: j['publicado'] as bool? ?? true,
        featured: j['destaque'] as bool? ?? false,
        minQty: (j['qtd_min'] as num?)?.toInt() ?? 1,
        maxQty: (j['qtd_max'] as num?)?.toInt() ?? 50,
        order: (j['ordem'] as num?)?.toInt() ?? 0,
        productionDays: (j['prazo_producao_dias'] as num?)?.toInt(),
        photoUrl: photoUrl,
      );

  String get priceLabel => switch (priceType) {
        _ when priceType == priceOnRequest || price == null => 'Preço sob consulta',
        priceEstimated => 'Cerca de ${_brl(price!)} / $unit',
        _ => 'A partir de ${_brl(price!)} / $unit',
      };
}

const priceFrom = 'a_partir_de';
const priceEstimated = 'estimado';
const priceOnRequest = 'sob_consulta';
const priceTypes = {priceFrom: 'A partir de', priceEstimated: 'Estimado', priceOnRequest: 'Sob consulta'};

String _brl(double v) => 'R\$ ${v.toStringAsFixed(2).replaceAll('.', ',')}';

class ProductImage {
  const ProductImage({required this.id, required this.path, required this.url, required this.principal, required this.order});

  final String id;
  final String path;
  final String url;
  final bool principal;
  final int order;
}

/// Dados do formulário → colunas do banco (só as que a dona pode editar).
class ProductDraft {
  const ProductDraft({
    required this.name,
    required this.category,
    required this.description,
    required this.unit,
    required this.price,
    required this.priceType,
    required this.available,
    required this.published,
    required this.featured,
    required this.minQty,
    required this.maxQty,
    required this.productionDays,
  });

  final String name;
  final String category;
  final String description;
  final String unit;
  final double? price;
  final String priceType;
  final bool available;
  final bool published;
  final bool featured;
  final int minQty;
  final int maxQty;
  final int? productionDays;

  Map<String, dynamic> toColumns() => {
        'nome': name,
        'categoria': category,
        'descricao': description,
        'unidade': unit,
        'preco': priceType == priceOnRequest ? null : price,
        'tipo_preco': priceType,
        'disponivel': available,
        'publicado': published,
        'destaque': featured,
        'qtd_min': minQty,
        'qtd_max': maxQty,
        'prazo_producao_dias': productionDays,
      };
}

/// Mesmos limites dos CHECKs do banco e do painel web (services/product_service.py).
abstract final class ProductRules {
  static const maxProductionDays = 90;
  static const maxImages = 10;
  static const maxImageBytes = 5 * 1024 * 1024;

  static String? name(String v) {
    final t = v.trim();
    if (t.length < 2 || t.length > 120) return 'Nome entre 2 e 120 caracteres.';
    if (!RegExp(r'[A-Za-z0-9À-ÿ]').hasMatch(t)) return 'Use letras ou números no nome.';
    return null;
  }

  static String? category(String v) =>
      (v.trim().length < 2 || v.trim().length > 60) ? 'Categoria entre 2 e 60 caracteres.' : null;
  static String? description(String v) => v.trim().length > 500 ? 'No máximo 500 caracteres.' : null;
  static String? unit(String v) =>
      (v.trim().isEmpty || v.trim().length > 40) ? 'Informe a unidade (ex.: kg, unidade, caixa com 6).' : null;
  static String? price(double? v, String type) {
    if (type == priceOnRequest) return null;
    if (v == null || v < 0) return 'Informe um preço válido (zero ou maior).';
    if (v > 99999999) return 'Preço muito alto.';
    return null;
  }

  static String? quantities(int? min, int? max) {
    if (min == null || max == null || min < 1) return 'Mínima deve ser 1 ou mais.';
    if (max < min) return 'A máxima não pode ser menor que a mínima.';
    return null;
  }

  static String? productionDays(int? v) =>
      v != null && (v < 0 || v > maxProductionDays) ? 'Entre 0 e $maxProductionDays dias.' : null;
}
