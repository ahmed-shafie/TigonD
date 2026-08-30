"""Persist AI-generated, non-executable pipeline proposals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_pipeline_proposals"
down_revision = "0004_ai_copilot"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipeline_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("source_assessments.id", ondelete="SET NULL")),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade():
    op.drop_table("pipeline_proposals")
