import re

import click
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.cli import with_appcontext
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from app.blueprints.auth.forms import LoginForm
from app.extensions import db
from app.models import Usuario

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        try:
            user = db.session.scalar(select(Usuario).where(Usuario.email == email))
        except SQLAlchemyError:
            current_app.logger.exception("Falha ao consultar usuário durante login")
            flash("Não foi possível entrar agora. Tente novamente.", "error")
            return render_template("auth/login.html", form=form), 503

        if user is None or not check_password_hash(user.senha_hash, form.password.data):
            flash("E-mail ou senha inválidos.", "error")
            return render_template("auth/login.html", form=form), 401

        login_user(user, remember=form.remember.data)
        flash(f"Bem-vindo(a), {user.nome}.", "success")
        destination = request.args.get("next", "")
        if _is_safe_redirect(destination):
            return redirect(destination)
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html", form=form)


@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Você saiu da sua conta.", "success")
    return redirect(url_for("auth.login"))


def _is_safe_redirect(target):
    return (
        target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
        and not any(ord(character) < 32 for character in target)
    )


@click.command("create-user")
@click.option("--email", prompt=True, help="E-mail da nova conta.")
@click.option("--name", prompt="Nome", help="Nome da nova conta.")
@with_appcontext
def create_user_command(email, name):
    """Cria uma conta local sem disponibilizar cadastro público."""
    from flask import current_app

    if not current_app.config.get("DATABASE_URL"):
        raise click.ClickException(
            "DATABASE_URL está vazia. Configure o banco antes de criar usuários."
        )

    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise click.ClickException("Informe um endereço de e-mail válido.")
    if not name.strip():
        raise click.ClickException("O nome não pode ficar vazio.")

    password = click.prompt(
        "Senha", hide_input=True, confirmation_prompt=True
    )
    if not password:
        raise click.ClickException("A senha não pode ficar vazia.")

    try:
        existing_user = db.session.scalar(
            select(Usuario).where(Usuario.email == email)
        )
        if existing_user is not None:
            raise click.ClickException("Já existe uma conta com esse e-mail.")

        db.session.add(
            Usuario(
                nome=name.strip(),
                email=email,
                senha_hash=generate_password_hash(password),
            )
        )
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise click.ClickException("Já existe uma conta com esse e-mail.") from error
    except SQLAlchemyError as error:
        db.session.rollback()
        current_app.logger.exception("Falha ao criar usuário pela CLI")
        raise click.ClickException(
            "Não foi possível criar a conta. Consulte os logs da aplicação."
        ) from error

    click.echo(f"Conta criada para {email}.")


def register_commands(app):
    app.cli.add_command(create_user_command)
