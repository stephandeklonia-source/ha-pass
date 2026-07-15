"""Add remember_pin flag to tokens.

Controls whether a guest's PIN session cookie persists across visits
(default: yes) or must be re-entered every time the guest link is opened.

Revision ID: 005
Revises: 004
"""
from alembic import op

revision = "005"
down_revision = "004"


def upgrade() -> None:
    op.execute("ALTER TABLE tokens ADD COLUMN remember_pin INTEGER NOT NULL DEFAULT 1")


def downgrade() -> None:
    op.execute("ALTER TABLE tokens DROP COLUMN remember_pin")
