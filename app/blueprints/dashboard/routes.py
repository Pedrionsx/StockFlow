from flask import Blueprint, current_app, flash, render_template
from flask_login import login_required
from sqlalchemy.exc import SQLAlchemyError

from app.services.dashboard_service import get_dashboard_data

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.app_template_filter("brl")
def format_brl(value):
    amount = f"{value:,.2f}"
    return f"R$ {amount.replace(',', 'X').replace('.', ',').replace('X', '.')}"


@dashboard_bp.get("/dashboard")
@dashboard_bp.get("/")
@login_required
def index():
    try:
        dashboard = get_dashboard_data()
    except (SQLAlchemyError, RuntimeError):
        current_app.logger.exception("Falha ao carregar os indicadores do dashboard")
        flash("Não foi possível carregar os indicadores do estoque.", "error")
        return render_template(
            "dashboard/index.html",
            dashboard=None,
            dashboard_error=True,
        ), 503

    return render_template(
        "dashboard/index.html",
        dashboard=dashboard,
        dashboard_error=False,
    )
