"""Add classification column to detections table.

Revision ID: b1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22

Adds the classification column to the detections table to support the 3-state
vessel classification system (identified, unidentified, ais_gap).
"""

from alembic import op


# revision identifiers, used by Alembic
revision = "b1b2c3d4e5f7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add classification column to the detections table and populate existing data."""
    # 1. Add the column
    op.execute("""
        ALTER TABLE detections
        ADD COLUMN IF NOT EXISTS classification VARCHAR(32);
    """)

    # 2. Add the index
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_detection_classification
        ON detections (classification);
    """)

    # 3. Perform initial classification for existing data
    # identified: has mmsi, dist <= 500
    # anomaly: has mmsi, dist > 500
    # unidentified/ais_gap: no mmsi (default to unidentified for safety)
    op.execute("""
        UPDATE detections
        SET classification = CASE
            WHEN mmsi IS NOT NULL AND correlation_distance_m <= 500 THEN 'identified'
            WHEN mmsi IS NOT NULL AND correlation_distance_m > 500 THEN 'anomaly'
            WHEN mmsi IS NOT NULL AND correlation_distance_m IS NULL THEN 'identified'
            WHEN mmsi IS NULL THEN 'unidentified'
            ELSE 'ais_gap'
        END
        WHERE classification IS NULL;
    """)


def downgrade() -> None:
    """Remove classification column from the detections table."""
    op.execute("DROP INDEX IF EXISTS idx_detection_classification;")
    op.execute("""
        ALTER TABLE detections
        DROP COLUMN IF EXISTS classification;
    """)
