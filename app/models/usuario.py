from flask_login import UserMixin

from app.extensions import db


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)

    movimentacoes = db.relationship("Movimentacao", back_populates="usuario")
