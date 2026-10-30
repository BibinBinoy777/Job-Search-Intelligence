"""Local account recovery and deletion state, additive."""

import sqlalchemy as sa
from alembic import op

revision = "0007_local_operations"
down_revision = "0006_automation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("deletion_pending", sa.Boolean(), server_default="false", nullable=False)
    )
    op.create_table(
        "recovery_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recovery_tokens_user_id", "recovery_tokens", ["user_id"])
    op.create_index("ix_recovery_tokens_expires_at", "recovery_tokens", ["expires_at"])


def downgrade():
    op.drop_table("recovery_tokens")
    op.drop_column("users", "deletion_pending")
