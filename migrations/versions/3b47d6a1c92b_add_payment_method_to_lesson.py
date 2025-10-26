"""
add payment_method to lesson

Revision ID: 3b47d6a1c92b
Revises: 02c515f814a9
Create Date: 2025-09-25 08:05:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3b47d6a1c92b"
down_revision = "02c515f814a9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # הוסף עמודה רק אם לא קיימת
    cols = [c["name"] for c in insp.get_columns("lesson")]
    if "payment_method" not in cols:
        op.add_column(
            "lesson",
            sa.Column("payment_method", sa.String(length=30), nullable=True),
        )

    # צור אינדקס רק אם לא קיים
    idx_name = "ix_lesson_payment_method"
    existing_idx = [i["name"] for i in insp.get_indexes("lesson")]
    if idx_name not in existing_idx:
        op.create_index(idx_name, "lesson", ["payment_method"], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # מחיקת אינדקס אם קיים
    idx_name = "ix_lesson_payment_method"
    existing_idx = [i["name"] for i in insp.get_indexes("lesson")]
    if idx_name in existing_idx:
        op.drop_index(idx_name, table_name="lesson")

    # מחיקת עמודה אם קיימת
    cols = [c["name"] for c in insp.get_columns("lesson")]
    if "payment_method" in cols:
        op.drop_column("lesson", "payment_method")

