"""Etapa 6: separação dos apps, autenticação do painel, interface sem elementos técnicos e
ausência de segredos no que é exibido ou distribuído.

Numeração = lista de testes obrigatórios da etapa 6 (os testes de banco estão em test_etapa06_postgres.py).
"""

import ast
import re
import subprocess
import tomllib
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_APP = str(ROOT / "public_app.py")
ADMIN_APP = str(ROOT / "admin_app.py")
ADMIN_PAGES = ["pages/admin/dashboard.py", "pages/admin/orders.py", "pages/admin/quotes.py",
               "pages/admin/products.py", "pages/admin/marketing.py"]
CANARY_KEY = "sb_publishable_CANARIO_9f8e7d6c5b4a3210"
CANARY_URL = "https://canario-etapa6.supabase.co"
PASSWORD = "senha-etapa6-teste"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_NAME", "STORE_SLUG", "PUBLIC_APP_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "etapa6.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("WHATSAPP_NUMBER", "5511979855065")


def run(app):
    return AppTest.from_file(app, default_timeout=60).run()


def all_text(at) -> str:
    """Tudo o que o servidor manda para o navegador (protobuf de todos os elementos da página)."""
    parts = []

    def walk(node):
        proto = getattr(node, "proto", None)
        if proto is not None:
            parts.append(str(proto))
        for child in getattr(node, "children", {}).values() if isinstance(getattr(node, "children", None), dict) \
                else getattr(node, "children", []) or []:
            walk(child)

    walk(at._tree)
    return "\n".join(parts)


# ================================================================ separação dos apps
PROJECT_PACKAGES = ("services", "components", "marketing", "config", "database")
ADMIN_ONLY_MODULES = ("services.auth_service", "marketing", "components.image_manager", "components.product_form",
                      "components.navigation", "components.dashboard_metrics", "components.data_table")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found |= {f"{node.module}.{a.name}" for a in node.names}
    return {m for m in found if m.split(".")[0] in PROJECT_PACKAGES}


def _module_file(mod: str) -> Path | None:
    for candidate in (ROOT / (mod.replace(".", "/") + ".py"), ROOT / mod.replace(".", "/") / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


def import_closure(entry_files: list[Path]) -> set[str]:
    seen, todo = set(), [f for f in entry_files]
    while todo:
        f = todo.pop()
        for mod in _imports(f):
            if mod not in seen:
                seen.add(mod)
                target = _module_file(mod)
                if target is not None:
                    todo.append(target)
    return seen


def test_10_public_app_does_not_import_admin_modules():
    entries = [ROOT / "public_app.py", *sorted((ROOT / "pages" / "public").glob("*.py"))]
    closure = import_closure(entries)
    leaked = sorted(m for m in closure if m.startswith(ADMIN_ONLY_MODULES))
    assert leaked == []
    assert "services.repository" in closure  # serviços de dados compartilhados (protegidos pelo RLS)


def test_10_public_app_registers_only_public_pages():
    source = (ROOT / "public_app.py").read_text(encoding="utf-8")
    assert "pages/admin" not in source and "auth_service" not in source
    pages = re.findall(r'st\.Page\("([^"]+)"', source)
    assert pages == ["pages/public/catalog.py", "pages/public/order.py", "pages/public/privacy.py"]


def test_10_admin_app_registers_only_admin_pages():
    pages = re.findall(r'st\.Page\("([^"]+)"', (ROOT / "admin_app.py").read_text(encoding="utf-8"))
    assert pages == ["pages/admin/login.py", *ADMIN_PAGES]


def test_public_app_renders_catalog_without_menu_or_login():
    at = run(PUBLIC_APP)
    assert not at.exception and at.title[0].value == "Kika Cakes"
    assert [b.label for b in at.button].count("Solicitar orçamento") == 27
    assert not at.text_input  # nenhum campo de login na vitrine


# ================================================================ 1 e 6. Painel sem login
@pytest.mark.parametrize("page", ADMIN_PAGES)
def test_1_6_admin_pages_without_login_go_to_login(page):
    at = run(ADMIN_APP)
    assert at.title[0].value == "Painel administrativo"  # a raiz do admin é o login
    at.switch_page(page).run()  # acesso direto à página interna
    assert at.title[0].value == "Painel administrativo"
    assert not at.metric and not at.get("download_button")


def test_7_forged_session_state_is_not_enough():
    at = run(ADMIN_APP)
    at.session_state["admin_ok"] = True
    at.session_state["admin_binding"] = "forjado"
    at.switch_page("pages/admin/orders.py").run()
    assert at.title[0].value == "Painel administrativo"


def test_wrong_password_then_login_and_logout():
    at = run(ADMIN_APP)
    at.text_input[0].input("errada")
    at.button[0].click().run()
    assert any("Senha incorreta" in e.value for e in at.error)
    at.text_input[0].input(PASSWORD)
    at.button[0].click().run()
    assert at.title[0].value.startswith("Painel ·") and at.metric
    next(b for b in at.button if b.label == "Sair").click().run()
    at.switch_page("pages/admin/dashboard.py").run()
    assert at.title[0].value == "Painel administrativo" and not at.metric


# ================================================================ 7. Supabase: sessão expirada, inválida, sem perfil
class _Auth:
    def __init__(self, mode="ok"):
        self.mode, self.signed_out = mode, False

    def sign_in_with_password(self, creds):
        if creds["password"] != "synthetic-valid-password":
            raise ValueError("Invalid login credentials")
        return SimpleNamespace(user=SimpleNamespace(id="user-1"))

    def get_user(self):
        if self.mode == "expired":
            raise ValueError("JWT expired")
        if self.mode == "other_user":
            return SimpleNamespace(user=SimpleNamespace(id="user-2"))
        return SimpleNamespace(user=SimpleNamespace(id="user-1"))

    def sign_out(self):
        self.signed_out = True


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "synthetic-publishable-key")
    monkeypatch.setenv("STORE_SLUG", "kika-cakes")
    import config

    return config.load_settings()


@pytest.mark.parametrize("mode", ["expired", "other_user"])
def test_7_expired_or_invalid_supabase_session_is_rejected_on_server(supabase_env, monkeypatch, mode):
    import services.repository as repository
    from services.auth_service import authorized_admin_repository, session_token

    monkeypatch.setattr(repository.SupabaseRepository, "for_owner", classmethod(lambda cls, c, uid, slug=None: "repo"))
    state = {"admin_ok": True, "admin_binding": session_token(supabase_env), "admin_user_id": "user-1",
             "admin_client": SimpleNamespace(auth=_Auth("ok"))}
    assert authorized_admin_repository(state, supabase_env) == "repo"  # controle: sessão boa passa
    state["admin_client"] = SimpleNamespace(auth=_Auth(mode))
    assert authorized_admin_repository(state, supabase_env) is None


def test_7_authenticated_user_without_admin_profile_cannot_enter(supabase_env, monkeypatch):
    import services.repository as repository
    import services.supabase_client as supabase_client
    from services.auth_service import AuthError, is_admin_session, login_supabase

    auth = _Auth()
    monkeypatch.setattr(supabase_client, "get_supabase_client", lambda s: SimpleNamespace(auth=auth))

    def no_profile(cls, client, uid, slug=None):
        raise repository.AdminAccessError("Este usuário não está vinculado a nenhuma confeitaria.")

    monkeypatch.setattr(repository.SupabaseRepository, "for_owner", classmethod(no_profile))
    state = {}
    with pytest.raises(AuthError, match="não está vinculado"):
        login_supabase(state, supabase_env, "qualquer@teste.dev", "synthetic-valid-password")
    assert auth.signed_out and not is_admin_session(state, supabase_env)


# ================================================================ 8. Nada de segredo ou detalhe técnico na tela
class _FakeQuery:
    def __init__(self, data, fail):
        self.data, self.fail = data, fail

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        if self.fail:
            raise ConnectionError(f"falha ao conectar em {CANARY_URL} com apikey={CANARY_KEY}")
        return SimpleNamespace(data=self.data)


def _fake_client(fail=False):
    store = {"id": "11111111-1111-1111-1111-111111111111", "slug": "kika-cakes", "nome": "Kika Cakes",
             "whatsapp": "5511979855065"}
    prod = {"id": "22222222-2222-2222-2222-222222222222", "slug": "bolo", "nome": "Bolo Teste", "categoria": "Bolos",
            "descricao": "", "unidade": "kg", "preco": 90, "tipo_preco": "a_partir_de", "disponivel": True,
            "imagem": None, "qtd_min": 1, "qtd_max": 5, "ordem": 1, "publicado": True}
    tables = {"confeitarias": [store], "produtos": [prod], "product_images": []}
    storage = SimpleNamespace(from_=lambda b: SimpleNamespace(get_public_url=lambda p: f"{CANARY_URL}/x/{p}"))
    return SimpleNamespace(table=lambda name: _FakeQuery(tables.get(name, []), fail), storage=storage,
                           rpc=lambda *a: _FakeQuery([], fail))


@pytest.mark.parametrize("fail", [False, True], ids=["banco_ok", "banco_fora_do_ar"])
def test_8_public_pages_never_show_keys_or_infrastructure(monkeypatch, fail):
    import services.repository as repository

    monkeypatch.setenv("DB_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", CANARY_URL)
    monkeypatch.setenv("SUPABASE_KEY", CANARY_KEY)
    monkeypatch.setattr(repository, "get_supabase_client", lambda settings: _fake_client(fail))
    for page in (None, "pages/public/order.py", "pages/public/privacy.py"):
        at = run(PUBLIC_APP)
        if page:
            at.switch_page(page).run()
        text = all_text(at)
        if page is None and fail:
            assert "indisponível" in text  # a cliente recebe só a mensagem amigável
        assert CANARY_KEY not in text and "sb_publishable" not in text
        for word in ("DB_BACKEND", "SUPABASE_URL", "SUPABASE_KEY", "Secrets", "Detalhes técnicos", "Traceback",
                     "ConnectionError", "apikey"):
            assert word not in text, (page, word)


def test_8_error_details_and_platform_chrome_are_hidden():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["client"]["showErrorDetails"] == "none"  # o antigo `false` passou a mostrar o stacktrace
    assert cfg["client"]["showErrorLinks"] is False
    for app in (PUBLIC_APP, ADMIN_APP):
        css = " ".join(m.value for m in run(app).markdown)
        for selector in ("stToolbar", "stAppDeployButton", "stMainMenu", "stDecoration", "stStatusWidget"):
            assert selector in css, (app, selector)


def test_public_pages_have_no_developer_references():
    for f in sorted((ROOT / "pages" / "public").glob("*.py")) + [ROOT / "components" / "product_card.py",
                                                                 ROOT / "components" / "quote_dialog.py"]:
        visible = " ".join(s.value for s in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
                           if isinstance(s, ast.Constant) and isinstance(s.value, str) and not s.value.startswith(
                               ("pages/", "Vitrine", "doceflow.")))
        for word in ("github", "vscode", "VS Code", "localhost", "streamlit.io", "DB_BACKEND", "Detalhes técnicos"):
            assert word.lower() not in visible.lower(), (f.name, word)


# ================================================================ 9. Chaves privilegiadas nos arquivos distribuídos
PRIVILEGED = {
    "sb_secret": r"sb_secret_[A-Za-z0-9_-]{16,}",
    "service_role_value": r"SUPABASE_SERVICE_ROLE_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_.-]{20,}",
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----",
    "db_url_with_password": r"postgres(?:ql)?://[^:/@\s]+:[^@\s<]{6,}@",
    "meta_token": r"\bEAA[A-Za-z0-9]{30,}",
    "instagram_token": r"\bIG(?:QV|AA)[A-Za-z0-9_-]{30,}",
    "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
}


def test_9_no_privileged_keys_in_versioned_files():
    try:
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git indisponível")
    hits = []
    for rel in files.splitlines():
        p = ROOT / rel
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".ttf", ".otf", ".ico"} or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        hits += [(rel, name) for name, pat in PRIVILEGED.items() if re.search(pat, text)]
    assert hits == []  # nomes de arquivo e tipo apenas: nunca o valor
    assert ".env" not in files.splitlines() and ".streamlit/secrets.toml" not in files.splitlines()


# ================================================================ 11. Worker / integrações
def test_11_no_code_reads_meta_or_instagram_tokens():
    """O worker do Instagram ainda não existe; nenhum módulo do app pode ler tokens da Meta.
    O token, quando existir, fica só no Supabase Vault (coluna não legível: test_etapa06_postgres)."""
    pattern = re.compile(r"(INSTAGRAM|META|FACEBOOK|IG)_[A-Z_]*(TOKEN|SECRET)", re.I)
    offenders = [str(f.relative_to(ROOT)) for f in ROOT.rglob("*.py")
                 if ".venv" not in f.parts and "tests" not in f.parts and pattern.search(f.read_text(encoding="utf-8"))]
    assert offenders == []


def test_order_flow_still_works_in_public_app():
    """Não regredir funcionalidade comercial: pedido completo pelo app público."""
    at = run(PUBLIC_APP)
    at.switch_page("pages/public/order.py").run()
    at.multiselect(key="ord_0_products").set_value(["bem-casado"]).run()
    at.number_input(key="ord_0_qty_bem-casado").set_value(50)
    at.text_input(key="ord_0_name").input("Cliente Etapa Seis")
    at.text_input(key="ord_0_phone").input("(11) 98765-4321")
    at.date_input(key="ord_0_date").set_value(date.today() + timedelta(days=8))
    at.radio(key="ord_0_fulfillment").set_value("Retirada").run()
    at.checkbox(key="ord_0_consent").check()
    at.button(key="ord_review").click().run()
    at.button(key="ord_confirm").click().run()
    assert any("Pedido registrado" in s.value for s in at.success)


def test_app_py_is_the_public_storefront():
    """app.py é o arquivo do app publicado mais antigo: precisa ser só a vitrine (sem painel)."""
    def pages(name):
        return re.findall(r'st\.Page\("([^"]+)"', (ROOT / name).read_text(encoding="utf-8"))

    assert pages("app.py") == pages("public_app.py")
    assert "auth_service" not in (ROOT / "app.py").read_text(encoding="utf-8")
    entries = [ROOT / "app.py", *sorted((ROOT / "pages" / "public").glob("*.py"))]
    assert not [m for m in import_closure(entries) if m.startswith(ADMIN_ONLY_MODULES)]
