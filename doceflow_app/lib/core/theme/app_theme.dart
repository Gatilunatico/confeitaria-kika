import 'package:flutter/material.dart';

/// Identidade Kika Cakes no app.
///
/// Contraste (WCAG AA, texto normal ≥ 4,5:1):
/// - marrom sobre rosa: 10,4:1; branco sobre marrom: 12,0:1 → texto e botões principais;
/// - o destaque (#E0628A) tem só 3,3:1 com branco: fica em detalhes, ícones, indicadores e
///   textos grandes em negrito, nunca em texto pequeno.
abstract final class KikaColors {
  static const rosa = Color(0xFFFDE8EC);
  static const marrom = Color(0xFF5C3317);
  static const destaque = Color(0xFFE0628A);
  static const branco = Color(0xFFFFFFFF);
  static const rosaBorda = Color(0xFFF5C6D1); // bordas e divisórias sobre o rosa
  static const erro = Color(0xFFB3261E);
}

abstract final class KikaFonts {
  static const titulos = 'AbrilFatface';
  static const textos = 'Quicksand';
}

ThemeData buildKikaTheme() {
  const scheme = ColorScheme(
    brightness: Brightness.light,
    primary: KikaColors.marrom,
    onPrimary: KikaColors.branco,
    secondary: KikaColors.destaque,
    onSecondary: KikaColors.marrom,
    tertiary: KikaColors.destaque,
    onTertiary: KikaColors.marrom,
    error: KikaColors.erro,
    onError: KikaColors.branco,
    surface: KikaColors.branco,
    onSurface: KikaColors.marrom,
    surfaceContainerHighest: KikaColors.rosa,
    outline: KikaColors.rosaBorda,
  );

  final base = ThemeData(useMaterial3: true, colorScheme: scheme, fontFamily: KikaFonts.textos);
  final text = base.textTheme.apply(bodyColor: KikaColors.marrom, displayColor: KikaColors.marrom);
  TextStyle? title(TextStyle? s) => s?.copyWith(fontFamily: KikaFonts.titulos, fontWeight: FontWeight.w400);

  return base.copyWith(
    scaffoldBackgroundColor: KikaColors.rosa,
    textTheme: text.copyWith(
      displayLarge: title(text.displayLarge),
      displayMedium: title(text.displayMedium),
      displaySmall: title(text.displaySmall),
      headlineLarge: title(text.headlineLarge),
      headlineMedium: title(text.headlineMedium),
      headlineSmall: title(text.headlineSmall),
      titleLarge: title(text.titleLarge),
      bodyLarge: text.bodyLarge?.copyWith(fontWeight: FontWeight.w500),
      bodyMedium: text.bodyMedium?.copyWith(fontWeight: FontWeight.w500),
      labelLarge: text.labelLarge?.copyWith(fontWeight: FontWeight.w700),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: KikaColors.rosa,
      foregroundColor: KikaColors.marrom,
      elevation: 0,
      scrolledUnderElevation: 1,
      centerTitle: false,
      titleTextStyle: TextStyle(fontFamily: KikaFonts.titulos, fontSize: 24, color: KikaColors.marrom),
    ),
    cardTheme: CardThemeData(
      color: KikaColors.branco,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: KikaColors.rosaBorda),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: KikaColors.marrom,
        foregroundColor: KikaColors.branco,
        minimumSize: const Size.fromHeight(52),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontFamily: KikaFonts.textos, fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: KikaColors.marrom,
        minimumSize: const Size.fromHeight(52),
        shape: const StadiumBorder(),
        side: const BorderSide(color: KikaColors.marrom, width: 1.4),
        textStyle: const TextStyle(fontFamily: KikaFonts.textos, fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: KikaColors.marrom,
        textStyle: const TextStyle(
          fontFamily: KikaFonts.textos,
          fontWeight: FontWeight.w700,
          decoration: TextDecoration.underline,
        ),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: KikaColors.branco,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: KikaColors.rosaBorda),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: KikaColors.destaque, width: 2),
      ),
      labelStyle: const TextStyle(color: KikaColors.marrom),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: KikaColors.branco,
      indicatorColor: KikaColors.rosa,
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontFamily: KikaFonts.textos, fontWeight: FontWeight.w700, color: KikaColors.marrom),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected) ? KikaColors.destaque : KikaColors.marrom,
        ),
      ),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: KikaColors.destaque),
    snackBarTheme: const SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: KikaColors.marrom,
      contentTextStyle: TextStyle(fontFamily: KikaFonts.textos, color: KikaColors.branco, fontWeight: FontWeight.w600),
    ),
    dividerTheme: const DividerThemeData(color: KikaColors.rosaBorda),
  );
}
