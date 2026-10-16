import re
import unittest
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Categoria, Movimentacao, Produto, Usuario


class TestConfig:
    SECRET_KEY = "test-secret-key"
    TESTING = True
    DATABASE_URL = "sqlite://"
    APP_ENV = "testing"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class AuthenticationAndProductsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=["db", "upgrade"])
        self.assertEqual(result.exit_code, 0, result.output)

        with self.app.app_context():
            self.user = Usuario(
                nome="Usuário de teste",
                email="teste@example.com",
                senha_hash=generate_password_hash("SenhaSegura123!"),
            )
            self.category = Categoria(nome="Periféricos")
            db.session.add_all([self.user, self.category])
            db.session.commit()
            self.user_id = self.user.id
            self.category_id = self.category.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def login(self, next_url=None):
        url = "/auth/login"
        if next_url:
            url = f"{url}?{urlencode({'next': next_url})}"
        return self.client.post(
            url,
            data={"email": "teste@example.com", "password": "SenhaSegura123!"},
        )

    def product_data(self, **overrides):
        data = {
            "nome": "Teclado mecânico",
            "codigo_barras": "123456789",
            "categoria_id": str(self.category_id),
            "preco_custo": "100.00",
            "preco_venda": "159.90",
            "quantidade": "12",
            "estoque_minimo": "3",
            "submit": "Salvar produto",
        }
        data.update(overrides)
        return data

    def test_production_requires_stable_secret_and_enforces_secure_defaults(self):
        missing_secret_config = type(
            "MissingSecretConfig",
            (),
            {
                "SECRET_KEY": None,
                "DATABASE_URL": "",
                "APP_ENV": "production",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY é obrigatória"):
            create_app(missing_secret_config)

        production_config = type(
            "ProductionConfig",
            (),
            {
                "SECRET_KEY": "production-test-secret",
                "DATABASE_URL": "sqlite://",
                "APP_ENV": "production",
                "DEBUG": True,
                "SESSION_COOKIE_SECURE": False,
                "REMEMBER_COOKIE_SECURE": False,
            },
        )
        app = create_app(production_config)
        self.assertFalse(app.config["DEBUG"])
        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
        self.assertTrue(app.config["REMEMBER_COOKIE_SECURE"])
        with app.app_context():
            db.engine.dispose()

    def test_production_requires_database_and_readiness_checks_connectivity(self):
        missing_database_config = type(
            "MissingDatabaseConfig",
            (),
            {
                "SECRET_KEY": "production-test-secret",
                "DATABASE_URL": "",
                "APP_ENV": "production",
            },
        )
        with self.assertRaisesRegex(RuntimeError, "DATABASE_URL é obrigatória"):
            create_app(missing_database_config)

        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 200)

    def test_mysql_provider_url_uses_pymysql_and_preserves_encoded_credentials(self):
        production_config = type(
            "MySQLProductionConfig",
            (),
            {
                "SECRET_KEY": "production-test-secret",
                "DATABASE_URL": (
                    "mysql://stockflow:p%40ss%3Aword@mysql.internal:3306/"
                    "stockflow?charset=utf8mb4"
                ),
                "APP_ENV": "production",
            },
        )
        app = create_app(production_config)
        self.assertEqual(
            app.config["SQLALCHEMY_DATABASE_URI"],
            "mysql+pymysql://stockflow:p%40ss%3Aword@mysql.internal:3306/"
            "stockflow?charset=utf8mb4",
        )
        with app.app_context():
            db.engine.dispose()

    def test_development_without_secret_gets_ephemeral_key_without_debug(self):
        development_config = type(
            "DevelopmentConfig",
            (),
            {"SECRET_KEY": None, "DATABASE_URL": "", "APP_ENV": "development"},
        )
        app = create_app(development_config)
        self.assertEqual(len(app.config["SECRET_KEY"]), 64)
        self.assertFalse(app.config["DEBUG"])

    def create_product(self, **overrides):
        return self.client.post(
            "/produtos/novo", data=self.product_data(**overrides)
        )

    def test_private_pages_redirect_to_login_and_logout_revokes_access(self):
        response = self.client.get("/produtos/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith("/auth/login?next="))
        self.assertEqual(self.client.get("/").status_code, 302)

        self.login()
        self.assertEqual(self.client.get("/produtos/").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)

        response = self.client.post("/auth/logout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/produtos/").status_code, 302)

    def test_login_uses_hash_and_rejects_invalid_credentials(self):
        invalid = self.client.post(
            "/auth/login",
            data={"email": "teste@example.com", "password": "incorreta"},
        )
        self.assertEqual(invalid.status_code, 401)
        self.assertIn(b"E-mail ou senha inv", invalid.data)

        with self.app.app_context():
            user = db.session.get(Usuario, self.user_id)
            self.assertNotEqual(user.senha_hash, "SenhaSegura123!")
            self.assertTrue(check_password_hash(user.senha_hash, "SenhaSegura123!"))

        valid = self.login()
        self.assertEqual(valid.status_code, 302)
        self.assertEqual(valid.location, "/")

    def test_flashes_render_as_safe_global_toasts(self):
        self.client.get("/produtos/")
        response = self.client.get("/auth/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="toast-container"', response.data)
        self.assertIn(b"data-toast-initial", response.data)
        self.assertIn(b"/static/js/components/toasts.js", response.data)

    def test_global_http_errors_are_safe_for_html_and_json(self):
        from flask import abort

        self.app.config["PROPAGATE_EXCEPTIONS"] = False

        @self.app.get("/test-forbidden")
        def forbidden():
            abort(403)

        @self.app.get("/api/test-missing")
        def missing_api():
            abort(404)

        @self.app.get("/test-server-error")
        def server_error():
            raise RuntimeError("sensitive database detail")

        not_found = self.client.get("/this-route-does-not-exist")
        self.assertEqual(not_found.status_code, 404)
        self.assertIn("Página não encontrada".encode(), not_found.data)
        self.assertNotIn(b"Traceback", not_found.data)

        forbidden_response = self.client.get("/test-forbidden")
        self.assertEqual(forbidden_response.status_code, 403)
        self.assertIn("Acesso negado".encode(), forbidden_response.data)

        json_response = self.client.get("/api/test-missing")
        self.assertEqual(json_response.status_code, 404)
        self.assertEqual(json_response.json, {
            "success": False,
            "message": "O endereço solicitado não existe ou foi movido.",
            "errors": {},
        })

        internal_error = self.client.get("/test-server-error")
        self.assertEqual(internal_error.status_code, 500)
        self.assertIn("Erro interno".encode(), internal_error.data)
        self.assertNotIn(b"sensitive database detail", internal_error.data)

    def test_login_rejects_external_next_redirect(self):
        response = self.login("https://example.org/phishing")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")

    def test_create_list_search_edit_duplicate_validation_and_soft_delete(self):
        self.login()
        created = self.create_product()
        self.assertEqual(created.status_code, 302)

        with self.app.app_context():
            product = db.session.scalar(
                select(Produto).where(Produto.codigo_barras == "123456789")
            )
            self.assertIsNotNone(product)
            self.assertEqual(product.preco_venda, Decimal("159.90"))
            self.assertTrue(product.ativo)
            movement = Movimentacao(
                produto_id=product.id,
                usuario_id=self.user_id,
                tipo="ENTRADA",
                quantidade=1,
                observacao="Movimentação histórica de teste",
            )
            db.session.add(movement)
            db.session.commit()
            product_id = product.id

        listing = self.client.get("/produtos/")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Teclado mec", listing.data)
        self.assertIn(b'id="product-search-input"', listing.data)
        self.assertIn(b'id="stock-movement-modal"', listing.data)
        self.assertIn(b"/static/js/pages/products.js", listing.data)
        self.assertIn(b'data-search="teclado mec', listing.data.lower())
        search = self.client.get("/produtos/?q=123456789")
        self.assertIn(b"Teclado mec", search.data)

        duplicate = self.create_product(nome="Outro produto")
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn("código de barras já".encode(), duplicate.data)

        invalid = self.create_product(preco_venda="-1.00")
        self.assertEqual(invalid.status_code, 200)
        self.assertIn(b"pre", invalid.data.lower())

        changed = self.client.post(
            f"/produtos/{product_id}/editar",
            data=self.product_data(nome="Teclado atualizado"),
        )
        self.assertEqual(changed.status_code, 302)
        with self.app.app_context():
            updated = db.session.get(Produto, product_id)
            self.assertEqual(updated.nome, "Teclado atualizado")
            self.assertEqual(updated.codigo_barras, "123456789")

        same_code_edit = self.client.post(
            f"/produtos/{product_id}/editar",
            data=self.product_data(
                nome="Teclado atualizado", codigo_barras="123456789"
            ),
        )
        self.assertEqual(same_code_edit.status_code, 302)
        second = self.create_product(
            nome="Mouse USB", codigo_barras="987654321"
        )
        self.assertEqual(second.status_code, 302)
        rejected_edit = self.client.post(
            f"/produtos/{product_id}/editar",
            data=self.product_data(codigo_barras="987654321"),
        )
        self.assertEqual(rejected_edit.status_code, 200)
        self.assertIn("código de barras já".encode(), rejected_edit.data)

        inactive = self.client.post(
            f"/produtos/{product_id}/status", data={"status": "todos"}
        )
        self.assertEqual(inactive.status_code, 302)
        self.assertIn("status=todos", inactive.location)
        with self.app.app_context():
            archived = db.session.get(Produto, product_id)
            self.assertFalse(archived.ativo)
            self.assertEqual(len(archived.movimentacoes), 1)
        self.assertIn(b"Teclado atualizado", self.client.get(
            "/produtos/?status=inativos"
        ).data)

        self.client.post(
            f"/produtos/{product_id}/status", data={"status": "todos"}
        )
        with self.app.app_context():
            self.assertTrue(db.session.get(Produto, product_id).ativo)

    def test_unknown_products_and_tampered_categories_are_rejected(self):
        self.login()
        self.assertEqual(self.client.get("/produtos/987654/editar").status_code, 404)
        self.assertEqual(
            self.client.post("/produtos/987654/status").status_code, 404
        )

        invalid_category = self.create_product(categoria_id="987654")
        self.assertEqual(invalid_category.status_code, 200)
        self.assertIn(b"categoria", invalid_category.data.lower())

    def test_create_user_cli_stores_only_a_password_hash(self):
        result = self.app.test_cli_runner().invoke(
            args=[
                "create-user",
                "--email",
                "novo@example.com",
                "--name",
                "Novo usuário",
            ],
            input="OutraSenha123!\nOutraSenha123!\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            user = db.session.scalar(
                select(Usuario).where(Usuario.email == "novo@example.com")
            )
            self.assertIsNotNone(user)
            self.assertNotEqual(user.senha_hash, "OutraSenha123!")
            self.assertTrue(check_password_hash(user.senha_hash, "OutraSenha123!"))

    def test_login_form_is_protected_by_csrf(self):
        csrf_config = type(
            "CsrfTestConfig",
            (TestConfig,),
            {"WTF_CSRF_ENABLED": True, "WTF_CSRF_CHECK_DEFAULT": True},
        )
        app = create_app(csrf_config)
        client = app.test_client()
        token_response = client.get("/auth/login")
        self.assertEqual(token_response.status_code, 200)
        token_match = re.search(
            rb'name="csrf_token" type="hidden" value="([^"]+)"',
            token_response.data,
        )
        self.assertIsNotNone(token_match)

        missing_token = client.post(
            "/auth/login",
            data={"email": "teste@example.com", "password": "SenhaSegura123!"},
        )
        self.assertEqual(missing_token.status_code, 400)
        missing_product_token = client.post("/produtos/novo")
        self.assertEqual(missing_product_token.status_code, 400)


if __name__ == "__main__":
    unittest.main()
