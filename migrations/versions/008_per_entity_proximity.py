"""Move the proximity requirement from a per-token toggle to per-entity.

Lets an admin require proximity for a specific entity (e.g. a helper
button wired to a door relay) without forcing every entity in the token
through the same check. Existing tokens that had the old blanket toggle
on keep it for their lock/alarm_control_panel entities, matching prior
behavior (those were the only domains it ever applied to).

Revision ID: 008
Revises: 007
"""
from alembic import op

revision = "008"
down_revision = "007"


def upgrade() -> None:
    op.execute("ALTER TABLE token_entities ADD COLUMN require_proximity INTEGER NOT NULL DEFAULT 0")
    op.execute("""
        UPDATE token_entities
        SET require_proximity = 1
        WHERE token_id IN (SELECT id FROM tokens WHERE require_proximity = 1)
          AND (entity_id LIKE 'lock.%' OR entity_id LIKE 'alarm_control_panel.%')
    """)
    op.execute("ALTER TABLE tokens DROP COLUMN require_proximity")


def downgrade() -> None:
    op.execute("ALTER TABLE tokens ADD COLUMN require_proximity INTEGER NOT NULL DEFAULT 0")
    op.execute("""
        UPDATE tokens
        SET require_proximity = 1
        WHERE id IN (SELECT token_id FROM token_entities WHERE require_proximity = 1)
    """)
    op.execute("ALTER TABLE token_entities DROP COLUMN require_proximity")
