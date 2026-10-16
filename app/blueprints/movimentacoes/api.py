from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import contains_eager, joinedload

from app.extensions import db
from app.models import Categoria, Movimentacao, Produto, Usuario
from app.services.movimentacao_service import (
    MovementError,
    MovementPersistenceError,
    register_movement,
)

api_bp = Blueprint("stock_api", __name__)


@api_bp.before_request
def require_authenticated_user():
    if not current_user.is_authenticated:
        return _error("Autenticação necessária.", 401)


@api_bp.get("/produtos")
def list_products():
    try:
        limit, offset = _pagination()
    except ValueError as error:
        return _error(str(error), 400)

    statement = (
        select(Produto)
        .join(Categoria)
        .where(Produto.ativo.is_(True))
        .options(joinedload(Produto.categoria))
        .order_by(Produto.nome)
        .limit(limit)
        .offset(offset)
    )
    try:
        products = db.session.scalars(statement).unique().all()
        total = db.session.scalar(
            select(db.func.count())
            .select_from(Produto)
            .where(Produto.ativo.is_(True))
        )
    except SQLAlchemyError:
        current_app.logger.exception("Falha da API ao consultar produtos disponíveis")
        return _error("Não foi possível consultar os produtos.", 503)

    return jsonify(
        {
            "success": True,
            "data": [
                {
                    "id": product.id,
                    "nome": product.nome,
                    "codigo_barras": product.codigo_barras,
                    "categoria": product.categoria.nome,
                    "estoque_atual": product.quantidade,
                }
                for product in products
            ],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }
    )


@api_bp.get("/movimentacoes")
def list_movements():
    try:
        page, page_size, sort, direction = _movement_query()
        date_start, date_end, start_label, end_label = _movement_date_range()
    except ValueError as error:
        return _error(str(error), 400)

    sort_columns = {
        "data": Movimentacao.data,
        "produto": Produto.nome,
        "tipo": Movimentacao.tipo,
        "quantidade": Movimentacao.quantidade,
        "usuario": Usuario.nome,
    }
    statement = select(Movimentacao).join(Movimentacao.produto).join(
        Movimentacao.usuario
    )
    filters = []
    search = request.args.get("q", "").strip()
    movement_type = request.args.get("tipo", "").upper()
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                Produto.nome.ilike(pattern),
                Produto.codigo_barras.ilike(pattern),
                Usuario.nome.ilike(pattern),
            )
        )
    if movement_type:
        if movement_type not in {"ENTRADA", "SAIDA"}:
            return _error(
                "O filtro tipo deve ser ENTRADA ou SAIDA.",
                400,
                errors={"tipo": "Filtro inválido."},
            )
        filters.append(Movimentacao.tipo == movement_type)
    if date_start is not None:
        filters.append(Movimentacao.data >= date_start)
    if date_end is not None:
        filters.append(Movimentacao.data < date_end)
    if filters:
        statement = statement.where(*filters)

    sort_column = sort_columns[sort]
    primary_order = sort_column.asc() if direction == "asc" else sort_column.desc()
    statement = (
        statement
        .options(
            contains_eager(Movimentacao.produto),
            contains_eager(Movimentacao.usuario),
        )
        .order_by(primary_order, Movimentacao.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    try:
        movements = db.session.scalars(statement).unique().all()
        count_statement = select(func.count(Movimentacao.id))
        if search:
            count_statement = count_statement.join(Movimentacao.produto).join(
                Movimentacao.usuario
            )
        if filters:
            count_statement = count_statement.where(*filters)
        total = db.session.scalar(count_statement) or 0
    except SQLAlchemyError:
        current_app.logger.exception("Falha da API ao consultar movimentações")
        return _error("Não foi possível consultar as movimentações.", 503)

    total_pages = (total + page_size - 1) // page_size
    if total_pages and page > total_pages:
        return _error(
            "A página solicitada está fora do intervalo disponível.",
            400,
            errors={"page": f"A última página disponível é {total_pages}."},
        )

    return jsonify(
        {
            "success": True,
            "data": [_serialize_movement(movement) for movement in movements],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
            "sorting": {"sort": sort, "direction": direction},
            "filters": {
                "q": search,
                "tipo": movement_type,
                "data_inicio": start_label,
                "data_fim": end_label,
            },
        }
    )


@api_bp.get("/movimentacoes/<int:movement_id>")
def get_movement(movement_id):
    statement = (
        select(Movimentacao)
        .where(Movimentacao.id == movement_id)
        .options(
            joinedload(Movimentacao.produto),
            joinedload(Movimentacao.usuario),
        )
    )
    try:
        movement = db.session.scalar(statement)
    except SQLAlchemyError:
        current_app.logger.exception(
            "Falha da API ao consultar movimentação %s", movement_id
        )
        return _error("Não foi possível consultar a movimentação.", 503)
    if movement is None:
        return _error("Movimentação não encontrada.", 404)

    return jsonify({"success": True, "data": _serialize_movement(movement)})


@api_bp.post("/movimentacoes/entradas")
def create_entry():
    return _create_movement("ENTRADA")


@api_bp.post("/movimentacoes/saidas")
def create_exit():
    return _create_movement("SAIDA")


def _create_movement(movement_type):
    if not request.is_json:
        return _error("Envie os dados como JSON.", 400)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("O corpo da requisição deve ser um objeto JSON válido.", 400)

    allowed_fields = {"produto_id", "quantidade", "observacao"}
    unexpected_fields = set(payload) - allowed_fields
    if unexpected_fields:
        return _error(
            "A requisição contém campos não permitidos.",
            400,
            errors={field: "Campo não permitido." for field in sorted(unexpected_fields)},
        )

    missing_fields = [
        field for field in ("produto_id", "quantidade") if field not in payload
    ]
    if missing_fields:
        return _error(
            "Campos obrigatórios ausentes.",
            400,
            errors={field: "Campo obrigatório." for field in missing_fields},
        )

    product_id = payload["produto_id"]
    quantity = payload["quantidade"]
    observation = payload.get("observacao")
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        return _error(
            "Dados inválidos.",
            422,
            errors={"produto_id": "Informe um identificador inteiro."},
        )
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        return _error(
            "Dados inválidos.",
            422,
            errors={"quantidade": "Informe uma quantidade inteira."},
        )
    if observation is not None and not isinstance(observation, str):
        return _error(
            "Dados inválidos.",
            422,
            errors={"observacao": "Informe um texto."},
        )

    try:
        movement = register_movement(
            product_id=product_id,
            user_id=current_user.id,
            movement_type=movement_type,
            quantity=quantity,
            observation=observation,
        )
    except MovementError as error:
        return _error(error.message, error.status_code, errors={error.field: error.message})
    except MovementPersistenceError:
        current_app.logger.exception("Falha de persistência ao registrar movimentação")
        return _error(
            "Não foi possível registrar a movimentação. Tente novamente.", 503
        )

    message = (
        "Entrada registrada com sucesso."
        if movement_type == "ENTRADA"
        else "Saída registrada com sucesso."
    )
    return (
        jsonify(
            {
                "success": True,
                "message": message,
                "data": {
                    "id": movement.id,
                    "produto_id": movement.produto_id,
                    "produto": movement.produto.nome,
                    "tipo": movement.tipo,
                    "quantidade_movimentada": movement.quantidade,
                    "estoque_atual": movement.produto.quantidade,
                    "data": movement.data.isoformat(),
                },
            }
        ),
        201,
    )


def _pagination():
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise ValueError("Os parâmetros limit e offset devem ser números inteiros.") from error
    if limit < 1 or limit > 100:
        raise ValueError("O parâmetro limit deve estar entre 1 e 100.")
    if offset < 0:
        raise ValueError("O parâmetro offset não pode ser negativo.")
    return limit, offset


def _movement_query():
    try:
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "20"))
    except ValueError as error:
        raise ValueError("page e page_size devem ser números inteiros.") from error
    if page < 1:
        raise ValueError("page deve ser maior ou igual a 1.")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size deve estar entre 1 e 100.")

    sort = request.args.get("sort", "data")
    if sort not in {"data", "produto", "tipo", "quantidade", "usuario"}:
        raise ValueError("A coluna de ordenação solicitada não é permitida.")
    direction = request.args.get("direction", "desc").lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("direction deve ser asc ou desc.")
    return page, page_size, sort, direction


def _movement_date_range():
    start_label = request.args.get("data_inicio", "").strip()
    end_label = request.args.get("data_fim", "").strip()
    try:
        start_date = date.fromisoformat(start_label) if start_label else None
        end_date = date.fromisoformat(end_label) if end_label else None
    except ValueError as error:
        raise ValueError("data_inicio e data_fim devem usar o formato AAAA-MM-DD.") from error
    if (
        (start_date and start_date.isoformat() != start_label)
        or (end_date and end_date.isoformat() != end_label)
    ):
        raise ValueError("data_inicio e data_fim devem usar o formato AAAA-MM-DD.")

    if start_date and end_date and start_date > end_date:
        raise ValueError("data_inicio não pode ser posterior a data_fim.")

    try:
        local_timezone = ZoneInfo(
            current_app.config.get("APP_TIMEZONE", "America/Sao_Paulo")
        )
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise RuntimeError("O fuso horário da aplicação está inválido.") from error

    start_utc = (
        datetime.combine(start_date, time.min, tzinfo=local_timezone)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
        if start_date
        else None
    )
    try:
        end_utc = (
            datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=local_timezone)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
            if end_date
            else None
        )
    except OverflowError as error:
        raise ValueError("data_fim está fora do intervalo suportado.") from error

    return start_utc, end_utc, start_label, end_label


def _serialize_movement(movement):
    return {
        "id": movement.id,
        "produto_id": movement.produto_id,
        "produto": movement.produto.nome,
        "codigo_barras": movement.produto.codigo_barras,
        "tipo": movement.tipo,
        "quantidade": movement.quantidade,
        "estoque_atual": movement.produto.quantidade,
        "observacao": movement.observacao,
        "data": movement.data.isoformat(),
        "usuario_id": movement.usuario_id,
        "usuario": movement.usuario.nome,
    }


def _error(message, status_code, errors=None):
    normalized_errors = {
        field: value if isinstance(value, list) else [str(value)]
        for field, value in (errors or {}).items()
    }
    response = {
        "success": False,
        "message": message,
        "errors": normalized_errors,
    }
    return jsonify(response), status_code
