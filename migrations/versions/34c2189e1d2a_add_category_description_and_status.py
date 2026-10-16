"""Add category description and active status

Revision ID: 34c2189e1d2a
Revises: e85a276ce7c0
Create Date: 2026-10-14 17:09:00

"""
from alembic import op
import sqlalchemy as sa


revision = "34c2189e1d2a"
down_revision = "e85a276ce7c0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("categorias", schema=None) as batch_op:
        batch_op.add_column(sa.Column("descricao", sa.String(length=500), nullable=True))
        batch_op.add_column(
            sa.Column("ativo", sa.Boolean(), server_default="1", nullable=False)
        )


def downgrade():
    with op.batch_alter_table("categorias", schema=None) as batch_op:
        batch_op.drop_column("ativo")
        batch_op.drop_column("descricao")
