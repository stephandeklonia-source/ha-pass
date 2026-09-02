"""Add entity templates table.

Reusable named entity-selections for the create-token entity picker, so
an admin doesn't have to re-search the same devices for every new link.

Revision ID: 007
Revises: 006
"""
from alembic import op

revision = "007"
down_revision = "006"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id          TEXT PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            entity_ids  TEXT NOT NULL,
            created_at  INTEGER NOT NULL
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS templates")
