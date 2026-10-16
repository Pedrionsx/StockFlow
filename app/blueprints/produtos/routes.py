from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.blueprints.produtos.forms import ProdutoForm
from app.extensions import db, login_manager
from app.models import Categoria, Produto

produtos_bp = Blueprint("produtos", __name__)


@produtos_bp.before_request
def require_login():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()


def _prepare_form(form):
    statement = select(Categoria).where(Categoria.ativo.is_(True))
    if form.product_id is not None:
        product_category_id = db.session.scalar(
            select(Produto.categoria_id).where(Produto.id == form.product_id)
        )
        if product_category_id is not None:
            statement = select(Categoria).where(
                (Categoria.ativo.is_(True))
                | (Categoria.id == product_category_id)
            )
    categories = db.session.scalars(statement.order_by(Categoria.nome)).all()
    form.categoria_id.choices = [(0, "Selecione uma categoria")] + [
        (category.id, category.nome) for category in categories
    ]
    return categories


def _render_form(form, title, product=None, status=200):
    try:
        categories = _prepare_form(form)
    except SQLAlchemyError:
        current_app.logger.exception("Falha ao carregar categorias do formulário")
        flash("Não foi possível carregar as categorias. Tente novamente.", "error")
        return render_template(
            "products/form.html", form=form, title=title, product=product
        ), 503

    if not categories:
        flash("Cadastre uma categoria antes de criar produtos.", "warning")

    return render_template(
        "products/form.html", form=form, title=title, product=product
    ), status


@produtos_bp.get("/")
def index():
    status = request.args.get("status", "ativos")
    if status not in {"ativos", "inativos", "todos"}:
        status = "ativos"
    search = request.args.get("q", "").strip()
    category_id = request.args.get("categoria_id", type=int)
    statement = select(Produto).options(joinedload(Produto.categoria))

    if status == "ativos":
        statement = statement.where(Produto.ativo.is_(True))
    elif status == "inativos":
        statement = statement.where(Produto.ativo.is_(False))
    if search or category_id is not None:
        statement = statement.join(Produto.categoria)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                Produto.nome.ilike(pattern),
                Produto.codigo_barras.ilike(pattern),
                Categoria.nome.ilike(pattern),
            )
        )
    if category_id is not None:
        statement = statement.where(Produto.categoria_id == category_id)

    try:
        products = db.session.scalars(
            statement.order_by(Produto.nome)
        ).unique().all()
        counts = {
            "ativos": db.session.scalar(
                select(func.count()).select_from(Produto).where(Produto.ativo.is_(True))
            ),
            "inativos": db.session.scalar(
                select(func.count()).select_from(Produto).where(Produto.ativo.is_(False))
            ),
        }
    except SQLAlchemyError:
        current_app.logger.exception("Falha ao consultar a lista de produtos")
        flash("Não foi possível carregar os produtos. Tente novamente.", "error")
        return render_template(
            "products/index.html",
            products=[],
            status=status,
            search=search,
            category_id=category_id,
            counts={"ativos": 0, "inativos": 0},
        ), 503

    return render_template(
        "products/index.html",
        products=products,
        status=status,
        search=search,
        category_id=category_id,
        counts=counts,
    )


@produtos_bp.route("/novo", methods=["GET", "POST"])
def create():
    form = ProdutoForm()
    try:
        _prepare_form(form)
        if form.validate_on_submit():
            product = Produto(
                nome=form.nome.data.strip(),
                codigo_barras=form.codigo_barras.data.strip(),
                categoria_id=form.categoria_id.data,
                preco_custo=form.preco_custo.data,
                preco_venda=form.preco_venda.data,
                quantidade=form.quantidade.data,
                estoque_minimo=form.estoque_minimo.data,
            )
            db.session.add(product)
            db.session.commit()
            flash("Produto cadastrado com sucesso.", "success")
            return redirect(url_for("produtos.index"))
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning("Conflito de integridade ao cadastrar produto")
        flash(
            "Não foi possível cadastrar o produto. Verifique se o código de barras já está em uso.",
            "error",
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao cadastrar produto")
        flash("Não foi possível salvar o produto. Tente novamente.", "error")
        return _render_form(form, "Novo produto", status=503)

    return _render_form(form, "Novo produto")


@produtos_bp.route("/<int:product_id>/editar", methods=["GET", "POST"])
def edit(product_id):
    product = db.session.get(Produto, product_id)
    if product is None:
        abort(404)

    form = ProdutoForm(product_id=product.id, obj=product)
    if request.method == "GET":
        form.categoria_id.data = product.categoria_id

    try:
        _prepare_form(form)
        if form.validate_on_submit():
            product.nome = form.nome.data.strip()
            product.codigo_barras = form.codigo_barras.data.strip()
            product.categoria_id = form.categoria_id.data
            product.preco_custo = form.preco_custo.data
            product.preco_venda = form.preco_venda.data
            product.quantidade = form.quantidade.data
            product.estoque_minimo = form.estoque_minimo.data
            db.session.commit()
            flash("Produto atualizado com sucesso.", "success")
            return redirect(url_for("produtos.index", status="todos"))
    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning("Conflito de integridade ao atualizar produto %s", product_id)
        flash(
            "Não foi possível atualizar o produto. Verifique se o código de barras já está em uso.",
            "error",
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao atualizar produto %s", product_id)
        flash("Não foi possível salvar as alterações. Tente novamente.", "error")
        return _render_form(form, "Editar produto", product=product, status=503)

    return _render_form(form, "Editar produto", product=product)


@produtos_bp.post("/<int:product_id>/status")
def toggle_status(product_id):
    product = db.session.get(Produto, product_id)
    if product is None:
        abort(404)

    product.ativo = not product.ativo
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao alterar status do produto %s", product_id)
        flash("Não foi possível alterar o status do produto.", "error")
    else:
        action = "ativado" if product.ativo else "inativado"
        flash(f"Produto {action} com sucesso.", "success")

    return redirect(url_for("produtos.index", status=request.form.get("status", "ativos")))
