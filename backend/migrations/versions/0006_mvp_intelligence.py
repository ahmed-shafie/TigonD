"""Persist approvals, incidents, memory, feedback and lineage events."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_mvp_intelligence"
down_revision = "0005_pipeline_proposals"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("operational_actions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("deployment_id", sa.String(36), nullable=False), sa.Column("action", sa.String(20), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False), sa.Column("token_hash", sa.String(64)), sa.Column("idempotency_key", sa.String(200), unique=True), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("incidents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("deployment_id", sa.String(36), nullable=False), sa.Column("category", sa.String(30), nullable=False), sa.Column("severity", sa.String(20), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("intelligence_memory", sa.Column("id", sa.String(36), primary_key=True), sa.Column("scope", sa.String(20), nullable=False), sa.Column("subject_id", sa.String(200), nullable=False), sa.Column("fact", sa.Text(), nullable=False), sa.Column("source", sa.String(200), nullable=False), sa.Column("embedding", postgresql.ARRAY(sa.Float())), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("recommendation_feedback", sa.Column("id", sa.String(36), primary_key=True), sa.Column("recommendation_id", sa.String(100), nullable=False), sa.Column("accepted", sa.Boolean(), nullable=False), sa.Column("outcome", sa.String(20), nullable=False), sa.Column("notes", sa.String(500)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_table("lineage_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("event_type", sa.String(50), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))


def downgrade():
    for table in ("lineage_events", "recommendation_feedback", "intelligence_memory", "incidents", "operational_actions"):
        op.drop_table(table)

