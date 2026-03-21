"""Add scoring columns to detections table.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-03-21

Adds calibrated_confidence, situation_score, final_score, and fp_flags
columns to the detections table to support the new scoring pipeline.
"""

from alembic import op


# revision identifiers, used by Alembic
revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add scoring columns to the detections table."""
    # Use ADD COLUMN IF NOT EXISTS to be idempotent and safe on re-runs
    op.execute("""
        ALTER TABLE detections
        ADD COLUMN IF NOT EXISTS calibrated_confidence FLOAT,
        ADD COLUMN IF NOT EXISTS situation_score FLOAT,
        ADD COLUMN IF NOT EXISTS final_score FLOAT,
        ADD COLUMN IF NOT EXISTS fp_flags TEXT;
    """)

    # Add an index on final_score for efficient filtering/ordering
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_detection_final_score
        ON detections (final_score);
    """)


def downgrade() -> None:
    """Remove scoring columns from the detections table."""
    op.execute("DROP INDEX IF EXISTS idx_detection_final_score;")
    op.execute("""
        ALTER TABLE detections
        DROP COLUMN IF EXISTS calibrated_confidence,
        DROP COLUMN IF EXISTS situation_score,
        DROP COLUMN IF EXISTS final_score,
        DROP COLUMN IF EXISTS fp_flags;
    """)
