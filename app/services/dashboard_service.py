from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Movimentacao, Produto


def get_dashboard_data(now=None):
    """Return stock metrics and recent activity using database-side aggregates."""
    timezone_name = current_app.config.get("APP_TIMEZONE", "America/Sao_Paulo")
    local_timezone = ZoneInfo(timezone_name)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    local_now = current_time.astimezone(local_timezone)

    local_day_start = datetime.combine(local_now.date(), time.min, tzinfo=local_timezone)
    local_next_day = local_day_start + timedelta(days=1)
    start_utc = local_day_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_next_day.astimezone(timezone.utc).replace(tzinfo=None)

    low_stock_case = case(
        (Produto.quantidade <= Produto.estoque_minimo, 1),
        else_=0,
    )
    metrics_statement = select(
        func.coalesce(
            func.sum(Produto.preco_custo * Produto.quantidade),
            Decimal("0.00"),
        ).label("valor_total_estoque"),
        func.count(Produto.id).label("total_produtos"),
        func.coalesce(func.sum(low_stock_case), 0).label(
            "produtos_estoque_baixo"
        ),
    ).where(Produto.ativo.is_(True))
    movements_today_statement = select(func.count(Movimentacao.id)).where(
        Movimentacao.data >= start_utc,
        Movimentacao.data < end_utc,
    )
    low_stock_products_statement = (
        select(Produto)
        .where(
            Produto.ativo.is_(True),
            Produto.quantidade <= Produto.estoque_minimo,
        )
        .order_by(Produto.quantidade.asc(), Produto.nome.asc())
        .limit(8)
    )
    recent_movements_statement = (
        select(Movimentacao)
        .options(
            joinedload(Movimentacao.produto),
            joinedload(Movimentacao.usuario),
        )
        .order_by(Movimentacao.data.desc(), Movimentacao.id.desc())
        .limit(5)
    )

    try:
        metrics = db.session.execute(metrics_statement).one()
        movements_today = db.session.scalar(movements_today_statement)
        low_stock_products = db.session.scalars(
            low_stock_products_statement
        ).all()
        recent_movements = db.session.scalars(recent_movements_statement).unique().all()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    recent_movement_rows = [
        {
            "produto": movement.produto.nome,
            "codigo_barras": movement.produto.codigo_barras,
            "tipo": movement.tipo,
            "quantidade": movement.quantidade,
            "data": (
                movement.data.replace(tzinfo=timezone.utc)
                if movement.data.tzinfo is None
                else movement.data
            ).astimezone(local_timezone),
            "usuario": movement.usuario.nome,
        }
        for movement in recent_movements
    ]

    return {
        "valor_total_estoque": metrics.valor_total_estoque or Decimal("0.00"),
        "total_produtos": metrics.total_produtos or 0,
        "produtos_estoque_baixo": metrics.produtos_estoque_baixo or 0,
        "movimentacoes_do_dia": movements_today or 0,
        "produtos_com_estoque_baixo": low_stock_products,
        "mais_produtos_estoque_baixo": (
            metrics.produtos_estoque_baixo or 0
        ) > len(low_stock_products),
        "movimentacoes_recentes": recent_movement_rows,
        "data_referencia": local_now.date(),
    }
