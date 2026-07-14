"""Add PIN protection: encrypted pin, access_code, guest_pin_sessions.

Revision ID: 004
Revises: 003
"""
from alembic import op

revision = "004"
down_revision = "003"


def upgrade() -> None:
    op.execute("ALTER TABLE tokens ADD COLUMN pin_encrypted TEXT")
    op.execute("ALTER TABLE tokens ADD COLUMN access_code TEXT")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tokens_access_code ON tokens(access_code)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS guest_pin_sessions (
            id          TEXT PRIMARY KEY,
            token_id    TEXT NOT NULL REFERENCES tokens(id) ON DELETE CASCADE,
            created_at  INTEGER NOT NULL,
            expires_at  INTEGER NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_guest_pin_sessions_token_id ON guest_pin_sessions(token_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_guest_pin_sessions_expires_at ON guest_pin_sessions(expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS guest_pin_sessions")
    op.execute("DROP INDEX IF EXISTS idx_tokens_access_code")
    op.execute("ALTER TABLE tokens DROP COLUMN access_code")
    op.execute("ALTER TABLE tokens DROP COLUMN pin_encrypted")
