"""
One-shot script to create MITRE ATT&CK tables and seed data.
Run inside the app container:
    docker exec -w /iriswebapp iriswebapp_app python setup_mitre.py
"""
import sys
import os

# Need Flask app context
sys.path.insert(0, '/iriswebapp')
os.chdir('/iriswebapp')

from app import app, db
from app.models.mitre import (
    MitreTactic, MitreTechnique, CaseMitreAssociation,
    EventMitreAssociation, AssetMitreAssociation, IocMitreAssociation,
    mitre_technique_tactic_map,
)

with app.app_context():
    # 1. Create tables if missing
    print("[1/2] Creating MITRE tables if they don't exist…")
    db.create_all()
    # Also stamp alembic so it doesn't complain on next migration
    from sqlalchemy import text
    with db.engine.connect() as conn:
        # Check current alembic head — add our revisions if not present
        versions = [row[0] for row in conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()]
        print("  Current alembic versions:", versions)
        if 'aaa111000002' not in versions:
            # Remove any existing single-head stamp and insert ours
            # as a merge so both heads are tracked
            if versions:
                conn.execute(text("DELETE FROM alembic_version"))
                conn.commit()
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('aaa111000002')"))
            conn.commit()
            print("  Stamped alembic_version → aaa111000002")

    # 2. Seed MITRE data
    print("[2/2] Seeding MITRE ATT&CK data…")
    from app.datamgmt.mitre.mitre_db import seed_mitre_attack
    seed_mitre_attack(db.session)

    count_tactics = db.session.query(MitreTactic).count()
    count_techniques = db.session.query(MitreTechnique).count()
    print(f"  Done — {count_tactics} tactics, {count_techniques} techniques loaded.")
    print("\nMITRE ATT&CK is ready! Access it at: https://localhost/case/mitre?cid=<your_case_id>")
