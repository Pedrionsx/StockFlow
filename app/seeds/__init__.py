import click
from flask import current_app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import Categoria, Movimentacao, Produto, Usuario


def seed_demo_data(password):
    categories = (
        "Eletrônicos",
        "Periféricos",
        "Escritório",
        "Acessórios",
        "Armazenamento",
    )
    users = (
        ("admin.demo@stockflow.invalid", "Administrador Demo"),
        ("funcionario.demo@stockflow.invalid", "Funcionário Demo"),
    )
    products = (
        ("7891000000001", "Notebook demonstrativo", "Eletrônicos", 8, "2800.00", "3499.90", 2),
        ("7891000000002", "Monitor demonstrativo 24 pol.", "Eletrônicos", 5, "620.00", "899.90", 2),
        ("7891000000003", "Teclado USB demonstrativo", "Periféricos", 0, "45.00", "89.90", 3),
        ("7891000000004", "Mouse sem fio demonstrativo", "Periféricos", 3, "38.00", "74.90", 5),
        ("7891000000005", "Cadeira de escritório demonstrativa", "Escritório", 6, "390.00", "599.90", 2),
        ("7891000000006", "Caderno demonstrativo", "Escritório", 24, "8.00", "16.90", 8),
        ("7891000000007", "Hub USB demonstrativo", "Acessórios", 2, "52.00", "99.90", 4),
        ("7891000000008", "Webcam demonstrativa", "Periféricos", 7, "115.00", "189.90", 2),
        ("7891000000009", "SSD demonstrativo 1 TB", "Armazenamento", 4, "280.00", "429.90", 2),
        ("7891000000010", "Pen drive demonstrativo 64 GB", "Armazenamento", 0, "24.00", "49.90", 5),
    )
    movement_specs = (
        ("7891000000001", "ENTRADA", 8, "Carga inicial demonstrativa", "admin.demo@stockflow.invalid"),
        ("7891000000002", "ENTRADA", 5, "Carga inicial demonstrativa", "admin.demo@stockflow.invalid"),
        ("7891000000003", "SAIDA", 3, "Saída demonstrativa", "funcionario.demo@stockflow.invalid"),
        ("7891000000004", "ENTRADA", 3, "Reposição demonstrativa", "admin.demo@stockflow.invalid"),
        ("7891000000005", "ENTRADA", 6, "Carga inicial demonstrativa", "admin.demo@stockflow.invalid"),
        ("7891000000006", "SAIDA", 4, "Saída demonstrativa", "funcionario.demo@stockflow.invalid"),
        ("7891000000007", "SAIDA", 2, "Saída demonstrativa", "funcionario.demo@stockflow.invalid"),
        ("7891000000008", "ENTRADA", 7, "Carga inicial demonstrativa", "admin.demo@stockflow.invalid"),
        ("7891000000009", "ENTRADA", 4, "Carga inicial demonstrativa", "admin.demo@stockflow.invalid"),
        ("7891000000010", "SAIDA", 2, "Saída demonstrativa", "funcionario.demo@stockflow.invalid"),
    )

    try:
        with db.session.begin():
            category_by_name = {}
            for name in categories:
                category = db.session.scalar(
                    select(Categoria).where(Categoria.nome == name)
                )
                if category is None:
                    category = Categoria(nome=name)
                    db.session.add(category)
                category_by_name[name] = category

            password_hash = generate_password_hash(password)
            user_by_email = {}
            for email, name in users:
                user = db.session.scalar(select(Usuario).where(Usuario.email == email))
                if user is None:
                    user = Usuario(nome=name, email=email, senha_hash=password_hash)
                    db.session.add(user)
                user_by_email[email] = user

            db.session.flush()

            product_by_barcode = {}
            for barcode, name, category_name, quantity, cost, price, minimum in products:
                product = db.session.scalar(
                    select(Produto).where(Produto.codigo_barras == barcode)
                )
                if product is None:
                    product = Produto(
                        codigo_barras=barcode,
                        nome=name,
                        categoria=category_by_name[category_name],
                        quantidade=quantity,
                        preco_custo=cost,
                        preco_venda=price,
                        estoque_minimo=minimum,
                    )
                    db.session.add(product)
                product_by_barcode[barcode] = product

            db.session.flush()

            for barcode, kind, quantity, note, user_email in movement_specs:
                observation = f"Seed demo: {barcode} - {note}"
                movement = db.session.scalar(
                    select(Movimentacao).where(
                        Movimentacao.observacao == observation,
                        Movimentacao.produto_id == product_by_barcode[barcode].id,
                    )
                )
                if movement is None:
                    db.session.add(
                        Movimentacao(
                            produto=product_by_barcode[barcode],
                            tipo=kind,
                            quantidade=quantity,
                            observacao=observation,
                            usuario=user_by_email[user_email],
                        )
                    )
    except SQLAlchemyError as error:
        db.session.rollback()
        raise click.ClickException(
            f"Seed cancelado; nenhuma alteração parcial foi mantida: {error}"
        ) from error


def register_commands(app):
    @app.cli.command("seed-demo")
    def seed_demo():
        """Insere dados fictícios de demonstração, somente em desenvolvimento."""
        if current_app.config.get("APP_ENV") != "development":
            raise click.ClickException(
                "O seed de demonstração só pode ser executado com APP_ENV=development."
            )
        if not current_app.config.get("DATABASE_URL"):
            raise click.ClickException(
                "DATABASE_URL está vazia. Configure a conexão antes de executar o seed."
            )

        password = click.prompt(
            "Senha inicial das contas demonstrativas",
            hide_input=True,
            confirmation_prompt=True,
        )
        if not password:
            raise click.ClickException("A senha das contas demonstrativas não pode ser vazia.")

        seed_demo_data(password)
        click.echo("Dados demonstrativos inseridos ou já existentes.")
