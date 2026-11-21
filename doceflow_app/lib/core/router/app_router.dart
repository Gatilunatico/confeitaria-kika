import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/application/auth_controller.dart';
import '../../features/auth/presentation/forgot_password_page.dart';
import '../../features/auth/presentation/login_page.dart';
import '../../features/auth/presentation/splash_page.dart';
import '../../features/dashboard/presentation/dashboard_page.dart';
import '../../features/orders/presentation/orders_pages.dart';
import '../../features/products/presentation/product_form_page.dart';
import '../../features/products/presentation/products_page.dart';
import '../../features/profile/presentation/profile_page.dart';
import '../../features/quotes/presentation/quotes_pages.dart';
import '../widgets/home_shell.dart';

abstract final class Routes {
  static const splash = '/abertura';
  static const login = '/entrar';
  static const forgot = '/entrar/esqueci-senha';
  static const home = '/inicio';
  static const quotes = '/orcamentos';
  static const orders = '/pedidos';
  static const products = '/produtos';
  static const profile = '/perfil';
}

/// A navegação segue o estado do login. As telas internas só abrem com [AuthSignedIn]; o
/// banco ainda confere a permissão em cada dado (RLS), então esconder a tela não é a proteção.
final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<AuthState>(ref.read(authControllerProvider));
  ref.listen(authControllerProvider, (_, next) => refresh.value = next);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: Routes.splash,
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final at = state.matchedLocation;
      final onAuthPage = at == Routes.login || at == Routes.forgot;
      return switch (auth) {
        AuthChecking() || AuthRestoreFailed() => at == Routes.splash ? null : Routes.splash,
        AuthSignedOut() => onAuthPage ? null : Routes.login,
        AuthSignedIn() => (onAuthPage || at == Routes.splash) ? Routes.home : null,
      };
    },
    routes: [
      GoRoute(path: Routes.splash, builder: (_, __) => const SplashPage()),
      GoRoute(
        path: Routes.login,
        builder: (_, __) => const LoginPage(),
        routes: [GoRoute(path: 'esqueci-senha', builder: (_, __) => const ForgotPasswordPage())],
      ),
      StatefulShellRoute.indexedStack(
        builder: (_, __, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: Routes.home, builder: (_, __) => const DashboardPage())]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: Routes.quotes,
              builder: (_, __) => const QuotesPage(),
              routes: [
                GoRoute(path: ':id', builder: (_, s) => QuoteDetailPage(quoteId: s.pathParameters['id']!)),
              ],
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: Routes.orders,
              builder: (_, __) => const OrdersPage(),
              routes: [
                GoRoute(path: ':id', builder: (_, s) => OrderDetailPage(orderId: s.pathParameters['id']!)),
              ],
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: Routes.products,
              builder: (_, __) => const ProductsPage(),
              routes: [
                GoRoute(path: 'novo', builder: (_, __) => const ProductFormPage()),
                GoRoute(path: ':id', builder: (_, s) => ProductFormPage(productId: s.pathParameters['id']!)),
              ],
            ),
          ]),
          StatefulShellBranch(routes: [GoRoute(path: Routes.profile, builder: (_, __) => const ProfilePage())]),
        ],
      ),
    ],
  );
});
