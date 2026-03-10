"""
MITRE ATT&CK seeder
Loads the enterprise ATT&CK matrix into the database.

Data is fetched automatically from MITRE CTI GitHub on first boot and cached
locally so subsequent restarts never need a network request.
Local cache: source/app/resources/enterprise-attack.json (auto-created)
"""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

MITRE_JSON_PATH = Path(__file__).parent.parent / 'resources' / 'enterprise-attack.json'
MITRE_REMOTE_URL = (
    'https://raw.githubusercontent.com/mitre/cti/master/'
    'enterprise-attack/enterprise-attack.json'
)


def _load_mitre_data():
    """Return the ATT&CK STIX bundle dict.

    Priority:
    1. Local cache (already downloaded)
    2. Auto-download from MITRE CTI GitHub and cache locally
    3. Return None and log a warning if network is unreachable
    """
    if MITRE_JSON_PATH.exists():
        log.info("Loading MITRE ATT&CK from local cache %s", MITRE_JSON_PATH)
        with open(MITRE_JSON_PATH, encoding='utf-8') as f:
            return json.load(f)

    log.info("MITRE ATT&CK cache not found — fetching from %s", MITRE_REMOTE_URL)
    try:
        import requests
        resp = requests.get(MITRE_REMOTE_URL, timeout=120, stream=True)
        resp.raise_for_status()

        MITRE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = MITRE_JSON_PATH.with_suffix('.tmp')
        with open(tmp_path, 'wb') as f:
            for chunk in resp.iter_content(65536):
                f.write(chunk)
        tmp_path.replace(MITRE_JSON_PATH)
        log.info("MITRE ATT&CK bundle saved to %s", MITRE_JSON_PATH)

        with open(MITRE_JSON_PATH, encoding='utf-8') as f:
            return json.load(f)

    except Exception as exc:
        log.warning(
            "Could not fetch MITRE ATT&CK data: %s. "
            "Skipping seeding — will retry on next boot.",
            exc
        )
        return None


def seed_mitre_attack(db_session):
    """Seed/upsert MITRE ATT&CK tactics and techniques.

    Uses upsert logic (match on the stable mitre_id string) so existing
    integer PKs are never changed and FK associations (case/event/asset/ioc)
    are fully preserved across updates.
    """
    from app.models.mitre import MitreTactic, MitreTechnique
    from sqlalchemy import text

    data = _load_mitre_data()
    if data is None:
        log.warning("Skipping MITRE ATT&CK seeding (missing JSON file).")
        return

    objects = data.get('objects', [])

    # -- 1. Upsert tactics (stable key = short_name) --
    tactic_order = [
        'initial-access', 'execution', 'persistence', 'privilege-escalation',
        'defense-evasion', 'credential-access', 'discovery', 'lateral-movement',
        'collection', 'command-and-control', 'exfiltration', 'impact',
        'resource-development', 'reconnaissance'
    ]
    tactic_stix = {
        obj['x_mitre_shortname']: obj
        for obj in objects
        if obj.get('type') == 'x-mitre-tactic'
        and not obj.get('x_mitre_deprecated')
        and not obj.get('revoked')
    }
    ordered_short_names = tactic_order + [s for s in tactic_stix if s not in tactic_order]

    tactic_db_map = {}  # short_name -> MitreTactic
    for idx, short_name in enumerate(ordered_short_names):
        t_obj = tactic_stix.get(short_name)
        if not t_obj:
            continue
        external = next((e for e in t_obj.get('external_references', [])
                         if e.get('source_name') == 'mitre-attack'), {})
        row = db_session.query(MitreTactic).filter_by(short_name=short_name).first()
        if row:
            row.mitre_id = external.get('external_id', short_name.upper())
            row.name = t_obj.get('name', short_name)
            row.description = t_obj.get('description', '')
            row.order = idx
        else:
            row = MitreTactic(
                mitre_id=external.get('external_id', short_name.upper()),
                name=t_obj.get('name', short_name),
                short_name=short_name,
                description=t_obj.get('description', ''),
                order=idx,
            )
            db_session.add(row)
            db_session.flush()
        tactic_db_map[short_name] = row

    db_session.flush()

    # -- 2. Upsert techniques (stable key = mitre_id string e.g. 'T1059') --
    techniques_stix = [
        obj for obj in objects
        if obj.get('type') == 'attack-pattern'
        and not obj.get('x_mitre_deprecated')
        and not obj.get('revoked')
    ]

    technique_db_map = {}  # mitre_id string -> MitreTechnique

    # Parents first so sub-techniques can reference them
    for is_sub in (False, True):
        for t_obj in techniques_stix:
            if bool(t_obj.get('x_mitre_is_subtechnique')) != is_sub:
                continue
            external = next((e for e in t_obj.get('external_references', [])
                             if e.get('source_name') == 'mitre-attack'), {})
            mitre_id = external.get('external_id', '')
            if not mitre_id:
                continue
            parent_id_str = mitre_id.rsplit('.', 1)[0] if '.' in mitre_id else None
            parent_db = technique_db_map.get(parent_id_str) if parent_id_str else None

            row = db_session.query(MitreTechnique).filter_by(mitre_id=mitre_id).first()
            if row:
                row.name = t_obj.get('name', '')
                row.description = t_obj.get('description', '')
                row.is_subtechnique = is_sub
                row.parent_id = parent_db.id if parent_db else None
            else:
                row = MitreTechnique(
                    mitre_id=mitre_id,
                    name=t_obj.get('name', ''),
                    description=t_obj.get('description', ''),
                    is_subtechnique=is_sub,
                    parent_id=parent_db.id if parent_db else None,
                )
                db_session.add(row)
                db_session.flush()
            technique_db_map[mitre_id] = row

    db_session.flush()

    # -- 3. Rebuild tactic<->technique links only for touched techniques --
    touched_ids = [t.id for t in technique_db_map.values()]
    if touched_ids:
        db_session.execute(
            text("DELETE FROM mitre_technique_tactic_map WHERE technique_id = ANY(:ids)"),
            {'ids': touched_ids}
        )
        db_session.flush()

    for t_obj in techniques_stix:
        external = next((e for e in t_obj.get('external_references', [])
                         if e.get('source_name') == 'mitre-attack'), {})
        mitre_id = external.get('external_id', '')
        technique = technique_db_map.get(mitre_id)
        if not technique:
            continue
        for phase in t_obj.get('kill_chain_phases', []):
            if phase.get('kill_chain_name') != 'mitre-attack':
                continue
            tactic = tactic_db_map.get(phase.get('phase_name'))
            if tactic and tactic not in technique.tactics:
                technique.tactics.append(tactic)

    db_session.commit()
    log.info("MITRE ATT&CK seeding complete: %d tactics, %d techniques processed",
             len(tactic_db_map), len(technique_db_map))


def reseed_mitre_attack(db_session):
    """Re-download the ATT&CK bundle and upsert.
    Existing integer PKs are preserved so all case/event/asset/ioc
    associations remain intact.
    """
    if MITRE_JSON_PATH.exists():
        MITRE_JSON_PATH.unlink()
        log.info("Removed local MITRE cache — will re-download")
    seed_mitre_attack(db_session)
    log.info("MITRE ATT&CK reseed complete")
