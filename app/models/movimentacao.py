from datetime import datetime, timezone

from sqlalchemy import CheckConstraint

from app.extensions import db


class Movimentacao(db.Model):
    __tablename__ = "movimentacoes"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('ENTRADA', 'SAIDA')", name="ck_movimentacoes_tipo_valido"
        ),
        CheckConstraint("quantidade > 0", name="ck_movimentacoes_quantidade_positiva"),
    )

    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(
        db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True
    )
    tipo = db.Column(db.String(7), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    data = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    observacao = db.Column(db.Text, nullable=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )

    produto = db.relationship("Produto", back_populates="movimentacoes")
    usuario = db.relationship("Usuario", back_populates="movimentacoes")
