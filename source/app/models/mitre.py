from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String, Text, Table, UniqueConstraint
from sqlalchemy.orm import relationship

from app import db

# Many-to-many: techniques <-> tactics
mitre_technique_tactic_map = Table(
    'mitre_technique_tactic_map',
    db.metadata,
    Column('technique_id', Integer, ForeignKey('mitre_techniques.id'), primary_key=True),
    Column('tactic_id', Integer, ForeignKey('mitre_tactics.id'), primary_key=True)
)


class MitreTactic(db.Model):
    __tablename__ = 'mitre_tactics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mitre_id = Column(String(20), unique=True, nullable=False)  # e.g. TA0001
    name = Column(String(100), nullable=False)
    short_name = Column(String(60), nullable=True)  # e.g. initial-access
    description = Column(Text, nullable=True)
    order = Column(Integer, nullable=True)  # column order in matrix

    techniques = relationship(
        'MitreTechnique',
        secondary=mitre_technique_tactic_map,
        back_populates='tactics'
    )


class MitreTechnique(db.Model):
    __tablename__ = 'mitre_techniques'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mitre_id = Column(String(20), unique=True, nullable=False)  # e.g. T1059 or T1059.001
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_subtechnique = Column(Boolean, default=False, nullable=False)
    parent_id = Column(Integer, ForeignKey('mitre_techniques.id'), nullable=True)

    tactics = relationship(
        'MitreTactic',
        secondary=mitre_technique_tactic_map,
        back_populates='techniques'
    )
    subtechniques = relationship(
        'MitreTechnique',
        backref=db.backref('parent', remote_side=[id]),
        foreign_keys=[parent_id]
    )


class CaseMitreAssociation(db.Model):
    __tablename__ = 'case_mitre_association'
    __table_args__ = (UniqueConstraint('case_id', 'technique_id', name='uq_case_mitre'),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    case_id = Column(BigInteger, ForeignKey('cases.case_id'), nullable=False, index=True)
    technique_id = Column(Integer, ForeignKey('mitre_techniques.id'), nullable=False)
    note = Column(Text, nullable=True)

    technique = relationship('MitreTechnique', lazy='joined')


class EventMitreAssociation(db.Model):
    __tablename__ = 'event_mitre_association'
    __table_args__ = (UniqueConstraint('event_id', 'technique_id', name='uq_event_mitre'),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(BigInteger, ForeignKey('cases_events.event_id'), nullable=False, index=True)
    technique_id = Column(Integer, ForeignKey('mitre_techniques.id'), nullable=False)

    technique = relationship('MitreTechnique', lazy='joined')


class AssetMitreAssociation(db.Model):
    __tablename__ = 'asset_mitre_association'
    __table_args__ = (UniqueConstraint('asset_id', 'technique_id', name='uq_asset_mitre'),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    asset_id = Column(BigInteger, ForeignKey('case_assets.asset_id'), nullable=False, index=True)
    technique_id = Column(Integer, ForeignKey('mitre_techniques.id'), nullable=False)

    technique = relationship('MitreTechnique', lazy='joined')


class IocMitreAssociation(db.Model):
    __tablename__ = 'ioc_mitre_association'
    __table_args__ = (UniqueConstraint('ioc_id', 'technique_id', name='uq_ioc_mitre'),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ioc_id = Column(BigInteger, ForeignKey('ioc.ioc_id'), nullable=False, index=True)
    technique_id = Column(Integer, ForeignKey('mitre_techniques.id'), nullable=False)

    technique = relationship('MitreTechnique', lazy='joined')
