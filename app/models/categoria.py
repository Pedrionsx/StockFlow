from app.extensions import db


class Categoria(db.Model):
    __tablename__ = "categorias"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)
    descricao = db.Column(db.String(500), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

    produtos = db.relationship("Produto", back_populates="categoria")
