"""Record proposal decisions and version proposals per assessment lineage."""
from alembic import op
import sqlalchemy as sa

revision = "0006_proposal_decision_trail"
down_revision = "0005_pipeline_proposals"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pipeline_proposals", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.add_column("pipeline_proposals", sa.Column("decided_by", sa.String(255), nullable=True))
    op.add_column("pipeline_proposals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("pipeline_proposals_version_key", "pipeline_proposals", type_="unique")
    op.create_unique_constraint(
        "pipeline_proposals_assessment_version_key", "pipeline_proposals", ["assessment_id", "version"]
    )
    op.create_index(
        "pipeline_proposals_unassessed_version_key", "pipeline_proposals", ["version"],
        unique=True, postgresql_where=sa.text("assessment_id IS NULL"),
    )


def downgrade():
    op.drop_index("pipeline_proposals_unassessed_version_key", table_name="pipeline_proposals")
    op.drop_constraint("pipeline_proposals_assessment_version_key", "pipeline_proposals", type_="unique")
    op.create_unique_constraint("pipeline_proposals_version_key", "pipeline_proposals", ["version"])
    op.drop_column("pipeline_proposals", "decided_at")
    op.drop_column("pipeline_proposals", "decided_by")
    op.drop_column("pipeline_proposals", "decision_reason")
