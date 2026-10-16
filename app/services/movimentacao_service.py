from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Movimentacao, Produto, Usuario


class MovementError(Exception):
    status_code = 422

    def __init__(self, message, field="quantidade"):
        super().__init__(message)
        self.message = message
        self.field = field


class ProductNotFoundError(MovementError):
    status_code = 404

    def __init__(self):
        super().__init__("Produto não encontrado.", "produto_id")


class InactiveProductError(MovementError):
    status_code = 409

    def __init__(self):
        super().__init__("Produtos inativos não aceitam movimentações.", "produto_id")


class InsufficientStockError(MovementError):
    status_code = 409

    def __init__(self):
        super().__init__(
            "A quantidade solicitada excede o estoque disponível.", "quantidade"
        )


class MovementPersistenceError(Exception):
    pass


def register_movement(product_id, user_id, movement_type, quantity, observation=None):
    if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id <= 0:
        raise MovementError("Informe um produto válido.", "produto_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise MovementError("Usuário autenticado inválido.", "usuario_id")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise MovementError(
            "A quantidade deve ser um número inteiro maior que zero.", "quantidade"
        )
    if quantity > 2_147_483_647:
        raise MovementError("A quantidade informada excede o limite permitido.")
    if movement_type not in {"ENTRADA", "SAIDA"}:
        raise MovementError("Tipo de movimentação inválido.", "tipo")
    if observation is not None:
        if not isinstance(observation, str):
            raise MovementError("A observação deve ser um texto.", "observacao")
        observation = observation.strip()
        if len(observation) > 2000:
            raise MovementError(
                "A observação deve ter no máximo 2000 caracteres.", "observacao"
            )
        observation = observation or None

    try:
        statement = (
            select(Produto)
            .where(Produto.id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        product = db.session.scalar(statement)
        if product is None:
            raise ProductNotFoundError()
        if not product.ativo:
            raise InactiveProductError()

        user = db.session.get(Usuario, user_id)
        if user is None:
            raise MovementError("Usuário autenticado não encontrado.", "usuario_id")

        if movement_type == "SAIDA" and product.quantidade < quantity:
            raise InsufficientStockError()

        if movement_type == "ENTRADA":
            if product.quantidade + quantity > 2_147_483_647:
                raise MovementError(
                    "A quantidade ultrapassaria o limite de estoque permitido."
                )
            product.quantidade += quantity
        else:
            product.quantidade -= quantity

        movement = Movimentacao(
            produto=product,
            usuario=user,
            tipo=movement_type,
            quantidade=quantity,
            observacao=observation,
        )
        db.session.add(movement)
        db.session.commit()
        return movement
    except MovementError:
        db.session.rollback()
        raise
    except SQLAlchemyError as error:
        db.session.rollback()
        raise MovementPersistenceError(
            "Não foi possível registrar a movimentação."
        ) from error
    except Exception:
        db.session.rollback()
        raise
