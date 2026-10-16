from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Categoria, Produto


class DuplicateCategoryError(ValueError):
    pass


class CategoryHasProductsError(ValueError):
    pass


def list_categories(search="", status="ativas", sort="nome", direction="asc"):
    product_count = func.count(Produto.id).label("product_count")
    statement = (
        select(Categoria, product_count)
        .outerjoin(Produto, Produto.categoria_id == Categoria.id)
        .group_by(Categoria.id)
    )

    if status == "ativas":
        statement = statement.where(Categoria.ativo.is_(True))
    elif status == "inativas":
        statement = statement.where(Categoria.ativo.is_(False))
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Categoria.nome.ilike(pattern),
                Categoria.descricao.ilike(pattern),
            )
        )

    sort_column = {
        "nome": Categoria.nome,
        "produtos": product_count,
    }[sort]
    order = sort_column.asc() if direction == "asc" else sort_column.desc()
    statement = statement.order_by(order, Categoria.nome.asc(), Categoria.id.asc())
    return db.session.execute(statement).all()


def get_category_counts():
    total = db.session.scalar(select(func.count()).select_from(Categoria)) or 0
    active = (
        db.session.scalar(
            select(func.count()).select_from(Categoria).where(Categoria.ativo.is_(True))
        )
        or 0
    )
    return {
        "ativas": active,
        "inativas": total - active,
        "total": total,
        "categorizados": db.session.scalar(
            select(func.count())
            .select_from(Produto)
            .join(Categoria, Produto.categoria_id == Categoria.id)
        )
        or 0,
        "sem_categoria": db.session.scalar(
            select(func.count())
            .select_from(Produto)
            .where(Produto.categoria_id.is_(None))
        )
        or 0,
    }


def create_category(nome, descricao=None, ativo=True):
    category = Categoria(
        nome=_normalize_name(nome),
        descricao=_normalize_description(descricao),
        ativo=bool(ativo),
    )
    _ensure_unique_name(category.nome)
    db.session.add(category)
    _commit_category(category, "Essa categoria já está cadastrada.")
    return category


def update_category(category, nome, descricao=None, ativo=True):
    normalized_name = _normalize_name(nome)
    _ensure_unique_name(normalized_name, exclude_id=category.id)
    category.nome = normalized_name
    category.descricao = _normalize_description(descricao)
    category.ativo = bool(ativo)
    _commit_category(category, "Essa categoria já está cadastrada.")
    return category


def set_category_active(category, active):
    category.ativo = bool(active)
    db.session.commit()
    return category


def delete_category(category):
    has_products = db.session.scalar(
        select(Produto.id).where(Produto.categoria_id == category.id).limit(1)
    )
    if has_products is not None:
        raise CategoryHasProductsError(
            "Esta categoria possui produtos. Reatribua-os ou desative a categoria."
        )
    db.session.delete(category)
    db.session.commit()


def _normalize_name(nome):
    normalized = (nome or "").strip()
    if not normalized:
        raise ValueError("Informe o nome da categoria.")
    return normalized


def _normalize_description(descricao):
    normalized = (descricao or "").strip()
    return normalized or None


def _ensure_unique_name(nome, exclude_id=None):
    statement = select(Categoria.id).where(
        func.lower(Categoria.nome) == nome.lower()
    )
    if exclude_id is not None:
        statement = statement.where(Categoria.id != exclude_id)
    if db.session.scalar(statement) is not None:
        raise DuplicateCategoryError("Essa categoria já está cadastrada.")


def _commit_category(category, duplicate_message):
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise DuplicateCategoryError(duplicate_message) from error
