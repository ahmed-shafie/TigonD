"""Persist NiFi flow versions and run state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_nifi_execution"
down_revision = "0002_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flow_deployments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("source_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("runtime", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("external_flow_id", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("flow_spec", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("assessment_id", "version", name="uq_flow_version"),
    )
    op.create_index("ix_flow_status", "flow_deployments", ["status", "updated_at"])


def downgrade():
    op.drop_index("ix_flow_status", table_name="flow_deployments")
    op.drop_table("flow_deployments")
