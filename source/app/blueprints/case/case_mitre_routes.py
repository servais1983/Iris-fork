#  IRIS Source Code
#  MITRE ATT&CK Integration

from flask import Blueprint, request
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.orm import joinedload

from app import db
from app.models.mitre import (
    MitreTactic,
    MitreTechnique,
    CaseMitreAssociation,
    EventMitreAssociation,
    AssetMitreAssociation,
    IocMitreAssociation,
)
from app.models.authorization import CaseAccessLevel, Permissions
from app.util import ac_api_case_requires, ac_api_requires, ac_case_requires, response_success, response_error

mitre_blueprint = Blueprint('mitre', __name__, template_folder='templates')


# ---------------------------------------------------------------------------
# Admin – update ATT&CK data
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/mitre/admin/update', methods=['POST'])
@ac_api_requires(Permissions.server_administrator)
def mitre_admin_update():
    """Re-download and re-seed the MITRE ATT&CK bundle. Admin-only."""
    from app.datamgmt.mitre.mitre_db import reseed_mitre_attack

    try:
        reseed_mitre_attack(db.session)
        from app.models.mitre import MitreTactic, MitreTechnique
        count_t = db.session.query(MitreTactic).count()
        count_tech = db.session.query(MitreTechnique).count()
        return response_success(
            f'ATT&CK updated: {count_t} tactics, {count_tech} techniques',
            data={'tactics': count_t, 'techniques': count_tech}
        )
    except Exception as exc:
        db.session.rollback()
        return response_error(f'Update failed: {exc}', status=500)


# ---------------------------------------------------------------------------
# Matrix – public data (no case context needed)
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/mitre/tactics', methods=['GET'])
@login_required
def mitre_list_tactics():
    """Return all tactics ordered by matrix column."""
    tactics = MitreTactic.query.order_by(MitreTactic.order).all()
    return response_success("Tactics fetched", [
        {'id': t.id, 'mitre_id': t.mitre_id, 'name': t.name,
         'short_name': t.short_name, 'order': t.order}
        for t in tactics
    ])


@mitre_blueprint.route('/mitre/techniques', methods=['GET'])
@login_required
def mitre_list_techniques():
    """Return all techniques, optionally filtered by tactic short_name."""
    tactic_filter = request.args.get('tactic')
    query = MitreTechnique.query

    if tactic_filter:
        query = (
            query
            .join(MitreTechnique.tactics)
            .filter(MitreTactic.short_name == tactic_filter)
        )

    techniques = query.order_by(MitreTechnique.mitre_id).all()
    return response_success("Techniques fetched", [
        {
            'id': t.id,
            'mitre_id': t.mitre_id,
            'name': t.name,
            'is_subtechnique': t.is_subtechnique,
            'parent_id': t.parent_id,
            'tactics': [{'id': tac.id, 'name': tac.name, 'short_name': tac.short_name} for tac in t.tactics],
        }
        for t in techniques
    ])


@mitre_blueprint.route('/mitre/matrix', methods=['GET'])
@login_required
def mitre_matrix():
    """Return the full matrix: tactics with their techniques grouped."""
    tactics = (
        MitreTactic.query
        .options(joinedload(MitreTactic.techniques).joinedload(MitreTechnique.subtechniques))
        .order_by(MitreTactic.order)
        .all()
    )
    result = []
    for tac in tactics:
        parents = [t for t in tac.techniques if not t.is_subtechnique]
        tactic_data = {
            'id': tac.id,
            'mitre_id': tac.mitre_id,
            'name': tac.name,
            'short_name': tac.short_name,
            'order': tac.order,
            'techniques': []
        }
        for tech in sorted(parents, key=lambda x: x.mitre_id):
            subs = [
                {'id': s.id, 'mitre_id': s.mitre_id, 'name': s.name}
                for s in sorted(tech.subtechniques, key=lambda x: x.mitre_id)
            ]
            tactic_data['techniques'].append({
                'id': tech.id,
                'mitre_id': tech.mitre_id,
                'name': tech.name,
                'subtechniques': subs,
            })
        result.append(tactic_data)
    return response_success("Matrix fetched", result)


@mitre_blueprint.route('/mitre/technique/<int:tech_id>', methods=['GET'])
@login_required
def mitre_technique_detail(tech_id):
    """Return full details for a single technique including description, URL, parent and sub-techniques."""
    tech = MitreTechnique.query.get(tech_id)
    if not tech:
        return response_error("Technique not found", status=404)
    mitre_url = 'https://attack.mitre.org/techniques/' + tech.mitre_id.replace('.', '/')
    return response_success("Technique detail", {
        'id': tech.id,
        'mitre_id': tech.mitre_id,
        'name': tech.name,
        'description': tech.description or '',
        'is_subtechnique': tech.is_subtechnique,
        'parent': (
            {'id': tech.parent.id, 'mitre_id': tech.parent.mitre_id, 'name': tech.parent.name}
            if tech.parent else None
        ),
        'subtechniques': [
            {'id': s.id, 'mitre_id': s.mitre_id, 'name': s.name}
            for s in sorted(tech.subtechniques, key=lambda x: x.mitre_id)
        ],
        'tactics': [
            {'id': t.id, 'mitre_id': t.mitre_id, 'name': t.name, 'short_name': t.short_name}
            for t in tech.tactics
        ],
        'url': mitre_url,
    })


@mitre_blueprint.route('/mitre/techniques/search', methods=['GET'])
@login_required
def mitre_search_techniques():
    """Full-text search by name or MITRE ID."""
    q = request.args.get('q', '').strip()
    if not q:
        return response_error("Missing query parameter 'q'", status=400)
    like = f'%{q}%'
    results = (
        MitreTechnique.query
        .filter(
            db.or_(
                MitreTechnique.name.ilike(like),
                MitreTechnique.mitre_id.ilike(like)
            )
        )
        .order_by(MitreTechnique.mitre_id)
        .limit(50)
        .all()
    )
    return response_success("Search results", [
        {
            'id': t.id,
            'mitre_id': t.mitre_id,
            'name': t.name,
            'is_subtechnique': t.is_subtechnique,
            'tactics': [tac.name for tac in t.tactics],
        }
        for t in results
    ])


# ---------------------------------------------------------------------------
# Case ↔ TTP
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/case/mitre/list', methods=['GET'])
@ac_api_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def case_mitre_list(caseid):
    rows = CaseMitreAssociation.query.filter_by(case_id=caseid).all()
    return response_success("Case MITRE techniques", [
        {
            'id': r.id,
            'technique_id': r.technique_id,
            'mitre_id': r.technique.mitre_id,
            'name': r.technique.name,
            'is_subtechnique': r.technique.is_subtechnique,
            'tactics': [t.name for t in r.technique.tactics],
            'note': r.note,
        }
        for r in rows
    ])


@mitre_blueprint.route('/case/mitre/add', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def case_mitre_add(caseid):
    data = request.get_json(force=True, silent=True) or {}
    technique_id = data.get('technique_id')
    if not technique_id:
        return response_error("technique_id is required", status=400)
    tech = MitreTechnique.query.get(technique_id)
    if not tech:
        return response_error("Technique not found", status=404)
    existing = CaseMitreAssociation.query.filter_by(case_id=caseid, technique_id=technique_id).first()
    if existing:
        return response_error("Technique already linked to this case", status=409)
    assoc = CaseMitreAssociation(case_id=caseid, technique_id=technique_id, note=data.get('note'))
    db.session.add(assoc)
    db.session.commit()
    return response_success("Technique linked to case", {'id': assoc.id})


@mitre_blueprint.route('/case/mitre/delete/<int:assoc_id>', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def case_mitre_delete(caseid, assoc_id):
    assoc = CaseMitreAssociation.query.filter_by(id=assoc_id, case_id=caseid).first()
    if not assoc:
        return response_error("Association not found", status=404)
    db.session.delete(assoc)
    db.session.commit()
    return response_success("Technique unlinked from case", {})


# ---------------------------------------------------------------------------
# Event ↔ TTP
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/case/timeline/events/<int:event_id>/mitre/list', methods=['GET'])
@ac_api_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def event_mitre_list(caseid, event_id):
    rows = EventMitreAssociation.query.filter_by(event_id=event_id).all()
    return response_success("Event MITRE techniques", [
        {
            'id': r.id,
            'technique_id': r.technique_id,
            'mitre_id': r.technique.mitre_id,
            'name': r.technique.name,
            'tactics': [t.name for t in r.technique.tactics],
        }
        for r in rows
    ])


@mitre_blueprint.route('/case/timeline/events/<int:event_id>/mitre/add', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def event_mitre_add(caseid, event_id):
    data = request.get_json(force=True, silent=True) or {}
    technique_id = data.get('technique_id')
    if not technique_id:
        return response_error("technique_id is required", status=400)
    tech = MitreTechnique.query.get(technique_id)
    if not tech:
        return response_error("Technique not found", status=404)
    existing = EventMitreAssociation.query.filter_by(event_id=event_id, technique_id=technique_id).first()
    if existing:
        return response_error("Technique already linked to this event", status=409)
    assoc = EventMitreAssociation(event_id=event_id, technique_id=technique_id)
    db.session.add(assoc)
    db.session.commit()
    return response_success("Technique linked to event", {'id': assoc.id})


@mitre_blueprint.route('/case/timeline/events/<int:event_id>/mitre/delete/<int:assoc_id>', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def event_mitre_delete(caseid, event_id, assoc_id):
    assoc = EventMitreAssociation.query.filter_by(id=assoc_id, event_id=event_id).first()
    if not assoc:
        return response_error("Association not found", status=404)
    db.session.delete(assoc)
    db.session.commit()
    return response_success("Technique unlinked from event", {})


# ---------------------------------------------------------------------------
# Asset ↔ TTP
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/case/assets/<int:asset_id>/mitre/list', methods=['GET'])
@ac_api_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def asset_mitre_list(caseid, asset_id):
    rows = AssetMitreAssociation.query.filter_by(asset_id=asset_id).all()
    return response_success("Asset MITRE techniques", [
        {
            'id': r.id,
            'technique_id': r.technique_id,
            'mitre_id': r.technique.mitre_id,
            'name': r.technique.name,
            'tactics': [t.name for t in r.technique.tactics],
        }
        for r in rows
    ])


@mitre_blueprint.route('/case/assets/<int:asset_id>/mitre/add', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def asset_mitre_add(caseid, asset_id):
    data = request.get_json(force=True, silent=True) or {}
    technique_id = data.get('technique_id')
    if not technique_id:
        return response_error("technique_id is required", status=400)
    tech = MitreTechnique.query.get(technique_id)
    if not tech:
        return response_error("Technique not found", status=404)
    existing = AssetMitreAssociation.query.filter_by(asset_id=asset_id, technique_id=technique_id).first()
    if existing:
        return response_error("Technique already linked to this asset", status=409)
    assoc = AssetMitreAssociation(asset_id=asset_id, technique_id=technique_id)
    db.session.add(assoc)
    db.session.commit()
    return response_success("Technique linked to asset", {'id': assoc.id})


@mitre_blueprint.route('/case/assets/<int:asset_id>/mitre/delete/<int:assoc_id>', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def asset_mitre_delete(caseid, asset_id, assoc_id):
    assoc = AssetMitreAssociation.query.filter_by(id=assoc_id, asset_id=asset_id).first()
    if not assoc:
        return response_error("Association not found", status=404)
    db.session.delete(assoc)
    db.session.commit()
    return response_success("Technique unlinked from asset", {})


# ---------------------------------------------------------------------------
# IOC ↔ TTP
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/case/ioc/<int:ioc_id>/mitre/list', methods=['GET'])
@ac_api_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def ioc_mitre_list(caseid, ioc_id):
    rows = IocMitreAssociation.query.filter_by(ioc_id=ioc_id).all()
    return response_success("IOC MITRE techniques", [
        {
            'id': r.id,
            'technique_id': r.technique_id,
            'mitre_id': r.technique.mitre_id,
            'name': r.technique.name,
            'tactics': [t.name for t in r.technique.tactics],
        }
        for r in rows
    ])


@mitre_blueprint.route('/case/ioc/<int:ioc_id>/mitre/add', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def ioc_mitre_add(caseid, ioc_id):
    data = request.get_json(force=True, silent=True) or {}
    technique_id = data.get('technique_id')
    if not technique_id:
        return response_error("technique_id is required", status=400)
    tech = MitreTechnique.query.get(technique_id)
    if not tech:
        return response_error("Technique not found", status=404)
    existing = IocMitreAssociation.query.filter_by(ioc_id=ioc_id, technique_id=technique_id).first()
    if existing:
        return response_error("Technique already linked to this IOC", status=409)
    assoc = IocMitreAssociation(ioc_id=ioc_id, technique_id=technique_id)
    db.session.add(assoc)
    db.session.commit()
    return response_success("Technique linked to IOC", {'id': assoc.id})


@mitre_blueprint.route('/case/ioc/<int:ioc_id>/mitre/delete/<int:assoc_id>', methods=['POST'])
@ac_api_case_requires(CaseAccessLevel.full_access)
def ioc_mitre_delete(caseid, ioc_id, assoc_id):
    assoc = IocMitreAssociation.query.filter_by(id=assoc_id, ioc_id=ioc_id).first()
    if not assoc:
        return response_error("Association not found", status=404)
    db.session.delete(assoc)
    db.session.commit()
    return response_success("Technique unlinked from IOC", {})


# ---------------------------------------------------------------------------
# Case MITRE matrix view (HTML page)
# ---------------------------------------------------------------------------

@mitre_blueprint.route('/case/mitre', methods=['GET'])
@ac_case_requires(CaseAccessLevel.read_only, CaseAccessLevel.full_access)
def case_mitre_page(caseid, url_redir):
    """Return an HTML page showing the ATT&CK navigator-style matrix for a case."""
    from flask import render_template, session, redirect, url_for
    if url_redir:
        return redirect(url_for('mitre.case_mitre_page', cid=caseid, redirect=True))
    case_techniques = {
        row.technique_id
        for row in CaseMitreAssociation.query.filter_by(case_id=caseid).all()
    }
    tactics = MitreTactic.query.order_by(MitreTactic.order).all()
    form = FlaskForm()
    return render_template(
        'case_mitre.html',
        case=session.get('current_case'),
        tactics=tactics,
        case_technique_ids=case_techniques,
        caseid=caseid,
        form=form,
    )
