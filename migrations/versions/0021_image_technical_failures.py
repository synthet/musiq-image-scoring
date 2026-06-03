"""image technical failures

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-16 23:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create the table
    op.create_table(
        'image_technical_failures',
        sa.Column('image_id', sa.Integer(), nullable=False),
        sa.Column('technical_failure_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('primary_reject_reason', sa.String(length=128), nullable=False, server_default='none'),
        sa.Column('blur', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('overexposed', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('underexposed', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('highlight_clipping', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('shadow_crushing', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['image_id'], ['images.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('image_id')
    )

def downgrade() -> None:
    op.drop_table('image_technical_failures')
