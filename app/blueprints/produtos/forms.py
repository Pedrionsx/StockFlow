from decimal import Decimal

from flask_wtf import FlaskForm
from sqlalchemy import select
from wtforms import DecimalField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, ValidationError

from app.extensions import db
from app.models import Categoria, Produto


class ProdutoForm(FlaskForm):
    nome = StringField(
        "Nome do produto",
        validators=[
            DataRequired(message="Informe o nome do produto."),
            Length(max=160, message="Use no máximo 160 caracteres."),
        ],
    )
    codigo_barras = StringField(
        "Código de barras",
        validators=[
            DataRequired(message="Informe o código de barras."),
            Length(max=64, message="Use no máximo 64 caracteres."),
        ],
    )
    categoria_id = SelectField(
        "Categoria",
        coerce=int,
        choices=[(0, "Selecione uma categoria")],
        validators=[InputRequired(message="Selecione uma categoria.")],
    )
    preco_custo = DecimalField(
        "Preço de custo",
        places=2,
        validators=[
            InputRequired(message="Informe o preço de custo."),
            NumberRange(min=Decimal("0"), message="O preço não pode ser negativo."),
        ],
    )
    preco_venda = DecimalField(
        "Preço de venda",
        places=2,
        validators=[
            InputRequired(message="Informe o preço de venda."),
            NumberRange(min=Decimal("0"), message="O preço não pode ser negativo."),
        ],
    )
    quantidade = IntegerField(
        "Quantidade em estoque",
        validators=[
            InputRequired(message="Informe a quantidade."),
            NumberRange(min=0, message="A quantidade não pode ser negativa."),
        ],
    )
    estoque_minimo = IntegerField(
        "Estoque mínimo",
        validators=[
            InputRequired(message="Informe o estoque mínimo."),
            NumberRange(min=0, message="O estoque mínimo não pode ser negativo."),
        ],
    )
    submit = SubmitField("Salvar produto")

    def __init__(self, product_id=None, *args, **kwargs):
        self.product_id = product_id
        super().__init__(*args, **kwargs)

    def validate_codigo_barras(self, field):
        if not field.data.strip():
            raise ValidationError("Informe o código de barras.")
        statement = select(Produto.id).where(
            Produto.codigo_barras == field.data.strip()
        )
        if self.product_id is not None:
            statement = statement.where(Produto.id != self.product_id)
        if db.session.scalar(statement) is not None:
            raise ValidationError("Este código de barras já está cadastrado.")

    def validate_categoria_id(self, field):
        if field.data <= 0:
            raise ValidationError("Selecione uma categoria válida.")
        category = db.session.get(Categoria, field.data)
        if category is None:
            raise ValidationError("Selecione uma categoria válida.")
        if category.ativo:
            return
        if self.product_id is not None:
            product_category_id = db.session.scalar(
                select(Produto.categoria_id).where(Produto.id == self.product_id)
            )
            if product_category_id == category.id:
                return
        raise ValidationError("Não é possível associar produtos a uma categoria inativa.")
