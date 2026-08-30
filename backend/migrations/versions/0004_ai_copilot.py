"""Persist audited AI copilot conversations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_ai_copilot"
down_revision = "0003_nifi_execution"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("tools_used", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_assistant_conversation", "assistant_messages", ["conversation_id", "created_at"])


def downgrade():
    op.drop_index("ix_assistant_conversation", table_name="assistant_messages")
    op.drop_table("assistant_messages")
