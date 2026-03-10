"""Add MITRE ATT&CK tables

Revision ID: aaa111000001
Revises: d5a720d1b99b
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from app.alembic.alembic_utils import _has_table

revision = 'aaa111000001'
down_revision = 'd5a720d1b99b'
branch_labels = None
depends_on = None


def upgrade():
    if not _has_table('mitre_tactics'):
        op.create_table(
            'mitre_tactics',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('mitre_id', sa.String(20), nullable=False, unique=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('short_name', sa.String(60), nullable=True),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('order', sa.Integer, nullable=True),
        )

    if not _has_table('mitre_techniques'):
        op.create_table(
            'mitre_techniques',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('mitre_id', sa.String(20), nullable=False, unique=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('is_subtechnique', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('parent_id', sa.Integer, sa.ForeignKey('mitre_techniques.id'), nullable=True),
        )

    if not _has_table('mitre_technique_tactic_map'):
        op.create_table(
            'mitre_technique_tactic_map',
            sa.Column('technique_id', sa.Integer, sa.ForeignKey('mitre_techniques.id'), primary_key=True),
            sa.Column('tactic_id', sa.Integer, sa.ForeignKey('mitre_tactics.id'), primary_key=True),
        )

    if not _has_table('case_mitre_association'):
        op.create_table(
            'case_mitre_association',
            sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column('case_id', sa.BigInteger, sa.ForeignKey('cases.case_id'), nullable=False, index=True),
            sa.Column('technique_id', sa.Integer, sa.ForeignKey('mitre_techniques.id'), nullable=False),
            sa.Column('note', sa.Text, nullable=True),
            sa.UniqueConstraint('case_id', 'technique_id', name='uq_case_mitre'),
        )

    if not _has_table('event_mitre_association'):
        op.create_table(
            'event_mitre_association',
            sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column('event_id', sa.BigInteger, sa.ForeignKey('cases_events.event_id'), nullable=False, index=True),
            sa.Column('technique_id', sa.Integer, sa.ForeignKey('mitre_techniques.id'), nullable=False),
            sa.UniqueConstraint('event_id', 'technique_id', name='uq_event_mitre'),
        )

    if not _has_table('asset_mitre_association'):
        op.create_table(
            'asset_mitre_association',
            sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column('asset_id', sa.BigInteger, sa.ForeignKey('case_assets.asset_id'), nullable=False, index=True),
            sa.Column('technique_id', sa.Integer, sa.ForeignKey('mitre_techniques.id'), nullable=False),
            sa.UniqueConstraint('asset_id', 'technique_id', name='uq_asset_mitre'),
        )

    if not _has_table('ioc_mitre_association'):
        op.create_table(
            'ioc_mitre_association',
            sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
            sa.Column('ioc_id', sa.BigInteger, sa.ForeignKey('ioc.ioc_id'), nullable=False, index=True),
            sa.Column('technique_id', sa.Integer, sa.ForeignKey('mitre_techniques.id'), nullable=False),
            sa.UniqueConstraint('ioc_id', 'technique_id', name='uq_ioc_mitre'),
        )


def downgrade():
    op.drop_table('ioc_mitre_association')
    op.drop_table('asset_mitre_association')
    op.drop_table('event_mitre_association')
    op.drop_table('case_mitre_association')
    op.drop_table('mitre_technique_tactic_map')
    op.drop_table('mitre_techniques')
    op.drop_table('mitre_tactics')
