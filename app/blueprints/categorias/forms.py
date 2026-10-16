from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class CategoriaForm(FlaskForm):
    nome = StringField(
        "Nome da categoria",
        validators=[
            DataRequired(message="Informe o nome da categoria."),
            Length(max=120, message="Use no máximo 120 caracteres."),
        ],
    )
    descricao = TextAreaField(
        "Descrição",
        validators=[Length(max=500, message="Use no máximo 500 caracteres.")],
    )
    ativo = SelectField(
        "Status",
        choices=[("true", "Ativa"), ("false", "Inativa")],
        default="true",
        validators=[DataRequired(message="Selecione um status.")],
    )
    submit = SubmitField("Salvar categoria")
