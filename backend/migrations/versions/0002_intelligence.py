"""Persist source assessments and approval feedback."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_intelligence"
down_revision = "0001_core_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_name", sa.String(100), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("recommended_runtime", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("decision_reason", sa.String(500)),
        sa.Column("decided_by", sa.String(255)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_assessments_source", "source_assessments", ["source_id", "created_at"])


def downgrade():
    op.drop_index("ix_assessments_source", table_name="source_assessments")
    op.drop_table("source_assessments")
