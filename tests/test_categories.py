import unittest

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Categoria, Produto, Usuario


class TestConfig:
    SECRET_KEY = "test-secret-key"
    TESTING = True
    DATABASE_URL = "sqlite://"
    APP_ENV = "testing"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False


class CategoriesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=["db", "upgrade"])
        self.assertEqual(result.exit_code, 0, result.output)
        with self.app.app_context():
            user = Usuario(
                nome="Usuário de teste",
                email="categorias@example.com",
                senha_hash=generate_password_hash("Senha123!"),
            )
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def login(self):
        response = self.client.post(
            "/auth/login",
            data={"email": "categorias@example.com", "password": "Senha123!"},
        )
        self.assertEqual(response.status_code, 302)

    def create_category(self, nome="Escritório", **fields):
        data = {
            "nome": nome,
            "descricao": fields.get("descricao", ""),
            "ativo": fields.get("ativo", "true"),
            "submit": "Salvar categoria",
        }
        return self.client.post("/categorias/nova", data=data)

    def test_category_pages_require_authentication(self):
        response = self.client.get("/categorias/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

    def test_create_search_sort_filter_and_category_product_count(self):
        self.login()
        created = self.create_category(descricao="Materiais e itens de escritório")
        self.assertEqual(created.status_code, 302)
        self.create_category("Eletrônicos")

        with self.app.app_context():
            category = db.session.scalar(
                select(Categoria).where(Categoria.nome == "Escritório")
            )
            product = Produto(
                codigo_barras="category-product-1",
                nome="Caneta azul",
                categoria_id=category.id,
                quantidade=4,
                preco_custo="1.00",
                preco_venda="2.00",
                estoque_minimo=1,
            )
            db.session.add(product)
            db.session.commit()
            category_id = category.id

        listing = self.client.get("/categorias/")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b"Categorias ativas", listing.data)
        self.assertIn(b"Produtos categorizados", listing.data)
        self.assertIn(b"Sem categoria", listing.data)
        self.assertIn(b"1</a>", listing.data)
        self.assertIn(f"/produtos/?status=todos&amp;categoria_id={category_id}".encode(), listing.data)

        searched = self.client.get("/categorias/?q=Materiais")
        self.assertEqual(searched.status_code, 200)
        self.assertIn(b"Escrit", searched.data)
        self.assertNotIn(b"Eletr", searched.data)

        sorted_by_products = self.client.get(
            "/categorias/?status=todas&sort=produtos&direction=desc"
        )
        self.assertEqual(sorted_by_products.status_code, 200)
        self.assertLess(
            sorted_by_products.data.index(b"Escrit"),
            sorted_by_products.data.index(b"Eletr"),
        )

    def test_duplicate_names_are_rejected_case_insensitively_and_updates_preserve_products(self):
        self.login()
        self.create_category("Alimentos")
        duplicate = self.create_category("  alimentos  ")
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn("já está cadastrada".encode(), duplicate.data)

        with self.app.app_context():
            category = db.session.scalar(
                select(Categoria).where(Categoria.nome == "Alimentos")
            )
            product = Produto(
                codigo_barras="category-product-2",
                nome="Arroz",
                categoria=category,
                quantidade=10,
                preco_custo="10.00",
                preco_venda="15.00",
                estoque_minimo=2,
            )
            db.session.add(product)
            db.session.commit()
            category_id = category.id
            product_id = product.id

        edited = self.client.post(
            f"/categorias/{category_id}/editar",
            data={
                "nome": "Mercearia",
                "descricao": "Produtos alimentícios",
                "ativo": "false",
                "submit": "Salvar categoria",
            },
        )
        self.assertEqual(edited.status_code, 302)
        with self.app.app_context():
            category = db.session.get(Categoria, category_id)
            product = db.session.get(Produto, product_id)
            self.assertEqual(category.nome, "Mercearia")
            self.assertFalse(category.ativo)
            self.assertEqual(product.categoria_id, category_id)

        new_product = self.client.get("/produtos/novo")
        self.assertEqual(new_product.status_code, 200)
        self.assertNotIn(b"Mercearia", new_product.data)
        rejected_assignment = self.client.post(
            "/produtos/novo",
            data={
                "nome": "Novo produto",
                "codigo_barras": "category-product-5",
                "categoria_id": str(category_id),
                "preco_custo": "2.00",
                "preco_venda": "3.00",
                "quantidade": "1",
                "estoque_minimo": "0",
                "submit": "Salvar produto",
            },
        )
        self.assertEqual(rejected_assignment.status_code, 200)
        self.assertIn("categoria inativa".encode(), rejected_assignment.data)
        edit_product = self.client.get(f"/produtos/{product_id}/editar")
        self.assertEqual(edit_product.status_code, 200)
        self.assertIn(b"Mercearia", edit_product.data)

    def test_category_deletion_is_rejected_when_products_exist_and_allowed_when_empty(self):
        self.login()
        self.create_category("Com produtos")
        self.create_category("Vazia")
        with self.app.app_context():
            categories = {
                category.nome: category.id
                for category in db.session.scalars(select(Categoria)).all()
            }
            db.session.add(
                Produto(
                    codigo_barras="category-product-3",
                    nome="Caderno",
                    categoria_id=categories["Com produtos"],
                    quantidade=1,
                    preco_custo="5.00",
                    preco_venda="8.00",
                    estoque_minimo=0,
                )
            )
            db.session.commit()

        blocked = self.client.post(f"/categorias/{categories['Com produtos']}/excluir")
        self.assertEqual(blocked.status_code, 302)
        self.assertIn(b"possui produtos", self.client.get(blocked.location).data)
        deleted = self.client.post(f"/categorias/{categories['Vazia']}/excluir")
        self.assertEqual(deleted.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Categoria, categories["Vazia"]))
            self.assertIsNotNone(db.session.get(Categoria, categories["Com produtos"]))

    def test_product_listing_can_be_filtered_by_category(self):
        self.login()
        self.create_category("Informática")
        with self.app.app_context():
            category = db.session.scalar(
                select(Categoria).where(Categoria.nome == "Informática")
            )
            db.session.add(
                Produto(
                    codigo_barras="category-product-4",
                    nome="Mouse",
                    categoria=category,
                    quantidade=3,
                    preco_custo="8.00",
                    preco_venda="12.00",
                    estoque_minimo=1,
                )
            )
            db.session.commit()
            category_id = category.id

        response = self.client.get(f"/produtos/?categoria_id={category_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mouse", response.data)
        self.assertIn(b"Categoria filtrada", response.data)
        self.assertIn(b"Inform", response.data)


if __name__ == "__main__":
    unittest.main()
