import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    if app.config["APP_ENV"] == "production":
        raise RuntimeError(
            "Não use o servidor de desenvolvimento em produção. "
            "Inicie a aplicação com Gunicorn (gunicorn run:app)."
        )
    debug = (
        app.config["APP_ENV"] == "development"
        and os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true"}
    )
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=debug,
    )
