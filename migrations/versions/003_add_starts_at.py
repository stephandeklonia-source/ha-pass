"""Add starts_at column to tokens.

Revision ID: 003
Revises: 002
"""
from alembic import op

revision = "003"
down_revision = "002"

def upgrade() -> None:
    # NULL = active immediately (backward compatible with existing tokens)
    op.execute("ALTER TABLE tokens ADD COLUMN starts_at INTEGER")

def downgrade() -> None:
    op.execute("ALTER TABLE tokens DROP COLUMN starts_at")
