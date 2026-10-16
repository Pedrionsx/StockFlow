from datetime import datetime
import re
import unittest

from sqlalchemy import event, select
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Categoria, Movimentacao, Produto, Usuario
from app.services.dashboard_service import get_dashboard_data
from app.services.movimentacao_service import (
    InsufficientStockError,
    InactiveProductError,
    MovementError,
    MovementPersistenceError,
    ProductNotFoundError,
    register_movement,
)


class TestConfig:
    SECRET_KEY = "test-secret-key"
    TESTING = True
    DATABASE_URL = "sqlite://"
    APP_ENV = "testing"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False


class MovimentacoesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=["db", "upgrade"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.user = Usuario(
                nome="Usuário de teste",
                email="teste@example.com",
                senha_hash=generate_password_hash("Senha123!"),
            )
            self.category = Categoria(nome="Eletrônicos")
            db.session.add_all([self.user, self.category])
            db.session.flush()
            self.product = Produto(
                codigo_barras="111222333",
                nome="Produto de teste",
                categoria=self.category,
                quantidade=5,
                preco_custo="10.00",
                preco_venda="20.00",
                estoque_minimo=1,
            )
            db.session.add(self.product)
            db.session.commit()
            self.user_id = self.user.id
            self.product_id = self.product.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def login(self):
        response = self.client.post(
            "/auth/login",
            data={"email": "teste@example.com", "password": "Senha123!"},
        )
        self.assertEqual(response.status_code, 302)

    def test_entry_updates_stock_and_creates_one_history_record(self):
        with self.app.app_context():
            movement = register_movement(
                self.product_id, self.user_id, "ENTRADA", 10, "Reposição"
            )
            product = db.session.get(Produto, self.product_id)
            self.assertEqual(product.quantidade, 15)
            self.assertEqual(movement.tipo, "ENTRADA")
            self.assertEqual(movement.quantidade, 10)
            self.assertEqual(
                db.session.scalar(
                    select(db.func.count())
                    .select_from(Movimentacao)
                    .where(Movimentacao.produto_id == self.product_id)
                ),
                1,
            )

    def test_exit_updates_stock_and_equal_available_balance_is_allowed(self):
        with self.app.app_context():
            register_movement(self.product_id, self.user_id, "SAIDA", 5)
            product = db.session.get(Produto, self.product_id)
            self.assertEqual(product.quantidade, 0)
            movement = db.session.scalar(select(Movimentacao))
            self.assertEqual(movement.tipo, "SAIDA")

    def test_invalid_quantities_and_missing_or_inactive_products_are_rejected(self):
        with self.app.app_context():
            for quantity in (0, -1, True, 1.5, "2"):
                with self.subTest(quantity=quantity):
                    with self.assertRaises(MovementError):
                        register_movement(
                            self.product_id, self.user_id, "ENTRADA", quantity
                        )
            with self.assertRaises(ProductNotFoundError):
                register_movement(99999, self.user_id, "ENTRADA", 1)
            product = db.session.get(Produto, self.product_id)
            product.ativo = False
            db.session.commit()
            with self.assertRaises(InactiveProductError):
                register_movement(self.product_id, self.user_id, "ENTRADA", 1)
            self.assertEqual(db.session.scalar(select(Movimentacao)), None)

    def test_insufficient_stock_does_not_change_balance_or_create_history(self):
        with self.app.app_context():
            with self.assertRaises(InsufficientStockError):
                register_movement(self.product_id, self.user_id, "SAIDA", 6)
            product = db.session.get(Produto, self.product_id)
            self.assertEqual(product.quantidade, 5)
            self.assertEqual(db.session.scalar(select(Movimentacao)), None)

    def test_history_insert_failure_rolls_back_stock_update(self):
        with self.app.app_context():
            def reject_history(mapper, connection, movement):
                raise IntegrityError("simulated insert failure", {}, RuntimeError("test"))

            event.listen(Movimentacao, "before_insert", reject_history)
            try:
                with self.assertRaises(MovementPersistenceError):
                    register_movement(
                        self.product_id, self.user_id, "ENTRADA", 3
                    )
            finally:
                event.remove(Movimentacao, "before_insert", reject_history)
            product = db.session.get(Produto, self.product_id)
            self.assertEqual(product.quantidade, 5)
            self.assertEqual(db.session.scalar(select(Movimentacao)), None)

    def test_mysql_product_lookup_uses_row_lock(self):
        statement = (
            select(Produto)
            .where(Produto.id == self.product_id)
            .with_for_update()
        )
        sql = str(statement.compile(dialect=mysql.dialect()))
        self.assertIn("FOR UPDATE", sql)

    def test_api_requires_authentication_and_valid_json_and_returns_history(self):
        unauthorized = self.client.get("/api/produtos")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertFalse(unauthorized.json["success"])
        self.assertEqual(unauthorized.json["errors"], {})

        self.login()
        screen = self.client.get("/movimentacoes/")
        self.assertEqual(screen.status_code, 200)
        self.assertIn(b"/static/js/pages/movements.js", screen.data)
        self.assertIn(b'name="csrf-token"', screen.data)
        products = self.client.get("/api/produtos")
        self.assertEqual(products.status_code, 200)
        self.assertEqual(products.json["data"][0]["estoque_atual"], 5)
        self.assertEqual(products.json["pagination"]["total"], 1)

        malformed = self.client.post(
            "/api/movimentacoes/entradas",
            data="{invalid json",
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertFalse(malformed.json["success"])

        missing = self.client.post(
            "/api/movimentacoes/entradas",
            json={"produto_id": self.product_id},
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn("quantidade", missing.json["errors"])

        invalid = self.client.post(
            "/api/movimentacoes/entradas",
            json={"produto_id": self.product_id, "quantidade": "dez"},
        )
        self.assertEqual(invalid.status_code, 422)

        absent_product = self.client.post(
            "/api/movimentacoes/entradas",
            json={"produto_id": 99999, "quantidade": 1},
        )
        self.assertEqual(absent_product.status_code, 404)

        zero_quantity = self.client.post(
            "/api/movimentacoes/entradas",
            json={"produto_id": self.product_id, "quantidade": 0},
        )
        self.assertEqual(zero_quantity.status_code, 422)

        success = self.client.post(
            "/api/movimentacoes/entradas",
            json={
                "produto_id": self.product_id,
                "quantidade": 4,
                "observacao": "Entrada pela API",
            },
        )
        self.assertEqual(success.status_code, 201)
        self.assertTrue(success.json["success"])
        self.assertEqual(success.json["data"]["estoque_atual"], 9)
        with self.app.app_context():
            dashboard = get_dashboard_data()
        self.assertEqual(dashboard["valor_total_estoque"], 90)
        self.assertEqual(dashboard["total_produtos"], 1)
        self.assertEqual(dashboard["produtos_estoque_baixo"], 0)
        self.assertEqual(dashboard["movimentacoes_do_dia"], 1)

        history = self.client.get("/api/movimentacoes")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json["data"]), 1)
        movement_id = history.json["data"][0]["id"]
        detail = self.client.get(f"/api/movimentacoes/{movement_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["data"]["produto_id"], self.product_id)
        self.assertEqual(detail.json["data"]["usuario"], "Usuário de teste")

        too_much = self.client.post(
            "/api/movimentacoes/saidas",
            json={"produto_id": self.product_id, "quantidade": 10},
        )
        self.assertEqual(too_much.status_code, 409)
        self.assertEqual(
            too_much.json["errors"]["quantidade"],
            ["A quantidade solicitada excede o estoque disponível."],
        )

        not_found = self.client.get("/api/movimentacoes/99999")
        self.assertEqual(not_found.status_code, 404)

    def test_history_paginates_sorts_and_filters(self):
        self.login()
        with self.app.app_context():
            register_movement(self.product_id, self.user_id, "ENTRADA", 2)
            register_movement(self.product_id, self.user_id, "ENTRADA", 7)
            register_movement(self.product_id, self.user_id, "SAIDA", 1)

        first_page = self.client.get(
            "/api/movimentacoes?page=1&page_size=2&sort=quantidade&direction=desc"
        )
        self.assertEqual(first_page.status_code, 200, first_page.json)
        self.assertEqual(
            [item["quantidade"] for item in first_page.json["data"]], [7, 2]
        )
        self.assertEqual(first_page.json["pagination"], {
            "page": 1,
            "page_size": 2,
            "total": 3,
            "total_pages": 2,
        })
        self.assertEqual(first_page.json["sorting"], {
            "sort": "quantidade",
            "direction": "desc",
        })
        user_sort = self.client.get(
            "/api/movimentacoes?page_size=5&sort=usuario&direction=asc"
        )
        self.assertEqual(user_sort.status_code, 200, user_sort.json)
        self.assertEqual(user_sort.json["sorting"]["sort"], "usuario")

        second_page = self.client.get(
            "/api/movimentacoes?page=2&page_size=2&sort=quantidade&direction=desc"
        )
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual([item["quantidade"] for item in second_page.json["data"]], [1])

        filtered = self.client.get(
            "/api/movimentacoes?q=produto%20de%20teste&tipo=SAIDA"
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json["pagination"]["total"], 1)
        self.assertEqual(filtered.json["filters"], {
            "data_inicio": "",
            "data_fim": "",
            "q": "produto de teste",
            "tipo": "SAIDA",
        })

    def test_history_rejects_invalid_pagination_and_sorting(self):
        self.login()
        for query in (
            "page=0",
            "page_size=101",
            "sort=senha",
            "direction=sideways",
            "tipo=ajuste",
            "data_inicio=2025-13-40",
            "data_inicio=2025-04-11&data_fim=2025-04-10",
        ):
            with self.subTest(query=query):
                response = self.client.get(f"/api/movimentacoes?{query}")
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json["success"])

        with self.app.app_context():
            register_movement(self.product_id, self.user_id, "ENTRADA", 1)
        out_of_range = self.client.get("/api/movimentacoes?page=2&page_size=1")
        self.assertEqual(out_of_range.status_code, 400)
        self.assertIn("page", out_of_range.json["errors"])

    def test_complete_stock_cycle_stays_consistent_across_api_history_and_dashboard(self):
        self.login()
        with self.app.app_context():
            product = db.session.get(Produto, self.product_id)
            product.quantidade = 0
            product.estoque_minimo = 5
            db.session.commit()

        operations = (
            ("entradas", 10, 10),
            ("entradas", 15, 25),
            ("entradas", 5, 30),
            ("saidas", 8, 22),
            ("saidas", 7, 15),
            ("saidas", 10, 5),
        )
        for endpoint, quantity, expected_stock in operations:
            response = self.client.post(
                f"/api/movimentacoes/{endpoint}",
                json={"produto_id": self.product_id, "quantidade": quantity},
            )
            self.assertEqual(response.status_code, 201, response.json)
            self.assertEqual(response.json["data"]["estoque_atual"], expected_stock)

        rejected_exit = self.client.post(
            "/api/movimentacoes/saidas",
            json={"produto_id": self.product_id, "quantidade": 6},
        )
        self.assertEqual(rejected_exit.status_code, 409)

        history_ids = []
        for page in range(1, 4):
            response = self.client.get(
                f"/api/movimentacoes?page={page}&page_size=2"
            )
            self.assertEqual(response.status_code, 200, response.json)
            history_ids.extend(item["id"] for item in response.json["data"])
            self.assertTrue(
                all(
                    item["produto"] == "Produto de teste"
                    and item["usuario"] == "Usuário de teste"
                    for item in response.json["data"]
                )
            )

        self.assertEqual(len(history_ids), 6)
        self.assertEqual(len(set(history_ids)), 6)
        with self.app.app_context():
            product = db.session.get(Produto, self.product_id)
            movement_count = db.session.scalar(
                select(db.func.count()).select_from(Movimentacao)
            )
            dashboard = get_dashboard_data()
            self.assertEqual(product.quantidade, 5)
            self.assertEqual(movement_count, 6)
            self.assertEqual(dashboard["valor_total_estoque"], 50)
            self.assertEqual(dashboard["produtos_estoque_baixo"], 1)
            self.assertEqual(dashboard["movimentacoes_do_dia"], 6)
        dashboard_page = self.client.get("/")
        self.assertEqual(dashboard_page.status_code, 200)
        self.assertIn("R$ 50,00".encode(), dashboard_page.data)

    def test_history_page_and_count_use_two_queries_without_n_plus_one_or_unused_joins(self):
        self.login()
        with self.app.app_context():
            for quantity in range(1, 13):
                register_movement(
                    self.product_id,
                    self.user_id,
                    "ENTRADA",
                    quantity,
                )

            statements = []

            def record_statement(
                connection, cursor, statement, parameters, context, executemany
            ):
                if "from movimentacoes" in statement.lower():
                    statements.append(statement.lower())

            event.listen(db.engine, "before_cursor_execute", record_statement)
            try:
                response = self.client.get(
                    "/api/movimentacoes?page_size=5&tipo=ENTRADA"
                )
            finally:
                event.remove(db.engine, "before_cursor_execute", record_statement)

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["pagination"]["total"], 12)
        self.assertEqual(len(response.json["data"]), 5)
        self.assertEqual(len(statements), 2)
        data_query, count_query = statements
        self.assertEqual(data_query.count(" join "), 2)
        self.assertNotIn("left outer join", data_query)
        self.assertNotIn(" join ", count_query)
        combined = self.client.get(
            "/api/movimentacoes?page=1&page_size=5&q=Produto%20de%20teste&tipo=ENTRADA"
        )
        self.assertEqual(combined.status_code, 200, combined.json)
        self.assertEqual(combined.json["pagination"]["total"], 12)
        self.assertEqual(len(combined.json["data"]), 5)

    def test_history_date_range_uses_local_day_and_combines_with_other_filters(self):
        self.login()
        with self.app.app_context():
            movement_ids = []
            for quantity in range(1, 5):
                movement = register_movement(
                    self.product_id, self.user_id, "ENTRADA", quantity
                )
                movement_ids.append(movement.id)
            timestamps = (
                datetime(2025, 4, 10, 2, 59, 59),
                datetime(2025, 4, 10, 3, 0, 0),
                datetime(2025, 4, 11, 2, 59, 59),
                datetime(2025, 4, 11, 3, 0, 0),
            )
            for movement_id, timestamp in zip(movement_ids, timestamps):
                movement = db.session.get(Movimentacao, movement_id)
                movement.data = timestamp
            db.session.commit()

        response = self.client.get(
            "/api/movimentacoes?page=1&page_size=1"
            "&q=Produto%20de%20teste&tipo=ENTRADA"
            "&data_inicio=2025-04-10&data_fim=2025-04-10"
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["pagination"]["total"], 2)
        self.assertEqual(response.json["pagination"]["total_pages"], 2)
        self.assertEqual(response.json["data"][0]["id"], movement_ids[2])
        self.assertEqual(
            response.json["filters"],
            {
                "q": "Produto de teste",
                "tipo": "ENTRADA",
                "data_inicio": "2025-04-10",
                "data_fim": "2025-04-10",
            },
        )

    def test_api_requires_csrf_token_when_csrf_is_enabled(self):
        csrf_config = type(
            "CsrfTestConfig",
            (TestConfig,),
            {"WTF_CSRF_ENABLED": True, "WTF_CSRF_CHECK_DEFAULT": True},
        )
        app = create_app(csrf_config)
        client = app.test_client()
        result = app.test_cli_runner().invoke(args=["db", "upgrade"])
        self.assertEqual(result.exit_code, 0, result.output)
        with app.app_context():
            user = Usuario(
                nome="Usuário CSRF",
                email="csrf@example.com",
                senha_hash=generate_password_hash("Senha123!"),
            )
            category = Categoria(nome="Categoria CSRF")
            db.session.add_all([user, category])
            db.session.flush()
            product = Produto(
                codigo_barras="csrf-123",
                nome="Produto CSRF",
                categoria=category,
                quantidade=5,
                preco_custo="1.00",
                preco_venda="2.00",
                estoque_minimo=1,
            )
            db.session.add(product)
            db.session.commit()
            user_id = user.id
            product_id = product.id
        login_page = client.get("/auth/login")
        csrf_field = re.search(
            rb'name="csrf_token" type="hidden" value="([^"]+)"', login_page.data
        )
        self.assertIsNotNone(csrf_field)
        login_response = client.post(
            "/auth/login",
            data={
                "email": "csrf@example.com",
                "password": "Senha123!",
                "csrf_token": csrf_field.group(1).decode(),
            },
        )
        self.assertEqual(login_response.status_code, 302)
        response = client.post(
            "/api/movimentacoes/entradas",
            json={"produto_id": product_id, "quantidade": 1},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["message"], "Token CSRF ausente ou inválido.")
        self.assertEqual(response.json["errors"], {})

        page = client.get("/movimentacoes/")
        self.assertEqual(page.status_code, 200)
        token = re.search(rb'<meta name="csrf-token" content="([^"]+)">', page.data)
        self.assertIsNotNone(token)
        accepted = client.post(
            "/api/movimentacoes/entradas",
            json={"produto_id": product_id, "quantidade": 1},
            headers={"X-CSRFToken": token.group(1).decode()},
        )
        self.assertEqual(accepted.status_code, 201, accepted.json)


if __name__ == "__main__":
    unittest.main()
