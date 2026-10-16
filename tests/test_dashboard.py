import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Categoria, Movimentacao, Produto, Usuario
from app.services.dashboard_service import get_dashboard_data


class TestConfig:
    SECRET_KEY = "test-secret-key"
    TESTING = True
    DATABASE_URL = "sqlite://"
    APP_ENV = "testing"
    APP_TIMEZONE = "America/Sao_Paulo"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False


class DashboardTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=["db", "upgrade"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            self.user = Usuario(
                nome="Usuário de teste",
                email="dashboard@example.com",
                senha_hash=generate_password_hash("Senha123!"),
            )
            self.category = Categoria(nome="Eletrônicos")
            db.session.add_all([self.user, self.category])
            db.session.commit()
            self.user_id = self.user.id
            self.category_id = self.category.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def add_product(
        self,
        barcode,
        name,
        quantity,
        minimum,
        cost,
        active=True,
    ):
        product = Produto(
            codigo_barras=barcode,
            nome=name,
            quantidade=quantity,
            estoque_minimo=minimum,
            preco_custo=cost,
            preco_venda=Decimal(cost) * Decimal("1.5"),
            categoria_id=self.category_id,
            ativo=active,
        )
        db.session.add(product)
        db.session.flush()
        return product

    def add_movement(self, product, when, kind="ENTRADA", quantity=1):
        movement = Movimentacao(
            produto=product,
            usuario_id=self.user_id,
            tipo=kind,
            quantidade=quantity,
            data=when,
        )
        db.session.add(movement)
        return movement

    def test_empty_database_returns_zero_metrics_and_empty_lists(self):
        with self.app.app_context():
            result = get_dashboard_data(
                now=datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
            )
        self.assertEqual(result["valor_total_estoque"], Decimal("0.00"))
        self.assertEqual(result["total_produtos"], 0)
        self.assertEqual(result["produtos_estoque_baixo"], 0)
        self.assertEqual(result["movimentacoes_do_dia"], 0)
        self.assertEqual(result["produtos_com_estoque_baixo"], [])
        self.assertEqual(result["movimentacoes_recentes"], [])

    def test_metrics_count_only_active_products_and_use_cost_value(self):
        with self.app.app_context():
            self.add_product("A-001", "Produto acima do mínimo", 5, 2, "10.25")
            self.add_product("A-002", "Produto no mínimo", 2, 2, "4.50")
            self.add_product("A-003", "Produto esgotado", 0, 1, "99.00")
            self.add_product("A-004", "Produto inativo", 1, 10, "100.00", False)
            db.session.commit()

            result = get_dashboard_data(
                now=datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
            )

        self.assertEqual(result["valor_total_estoque"], Decimal("60.25"))
        self.assertEqual(result["total_produtos"], 3)
        self.assertEqual(result["produtos_estoque_baixo"], 2)
        self.assertEqual(
            [product.nome for product in result["produtos_com_estoque_baixo"]],
            ["Produto esgotado", "Produto no mínimo"],
        )

    def test_movements_are_counted_in_sao_paulo_calendar_day(self):
        with self.app.app_context():
            product = self.add_product("A-010", "Produto diário", 10, 1, "10.00")
            local_zone = ZoneInfo("America/Sao_Paulo")
            now = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
            local_now = now.astimezone(local_zone)
            local_start = datetime.combine(
                local_now.date(), datetime.min.time(), tzinfo=local_zone
            )
            start_utc = local_start.astimezone(timezone.utc)
            end_utc = (local_start + timedelta(days=1)).astimezone(timezone.utc)

            self.add_movement(product, start_utc)
            self.add_movement(product, end_utc - timedelta(microseconds=1), "SAIDA")
            self.add_movement(product, start_utc - timedelta(microseconds=1))
            self.add_movement(product, end_utc)
            db.session.commit()

            result = get_dashboard_data(now=now)

        self.assertEqual(result["movimentacoes_do_dia"], 2)
        self.assertEqual(len(result["movimentacoes_recentes"]), 4)

    def test_dashboard_is_private_and_renders_database_indicators(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.add_product("A-020", "Produto do painel", 2, 3, "12.34")
            db.session.commit()

        login = self.client.post(
            "/auth/login",
            data={"email": "dashboard@example.com", "password": "Senha123!"},
        )
        self.assertEqual(login.status_code, 302)

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("R$ 24,68".encode(), response.data)
        self.assertIn("Produto do painel".encode(), response.data)
        self.assertIn("Estoque baixo".encode(), response.data)
        self.assertNotIn("Café especial".encode(), response.data)

    def test_dashboard_shows_empty_alert_and_zero_activity(self):
        with self.app.app_context():
            self.add_product("A-030", "Produto saudável", 10, 2, "1.00")
            db.session.commit()
        self.client.post(
            "/auth/login",
            data={"email": "dashboard@example.com", "password": "Senha123!"},
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Estoque em dia".encode(), response.data)
        self.assertIn("Ainda não há movimentações registradas".encode(), response.data)
        self.assertIn(">0<".encode(), response.data)

    def test_dashboard_displays_explicit_error_when_database_query_fails(self):
        self.client.post(
            "/auth/login",
            data={"email": "dashboard@example.com", "password": "Senha123!"},
        )
        with patch(
            "app.blueprints.dashboard.routes.get_dashboard_data",
            side_effect=SQLAlchemyError("internal database details"),
        ):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Indicadores indisponíveis".encode(), response.data)
        self.assertNotIn("internal database details".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
