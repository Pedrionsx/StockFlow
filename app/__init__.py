import click
import os
import secrets

from flask import Flask, current_app, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from config import Config
from app.extensions import csrf, db, login_manager, migrate

from app import models


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    app_env = (app.config.get("APP_ENV") or "production").strip().lower()
    if app_env not in {"development", "testing", "production"}:
        raise RuntimeError(
            "APP_ENV deve ser development, testing ou production."
        )
    if not app.config.get("SECRET_KEY"):
        if app_env == "production":
            raise RuntimeError(
                "SECRET_KEY é obrigatória em produção. Configure uma chave "
                "aleatória e estável nas variáveis de ambiente."
            )
        app.config["SECRET_KEY"] = secrets.token_hex(32)
    if app_env == "production" and not (
        app.config.get("DATABASE_URL") or ""
    ).strip():
        raise RuntimeError(
            "DATABASE_URL é obrigatória em produção. Configure a conexão "
            "com o MySQL nas variáveis de ambiente."
        )
    app.config["APP_ENV"] = app_env
    app.config["DEBUG"] = False
    if app_env == "production":
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["REMEMBER_COOKIE_SECURE"] = True

    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entre na sua conta para continuar."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"
    database_url = (app.config.get("DATABASE_URL") or "").strip()
    if database_url:
        try:
            parsed_database_url = make_url(database_url)
        except ArgumentError:
            raise RuntimeError(
                "DATABASE_URL deve ser uma URL SQLAlchemy válida."
            ) from None
        if parsed_database_url.drivername == "mysql":
            parsed_database_url = parsed_database_url.set(
                drivername="mysql+pymysql"
            )
            database_url = parsed_database_url.render_as_string(
                hide_password=False
            )
    app.config["DATABASE_URL"] = database_url

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return None
        return db.session.get(models.Usuario, user_id)

    if database_url:
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
        db.init_app(app)
    else:
        app.logger.warning(
            "DATABASE_URL não configurada; a integração com o banco está desativada."
        )

    migrate.init_app(app, db)

    from app.seeds import register_commands

    register_commands(app)

    from app.blueprints.auth import auth_bp
    from app.blueprints.auth.routes import register_commands as register_auth_commands
    from app.blueprints.categorias import categorias_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.movimentacoes import movimentacoes_bp
    from app.blueprints.movimentacoes.api import api_bp
    from app.blueprints.produtos import produtos_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(categorias_bp, url_prefix="/categorias")
    app.register_blueprint(produtos_bp, url_prefix="/produtos")
    app.register_blueprint(movimentacoes_bp, url_prefix="/movimentacoes")
    app.register_blueprint(api_bp, url_prefix="/api")
    register_auth_commands(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith("/api/"):
            return jsonify(
                {
                    "success": False,
                    "message": "Token CSRF ausente ou inválido.",
                    "errors": {},
                }
            ), 400
        return render_template(
            "errors/error.html",
            code=400,
            title="Solicitação inválida",
            message="Não foi possível validar sua solicitação. Atualize a página e tente novamente.",
        ), 400

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        code = error.code or 500
        messages = {
            401: ("Acesso necessário", "Entre na sua conta para continuar."),
            403: ("Acesso negado", "Você não tem permissão para acessar este conteúdo."),
            404: ("Página não encontrada", "O endereço solicitado não existe ou foi movido."),
            405: ("Ação indisponível", "Essa ação não está disponível para esta solicitação."),
        }
        title, message = messages.get(
            code, ("Não foi possível concluir", "A solicitação não pôde ser concluída.")
        )
        if request.path.startswith("/api/") or request.is_json:
            return jsonify(
                {"success": False, "message": message, "errors": {}}
            ), code
        error_templates = {
            403: "errors/403.html",
            404: "errors/404.html",
        }
        return render_template(
            error_templates.get(code, "errors/error.html"),
            code=code,
            title=title,
            message=message,
        ), code

    @app.errorhandler(500)
    def handle_internal_error(error):
        original = getattr(error, "original_exception", None)
        if original is not None:
            current_app.logger.error(
                "Unhandled application exception",
                exc_info=(type(original), original, original.__traceback__),
            )
        else:
            current_app.logger.error("Unhandled internal server error")
        if database_url:
            db.session.rollback()

        message = "Ocorreu um erro inesperado. Tente novamente mais tarde."
        if request.path.startswith("/api/") or request.is_json:
            return jsonify(
                {"success": False, "message": message, "errors": {}}
            ), 500
        return render_template(
            "errors/500.html",
            code=500,
            title="Erro interno",
            message=message,
        ), 500

    @app.get("/health")
    def index():
        return jsonify(
            {
                "aplicacao": "StockFlow",
                "status": "ok",
                "banco_configurado": bool(app.config["DATABASE_URL"]),
            }
        )

    @app.get("/ready")
    def readiness():
        if not database_url:
            return jsonify({"status": "not_ready"}), 503
        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            current_app.logger.exception("Banco indisponível no teste de readiness")
            return jsonify({"status": "not_ready"}), 503
        return jsonify({"status": "ready"})

    @app.cli.command("check-db")
    def check_db():
        """Verifica a conexão configurada com o banco de dados."""
        if not database_url:
            raise click.ClickException(
                "DATABASE_URL está vazia. Configure a conexão no arquivo .env."
            )

        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise click.ClickException(
                f"Não foi possível conectar ao banco de dados: {error}"
            ) from error

        click.echo("Conexão com o banco de dados estabelecida com sucesso.")
        app.logger.debug("Conexão com o banco de dados estabelecida com sucesso.")

    return app
