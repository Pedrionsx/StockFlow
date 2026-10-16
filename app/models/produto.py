from sqlalchemy import CheckConstraint

from app.extensions import db


class Produto(db.Model):
    __tablename__ = "produtos"
    __table_args__ = (
        CheckConstraint("quantidade >= 0", name="ck_produtos_quantidade_nao_negativa"),
        CheckConstraint(
            "estoque_minimo >= 0", name="ck_produtos_estoque_minimo_nao_negativo"
        ),
        CheckConstraint("preco_custo >= 0", name="ck_produtos_preco_custo_nao_negativo"),
        CheckConstraint(
            "preco_venda >= 0", name="ck_produtos_preco_venda_nao_negativo"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    codigo_barras = db.Column(db.String(64), nullable=False, unique=True, index=True)
    nome = db.Column(db.String(160), nullable=False, index=True)
    quantidade = db.Column(db.Integer, nullable=False, default=0)
    preco_custo = db.Column(db.Numeric(10, 2), nullable=False)
    preco_venda = db.Column(db.Numeric(10, 2), nullable=False)
    estoque_minimo = db.Column(db.Integer, nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categorias.id"), nullable=False, index=True
    )

    categoria = db.relationship("Categoria", back_populates="produtos")
    movimentacoes = db.relationship("Movimentacao", back_populates="produto")
