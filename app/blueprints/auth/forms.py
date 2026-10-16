import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, InputRequired, Length, ValidationError


class LoginForm(FlaskForm):
    email = StringField(
        "E-mail",
        validators=[DataRequired(message="Informe seu e-mail."), Length(max=255)],
    )
    password = PasswordField(
        "Senha", validators=[InputRequired(message="Informe sua senha.")]
    )
    remember = BooleanField("Manter conectado")
    submit = SubmitField("Entrar")

    def validate_email(self, field):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", field.data.strip()):
            raise ValidationError("Informe um e-mail válido.")
