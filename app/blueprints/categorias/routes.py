from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, login_manager
from app.blueprints.categorias.forms import CategoriaForm
from app.models import Categoria
from app.services.categoria_service import (
    CategoryHasProductsError,
    DuplicateCategoryError,
    create_category,
    delete_category,
    get_category_counts,
    list_categories,
    set_category_active,
    update_category,
)

categorias_bp = Blueprint("categorias", __name__)


@categorias_bp.before_request
def require_login():
    if not current_user.is_authenticated:
        return login_manager.unauthorized()


@categorias_bp.get("/")
def index():
    status = request.args.get("status", "ativas")
    if status not in {"ativas", "inativas", "todas"}:
        status = "ativas"
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "nome")
    if sort not in {"nome", "produtos"}:
        sort = "nome"
    direction = request.args.get("direction", "asc").lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"

    try:
        categories = list_categories(search, status, sort, direction)
        counts = get_category_counts()
    except SQLAlchemyError:
        current_app.logger.exception("Falha ao consultar categorias")
        flash("Não foi possível carregar as categorias. Tente novamente.", "error")
        categories = []
        counts = {
            "ativas": 0,
            "inativas": 0,
            "total": 0,
            "categorizados": 0,
            "sem_categoria": 0,
        }
        return render_template(
            "categories/index.html",
            categories=categories,
            counts=counts,
            status=status,
            search=search,
            sort=sort,
            direction=direction,
            database_error=True,
        ), 503

    return render_template(
        "categories/index.html",
        categories=categories,
        counts=counts,
        status=status,
        search=search,
        sort=sort,
        direction=direction,
        database_error=False,
    )


@categorias_bp.route("/nova", methods=["GET", "POST"])
def create():
    form = CategoriaForm()
    if form.validate_on_submit():
        try:
            create_category(form.nome.data, form.descricao.data, form.ativo.data == "true")
        except DuplicateCategoryError as error:
            form.nome.errors.append(str(error))
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao cadastrar categoria")
            flash("Não foi possível salvar a categoria. Tente novamente.", "error")
            return render_template("categories/form.html", form=form, title="Nova categoria"), 503
        else:
            flash("Categoria cadastrada com sucesso.", "success")
            return redirect(url_for("categorias.index"))
    return render_template("categories/form.html", form=form, title="Nova categoria")


@categorias_bp.route("/<int:category_id>/editar", methods=["GET", "POST"])
def edit(category_id):
    category = db_get_category(category_id)
    form = CategoriaForm(obj=category)
    if request.method == "GET":
        form.ativo.data = "true" if category.ativo else "false"
    if form.validate_on_submit():
        try:
            update_category(category, form.nome.data, form.descricao.data, form.ativo.data == "true")
        except DuplicateCategoryError as error:
            form.nome.errors.append(str(error))
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao atualizar categoria %s", category_id)
            flash("Não foi possível salvar as alterações. Tente novamente.", "error")
            return render_template("categories/form.html", form=form, title="Editar categoria"), 503
        else:
            flash("Categoria atualizada com sucesso.", "success")
            return redirect(url_for("categorias.index", status="todas"))
    return render_template("categories/form.html", form=form, title="Editar categoria")


@categorias_bp.post("/<int:category_id>/status")
def toggle_status(category_id):
    category = db_get_category(category_id)
    try:
        set_category_active(category, not category.ativo)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao alterar status da categoria %s", category_id)
        flash("Não foi possível alterar o status da categoria.", "error")
    else:
        flash(
            f"Categoria {'ativada' if category.ativo else 'desativada'} com sucesso.",
            "success",
        )
    return redirect(url_for("categorias.index", status=request.form.get("status", "todas")))


@categorias_bp.post("/<int:category_id>/excluir")
def delete(category_id):
    category = db_get_category(category_id)
    try:
        delete_category(category)
    except CategoryHasProductsError as error:
        flash(str(error), "warning")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao excluir categoria %s", category_id)
        flash("Não foi possível excluir a categoria. Tente novamente.", "error")
    else:
        flash("Categoria excluída com sucesso.", "success")
    return redirect(url_for("categorias.index", status=request.form.get("status", "todas")))


def db_get_category(category_id):
    category = db.session.get(Categoria, category_id)
    if category is None:
        abort(404)
    return category
