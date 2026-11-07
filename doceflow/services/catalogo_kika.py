"""Catálogo oficial da Kika Cakes, transcrito dos cardápios em PDF (nov/2026):
tabela de preços de bolos, cardápio de doces & personalizados e cardápio de doces finos.

É a fonte única dos dados iniciais: `services/catalog.py` usa esta lista no
SQLite local; `supabase/seed.sql` e `supabase/migrations/003_catalogo_real.sql` foram gerados dela.
Preços são "a partir de": o valor final é confirmado pela confeitaria.
"""

CAKE_NOTE = " Informe o sabor nas observações. Peso final, decoração e valor são confirmados pela confeitaria."
SWEETS_NOTE = " Informe os sabores nas observações."
TAG_NOTE = " Personalizado com tag. Pedido mínimo de 6 unidades. Informe tema e nome nas observações."
PASTA_NOTE = " Personalizado em pasta americana. Pedido mínimo de 6 unidades. Informe tema e nome nas observações."
LABEL_NOTE = " Personalizado com etiqueta. Informe tema e nome nas observações."
FILLINGS = " Recheios: limão, maracujá, ninho, coco ou brigadeiro (50 un: até 2 sabores; 100 un: até 4 sabores)."

# (ordem, slug, nome, categoria, descrição, unidade, preço, imagem, qtd_min, qtd_max)
CATALOGO = [
    # Bolos (por kg)
    (1, "bolo-tradicional", "Bolo Tradicional", "Bolos",
     "Sabores: Brigadeiro (tradicional de chocolate); Brigadeiro de Leite Ninho; Dois Amores (brigadeiro branco "
     "e tradicional); Prestígio (coco com brigadeiro tradicional)." + CAKE_NOTE,
     "kg", 90.0, "bolo-festa.svg", 1, 20),
    (2, "bolo-especial", "Bolo Especial", "Bolos",
     "Sabores: Abacaxi; Abacaxi com Coco; Doce de Leite (Moça cozida); Doce de Leite com Abacaxi; Doce de Leite "
     "com Ameixa; Olho de Sogra (coco e doce de leite com ameixa); Sensação (mousse de morango com raspas de "
     "chocolate e brigadeiro)." + CAKE_NOTE,
     "kg", 95.0, "bolo-festa.svg", 1, 20),
    (3, "bolo-nobre-frutas", "Bolo Nobre com Frutas", "Bolos",
     "Sabores: Ninho com Morango (creme de Leite Ninho com morangos frescos); Brigadeiro com Morango; "
     "Brigadeiro de Maracujá." + CAKE_NOTE,
     "kg", 100.0, "naked-cake.svg", 1, 20),
    (4, "bolo-geleia-artesanal", "Bolo com Geleia Artesanal", "Bolos",
     "Sabores: Frutas Amarelas (redução artesanal); Geleia de Frutas Vermelhas (morango, amora e framboesa); "
     "Geleia de Morango (pedaçuda, feita na confeitaria)." + CAKE_NOTE,
     "kg", 110.0, "naked-cake.svg", 1, 20),
    # Docinhos (por cento)
    (10, "docinhos-tradicionais", "Docinhos Tradicionais", "Docinhos",
     "Sabores: Brigadeiro, Beijinho, Ninho, Prestígio (brigadeiro tradicional com coco) e Bicho de Pé." + SWEETS_NOTE,
     "cento", 150.0, "brigadeiros.svg", 1, 20),
    (11, "docinhos-premium", "Docinhos Linha Premium", "Docinhos",
     "Sabores: Ninho com Nutella, Ferrero Rocher, Bicho de Pé com Nutella, Churros e Surpresa de Uva." + SWEETS_NOTE,
     "cento", 200.0, "brigadeiros.svg", 1, 20),
    # Personalizados com tag (mínimo 6)
    (20, "pirulito-ao-leite-tag", "Pirulito ao Leite com Tag", "Personalizados com Tag",
     "Pirulito de chocolate ao leite." + TAG_NOTE, "unidade", 6.0, "pirulito.svg", 6, 300),
    (21, "pirulito-branco-tag", "Pirulito Branco com Tag", "Personalizados com Tag",
     "Pirulito de chocolate branco." + TAG_NOTE, "unidade", 7.0, "pirulito.svg", 6, 300),
    (22, "pao-de-mel-palito-tag", "Pão de Mel no Palito (Grande) com Tag", "Personalizados com Tag",
     "Pão de mel grande no palito." + TAG_NOTE, "unidade", 10.0, "pao-de-mel.svg", 6, 300),
    (23, "maca-de-chocolate-tag", "Maçã de Chocolate com Tag", "Personalizados com Tag",
     "Maçã coberta com chocolate." + TAG_NOTE, "unidade", 14.0, "maca-chocolate.svg", 6, 300),
    (24, "cupcake-tag", "Cupcake com Tag", "Personalizados com Tag",
     "Cupcake decorado." + TAG_NOTE, "unidade", 8.5, "cupcakes.svg", 6, 300),
    # Personalizados com etiqueta
    (30, "brownie-etiqueta", "Brownie com Etiqueta", "Personalizados com Etiqueta",
     "Brownie sem recheio." + LABEL_NOTE, "unidade", 8.0, "brownie.svg", 1, 300),
    (31, "mini-pao-de-mel-etiqueta", "Mini Pão de Mel com Etiqueta", "Personalizados com Etiqueta",
     "Mini pão de mel." + LABEL_NOTE, "unidade", 5.0, "pao-de-mel.svg", 1, 300),
    # Personalizados em pasta americana (mínimo 6)
    (40, "pirulito-ao-leite-pasta", "Pirulito ao Leite em Pasta Americana", "Personalizados em Pasta Americana",
     "Pirulito de chocolate ao leite." + PASTA_NOTE, "unidade", 9.5, "pirulito.svg", 6, 300),
    (41, "pirulito-branco-pasta", "Pirulito Branco em Pasta Americana", "Personalizados em Pasta Americana",
     "Pirulito de chocolate branco." + PASTA_NOTE, "unidade", 10.5, "pirulito.svg", 6, 300),
    (42, "pao-de-mel-palito-pasta", "Pão de Mel no Palito em Pasta Americana", "Personalizados em Pasta Americana",
     "Pão de mel no palito." + PASTA_NOTE, "unidade", 14.0, "pao-de-mel.svg", 6, 300),
    (43, "mini-pao-de-mel-pasta", "Mini Pão de Mel em Pasta Americana", "Personalizados em Pasta Americana",
     "Mini pão de mel." + PASTA_NOTE, "unidade", 6.5, "pao-de-mel.svg", 6, 300),
    (44, "maca-de-chocolate-pasta", "Maçã de Chocolate em Pasta Americana", "Personalizados em Pasta Americana",
     "Maçã coberta com chocolate." + PASTA_NOTE, "unidade", 16.0, "maca-chocolate.svg", 6, 300),
    (45, "cupcake-pasta", "Cupcake em Pasta Americana", "Personalizados em Pasta Americana",
     "Cupcake decorado." + PASTA_NOTE, "unidade", 12.0, "cupcakes.svg", 6, 300),
    # Doces finos
    (50, "baby-brownie", "Baby Brownie", "Doces Finos",
     "Sabores: Brigadeiro, Ninho e Doce de Leite. Pedido mínimo de 25 unidades." + SWEETS_NOTE,
     "unidade", 2.5, "doces-finos.jpg", 25, 1000),
    (51, "bem-casado", "Bem Casado", "Doces Finos",
     "Embalado no papel crepom com laço de cetim e tag personalizada. Pedido mínimo de 25 unidades.",
     "unidade", 6.0, "bem-casado.jpg", 25, 1000),
    (52, "mini-trufa-simples-blend", "Mini Trufa Recheada Simples (Blend)", "Doces Finos",
     "Cobertura de chocolate blend. R$ 160,00 o cento. Pedido mínimo de 50 unidades." + FILLINGS,
     "unidade", 1.6, "mini-trufa.jpg", 50, 1000),
    (53, "mini-trufa-simples-branca", "Mini Trufa Recheada Simples (Branca)", "Doces Finos",
     "Cobertura de chocolate branco. R$ 180,00 o cento. Pedido mínimo de 50 unidades." + FILLINGS,
     "unidade", 1.8, "mini-trufa.jpg", 50, 1000),
    (54, "mini-trufa-decorada-blend", "Mini Trufa Recheada Decorada (Blend)", "Doces Finos",
     "Cobertura de chocolate blend, decorada. Pedido mínimo de 50 unidades." + FILLINGS,
     "unidade", 2.6, "trufa-decorada.jpg", 50, 1000),
    (55, "mini-trufa-decorada-branca", "Mini Trufa Recheada Decorada (Branca)", "Doces Finos",
     "Cobertura de chocolate branco, decorada. Pedido mínimo de 50 unidades." + FILLINGS,
     "unidade", 2.8, "trufa-decorada.jpg", 50, 1000),
    (56, "copinho-chocolate-blend", "Copinho de Chocolate (Blend)", "Doces Finos",
     "Copinho de cobertura de chocolate blend. Pedido mínimo de 50 unidades. Decoração com frutas: consultar "
     "valores." + FILLINGS, "unidade", 3.8, "copinho.jpg", 50, 1000),
    (57, "copinho-chocolate-branco", "Copinho de Chocolate (Branco)", "Doces Finos",
     "Copinho de cobertura de chocolate branco. Pedido mínimo de 50 unidades. Decoração com frutas: consultar "
     "valores." + FILLINGS, "unidade", 4.5, "copinho.jpg", 50, 1000),
]

WHATSAPP_OFICIAL = "5511979855065"  # (11) 97985-5065, publicado nos cardápios
