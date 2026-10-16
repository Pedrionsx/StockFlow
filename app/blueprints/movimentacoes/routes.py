from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from flask import current_app

from app.extensions import db
from app.models import Produto

movimentacoes_bp = Blueprint("movimentacoes", __name__)


@movimentacoes_bp.get("/")
@login_required
def index():
    try:
        products = db.session.scalars(
            select(Produto)
            .where(Produto.ativo.is_(True))
            .order_by(Produto.nome)
        ).all()
    except SQLAlchemyError:
        current_app.logger.exception("Falha ao carregar a tela de movimentações")
        return render_template("pages/module_placeholder.html",
            title="Movimentações",
            description="Não foi possível carregar o estoque. Tente novamente.",
            icon="activity",
        ), 503

    return render_template("movements/index.html", products=products)
