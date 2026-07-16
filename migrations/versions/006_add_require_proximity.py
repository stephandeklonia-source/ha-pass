"""Add require_proximity flag to tokens.

When set, lock and alarm_control_panel commands for this token must come
with a guest-reported location within HA's home zone radius.

Revision ID: 006
Revises: 005
"""
from alembic import op

revision = "006"
down_revision = "005"


def upgrade() -> None:
    op.execute("ALTER TABLE tokens ADD COLUMN require_proximity INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE tokens DROP COLUMN require_proximity")
