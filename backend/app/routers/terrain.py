"""Fonctions de poste : main courante, PTI, consignes, clés, visiteurs, pauses.

Toutes les créations acceptent un identifiant généré par l'appli : un renvoi après une coupure
réseau renvoie l'objet existant au lieu de créer un doublon.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.deps import DB, CurrentUser, Manager
from app.geo import point
from app.journal import journal
from app.models import (
    Alert,
    AlertKind,
    AlertStatus,
    Instruction,
    InstructionAck,
    JournalEntry,
    JournalKind,
    KeyMovement,
    Role,
    Shift,
    ShiftPause,
    ShiftStatus,
    Site,
    SiteKey,
    User,
    Visit,
)
from app.routers.shifts import get_shift_for
from app.schemas_terrain import (
    AckIn,
    AlertAction,
    AlertIn,
    AlertOut,
    InstructionIn,
    InstructionOut,
    JournalIn,
    JournalOut,
    KeyMovementIn,
    KeyMovementOut,
    KeyOut,
    PauseIn,
    PauseOut,
    VisitExit,
    VisitIn,
    VisitOut,
)

router = APIRouter(tags=["poste"])

# Événements « en un geste » proposés à l'agent (Évt simple)
QUICK_EVENTS = [
    {"icon": "✅", "text": "RAS"},
    {"icon": "🚪", "text": "Ouverture du site"},
    {"icon": "🔒", "text": "Fermeture du site"},
    {"icon": "🚧", "text": "Ouverture du portail"},
    {"icon": "⛔", "text": "Fermeture du portail"},
    {"icon": "🚚", "text": "Livraison réceptionnée"},
    {"icon": "🚗", "text": "Passage véhicule autorisé"},
    {"icon": "🔔", "text": "Alarme acquittée"},
    {"icon": "💡", "text": "Éclairage vérifié"},
    {"icon": "📞", "text": "Appel du client"},
    {"icon": "👮", "text": "Passage police / gendarmerie"},
    {"icon": "🧯", "text": "Contrôle des extincteurs"},
]


def get_site_for(db, user: User, site_id: uuid.UUID) -> Site:
    s = db.get(Site, site_id)
    if s is None or s.company_id != user.company_id:
        raise HTTPException(404, "Site introuvable")
    return s


def now() -> datetime:
    return datetime.now(UTC)


# ====================== Main courante ======================
def journal_out(e: JournalEntry) -> JournalOut:
    out = JournalOut.model_validate(e)
    out.agent_name = e.agent.full_name if e.agent else None
    return out


@router.get("/journal/quick-events")
def quick_events(user: CurrentUser):
    return QUICK_EVENTS


@router.get("/journal", response_model=list[JournalOut])
def list_journal(
    db: DB, user: CurrentUser, shift_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    start: datetime | None = None, end: datetime | None = None, limit: int = 200,
):
    q = (
        select(JournalEntry).join(Site, Site.id == JournalEntry.site_id)
        .where(Site.company_id == user.company_id).options(joinedload(JournalEntry.agent))
    )
    if user.role == Role.agent:
        # L'agent voit la main courante de son site (relève comprise) sur les dernières 24 h
        if not site_id and not shift_id:
            raise HTTPException(422, "Précisez la vacation ou le site")
        start = max(start or now() - timedelta(hours=24), now() - timedelta(days=7))
    if shift_id:
        shift = get_shift_for(db, user, shift_id)
        q = q.where(JournalEntry.site_id == shift.site_id)
        start = start or (shift.actual_start or shift.planned_start) - timedelta(hours=12)
    if site_id:
        q = q.where(JournalEntry.site_id == site_id)
    if start:
        q = q.where(JournalEntry.occurred_at >= start)
    if end:
        q = q.where(JournalEntry.occurred_at <= end)
    rows = db.scalars(q.order_by(JournalEntry.occurred_at.desc()).limit(min(limit, 1000))).all()
    return [journal_out(e) for e in rows]


@router.post("/journal", response_model=JournalOut, status_code=201)
def add_journal(db: DB, user: CurrentUser, body: JournalIn):
    if body.id and (existing := db.get(JournalEntry, body.id, options=[joinedload(JournalEntry.agent)])):
        if existing.agent_id != user.id:
            raise HTTPException(409, "Identifiant déjà utilisé")
        return journal_out(existing)
    shift = get_shift_for(db, user, body.shift_id)
    loc = point(body.position.lat, body.position.lon) if body.position else None
    e = journal(db, site_id=shift.site_id, agent_id=user.id, shift_id=shift.id,
                kind=JournalKind(body.kind), text=body.text.strip(), at=body.at, location=loc, entry_id=body.id)
    db.commit()
    db.refresh(e)
    return journal_out(e)


# ====================== PTI / alertes ======================
KIND_LABEL = {
    AlertKind.sos: "Alerte SOS déclenchée",
    AlertKind.immobilite: "Alerte perte de verticalité / immobilité",
    AlertKind.chute: "Alerte chute détectée",
    AlertKind.test: "Test du PTI réussi",
}


def alert_out(db, a: Alert) -> AlertOut:
    out = AlertOut.model_validate(a)
    out.agent_name = a.agent.full_name if a.agent else None
    out.agent_phone = a.agent.phone if a.agent else None
    out.site_name = a.site.name if a.site else None
    if a.handled_by_id:
        h = db.get(User, a.handled_by_id)
        out.handled_by_name = h.full_name if h else None
    return out


def get_alert_for(db, user: User, alert_id: uuid.UUID) -> Alert:
    a = db.get(Alert, alert_id, options=[joinedload(Alert.agent), joinedload(Alert.site)])
    if a is None or a.agent.company_id != user.company_id:
        raise HTTPException(404, "Alerte introuvable")
    if user.role == Role.agent and a.agent_id != user.id:
        raise HTTPException(403, "Accès refusé")
    return a


@router.post("/alerts", response_model=AlertOut, status_code=201)
def raise_alert(db: DB, user: CurrentUser, body: AlertIn):
    if body.id and db.get(Alert, body.id):
        return alert_out(db, get_alert_for(db, user, body.id))
    shift = get_shift_for(db, user, body.shift_id) if body.shift_id else db.scalar(
        select(Shift).where(Shift.agent_id == user.id, Shift.status == ShiftStatus.en_cours)
    )
    loc = point(body.position.lat, body.position.lon) if body.position else None
    at = body.at or now()
    is_test = body.kind == AlertKind.test
    a = Alert(
        id=body.id or uuid.uuid4(), agent_id=user.id, shift_id=shift.id if shift else None,
        site_id=shift.site_id if shift else None, kind=body.kind, triggered_at=at,
        status=AlertStatus.close if is_test else AlertStatus.active, closed_at=at if is_test else None,
        location=loc, accuracy_m=body.position.accuracy_m if body.position else None, note=body.note,
    )
    db.add(a)
    if shift:
        journal(db, site_id=shift.site_id, agent_id=user.id, shift_id=shift.id, kind=JournalKind.alerte,
                text=KIND_LABEL[body.kind], at=at, location=loc, ref_id=a.id)
    db.commit()
    return alert_out(db, get_alert_for(db, user, a.id))


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(db: DB, user: CurrentUser, active: bool = False, include_tests: bool = False, limit: int = 100):
    q = (
        select(Alert).join(User, User.id == Alert.agent_id).where(User.company_id == user.company_id)
        .options(joinedload(Alert.agent), joinedload(Alert.site))
    )
    if user.role == Role.agent:
        q = q.where(Alert.agent_id == user.id)
    if active:
        q = q.where(Alert.status.in_([AlertStatus.active, AlertStatus.prise_en_charge]))
    if not include_tests:
        q = q.where(Alert.kind != AlertKind.test)
    return [alert_out(db, a) for a in db.scalars(q.order_by(Alert.triggered_at.desc()).limit(min(limit, 500)))]


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(db: DB, user: CurrentUser, alert_id: uuid.UUID):
    return alert_out(db, get_alert_for(db, user, alert_id))


@router.post("/alerts/{alert_id}/cancel", response_model=AlertOut)
def cancel_alert(db: DB, user: CurrentUser, alert_id: uuid.UUID, body: AlertAction):
    """Fausse alerte annulée par l'agent lui-même."""
    a = get_alert_for(db, user, alert_id)
    if a.agent_id != user.id:
        raise HTTPException(403, "Seul l'agent peut annuler sa propre alerte")
    if a.status in (AlertStatus.active, AlertStatus.prise_en_charge):
        a.status, a.closed_at = AlertStatus.annulee, now()
        a.note = ((a.note or "") + f"\nAnnulée par l'agent : {body.note or 'fausse alerte'}").strip()
        if a.site_id:
            journal(db, site_id=a.site_id, agent_id=user.id, shift_id=a.shift_id, kind=JournalKind.alerte,
                    text="Alerte PTI annulée par l'agent (fausse alerte)", ref_id=a.id)
        db.commit()
    return alert_out(db, a)


@router.post("/alerts/{alert_id}/handle", response_model=AlertOut)
def handle_alert(db: DB, user: Manager, alert_id: uuid.UUID, body: AlertAction):
    a = get_alert_for(db, user, alert_id)
    if a.status == AlertStatus.active:
        a.status, a.handled_by_id, a.handled_at = AlertStatus.prise_en_charge, user.id, now()
        if body.note:
            a.note = ((a.note or "") + f"\n{body.note}").strip()
        db.commit()
    return alert_out(db, a)


@router.post("/alerts/{alert_id}/close", response_model=AlertOut)
def close_alert(db: DB, user: Manager, alert_id: uuid.UUID, body: AlertAction):
    a = get_alert_for(db, user, alert_id)
    if a.status in (AlertStatus.active, AlertStatus.prise_en_charge):
        a.status, a.closed_at = AlertStatus.close, now()
        a.handled_by_id = a.handled_by_id or user.id
        a.handled_at = a.handled_at or now()
        if body.note:
            a.note = ((a.note or "") + f"\nClôture : {body.note}").strip()
        db.commit()
    return alert_out(db, a)


# ====================== Consignes ======================
@router.get("/instructions", response_model=list[InstructionOut])
def list_instructions(db: DB, user: CurrentUser, site_id: uuid.UUID, include_expired: bool = False):
    get_site_for(db, user, site_id)
    q = select(Instruction).where(Instruction.site_id == site_id)
    if not include_expired:
        t = now()
        q = q.where(
            or_(Instruction.valid_from.is_(None), Instruction.valid_from <= t),
            or_(Instruction.valid_to.is_(None), Instruction.valid_to >= t),
        )
    rows = db.scalars(q.order_by(Instruction.important.desc(), Instruction.created_at.desc())).all()
    acks = dict(db.execute(
        select(InstructionAck.instruction_id, InstructionAck.acked_at)
        .where(InstructionAck.user_id == user.id, InstructionAck.instruction_id.in_([r.id for r in rows]))
    ).all()) if rows else {}
    out = []
    for r in rows:
        o = InstructionOut.model_validate(r)
        o.acked_at = acks.get(r.id)
        out.append(o)
    return out


@router.post("/instructions", response_model=InstructionOut, status_code=201)
def create_instruction(db: DB, user: Manager, body: InstructionIn):
    get_site_for(db, user, body.site_id)
    i = Instruction(**body.model_dump(), author_id=user.id)
    db.add(i)
    db.commit()
    return InstructionOut.model_validate(i)


@router.post("/instructions/{instruction_id}/ack", response_model=InstructionOut)
def ack_instruction(db: DB, user: CurrentUser, instruction_id: uuid.UUID, body: AckIn):
    i = db.get(Instruction, instruction_id)
    if i is None:
        raise HTTPException(404, "Consigne introuvable")
    get_site_for(db, user, i.site_id)
    ack = db.get(InstructionAck, (i.id, user.id))
    if ack is None:
        ack = InstructionAck(instruction_id=i.id, user_id=user.id, acked_at=body.at or now())
        db.add(ack)
        journal(db, site_id=i.site_id, agent_id=user.id, shift_id=body.shift_id, kind=JournalKind.consigne,
                text=f"Consigne lue et validée : « {i.title} »", at=ack.acked_at, ref_id=i.id)
        db.commit()
    o = InstructionOut.model_validate(i)
    o.acked_at = ack.acked_at
    return o


# ====================== Clés ======================
def key_out(k: SiteKey) -> KeyOut:
    o = KeyOut.model_validate(k)
    last = k.movements[-1] if k.movements else None
    if last and last.action == "sortie":
        o.is_out, o.holder_name, o.holder_company, o.since = True, last.holder_name, last.holder_company, last.at
    elif last:
        o.since = last.at
    return o


@router.get("/keys", response_model=list[KeyOut])
def list_keys(db: DB, user: CurrentUser, site_id: uuid.UUID):
    get_site_for(db, user, site_id)
    return [key_out(k) for k in db.scalars(select(SiteKey).where(SiteKey.site_id == site_id).order_by(SiteKey.label))]


@router.get("/keys/{key_id}/movements", response_model=list[KeyMovementOut])
def key_movements(db: DB, user: CurrentUser, key_id: uuid.UUID):
    k = db.get(SiteKey, key_id)
    if k is None:
        raise HTTPException(404, "Clé introuvable")
    get_site_for(db, user, k.site_id)
    return list(reversed(k.movements))[:50]


@router.post("/keys/{key_id}/movements", response_model=KeyOut, status_code=201)
def move_key(db: DB, user: CurrentUser, key_id: uuid.UUID, body: KeyMovementIn):
    k = db.get(SiteKey, key_id)
    if k is None:
        raise HTTPException(404, "Clé introuvable")
    get_site_for(db, user, k.site_id)
    if body.id and db.get(KeyMovement, body.id):
        return key_out(k)  # renvoi hors-ligne
    out_now = bool(k.movements) and k.movements[-1].action == "sortie"
    if body.action == "sortie" and out_now:
        raise HTTPException(409, f"Clé déjà sortie (détenue par {k.movements[-1].holder_name})")
    if body.action == "retour" and not out_now:
        raise HTTPException(409, "Cette clé est déjà au poste")
    m = KeyMovement(
        id=body.id or uuid.uuid4(), key_id=k.id, agent_id=user.id, shift_id=body.shift_id, action=body.action,
        holder_name=body.holder_name.strip(), holder_company=body.holder_company, at=body.at or now(), note=body.note,
    )
    k.movements.append(m)
    who = m.holder_name + (f" ({m.holder_company})" if m.holder_company else "")
    journal(db, site_id=k.site_id, agent_id=user.id, shift_id=body.shift_id, kind=JournalKind.clef,
            text=f"Clé « {k.label} » {'remise à' if body.action == 'sortie' else 'rendue par'} {who}",
            at=m.at, ref_id=k.id)
    db.commit()
    db.refresh(k)
    return key_out(k)


# ====================== Visiteurs ======================
@router.get("/visits", response_model=list[VisitOut])
def list_visits(db: DB, user: CurrentUser, site_id: uuid.UUID, present: bool = False, limit: int = 100):
    get_site_for(db, user, site_id)
    q = select(Visit).where(Visit.site_id == site_id)
    if present:
        q = q.where(Visit.left_at.is_(None))
    else:
        q = q.where(Visit.arrived_at >= now() - timedelta(days=7))
    return db.scalars(q.order_by(Visit.arrived_at.desc()).limit(min(limit, 500))).all()


@router.post("/visits", response_model=VisitOut, status_code=201)
def add_visit(db: DB, user: CurrentUser, body: VisitIn):
    if body.id and (existing := db.get(Visit, body.id)):
        return existing
    get_site_for(db, user, body.site_id)
    v = Visit(id=body.id or uuid.uuid4(), agent_id=user.id, arrived_at=body.at or now(),
              **body.model_dump(exclude={"id", "at"}))
    db.add(v)
    detail = ", ".join(x for x in [v.company, f"véhicule {v.vehicle_plate}" if v.vehicle_plate else None,
                                   f"pour {v.host_name}" if v.host_name else None] if x)
    journal(db, site_id=v.site_id, agent_id=user.id, shift_id=v.shift_id, kind=JournalKind.visiteur,
            text=f"Arrivée visiteur : {v.visitor_name}" + (f" ({detail})" if detail else ""), at=v.arrived_at, ref_id=v.id)
    db.commit()
    return v


@router.post("/visits/{visit_id}/exit", response_model=VisitOut)
def exit_visit(db: DB, user: CurrentUser, visit_id: uuid.UUID, body: VisitExit):
    v = db.get(Visit, visit_id)
    if v is None:
        raise HTTPException(404, "Visite introuvable")
    get_site_for(db, user, v.site_id)
    if v.left_at is None:
        v.left_at = body.at or now()
        journal(db, site_id=v.site_id, agent_id=user.id, shift_id=v.shift_id, kind=JournalKind.visiteur,
                text=f"Départ visiteur : {v.visitor_name}", at=v.left_at, ref_id=v.id)
        db.commit()
    return v


# ====================== Pauses ======================
@router.post("/shifts/{shift_id}/pauses", response_model=PauseOut, status_code=201)
def start_pause(db: DB, user: CurrentUser, shift_id: uuid.UUID, body: PauseIn):
    shift = get_shift_for(db, user, shift_id)
    if body.id and (existing := db.get(ShiftPause, body.id)):
        return existing
    if shift.status != ShiftStatus.en_cours:
        raise HTTPException(409, "La vacation n'est pas en cours")
    if db.scalar(select(ShiftPause).where(ShiftPause.shift_id == shift.id, ShiftPause.ended_at.is_(None))):
        raise HTTPException(409, "Une pause est déjà en cours")
    p = ShiftPause(id=body.id or uuid.uuid4(), shift_id=shift.id, started_at=body.at or now())
    db.add(p)
    journal(db, site_id=shift.site_id, agent_id=user.id, shift_id=shift.id, kind=JournalKind.pause,
            text="Début de pause", at=p.started_at, ref_id=p.id)
    db.commit()
    return p


@router.post("/shifts/{shift_id}/pauses/{pause_id}/end", response_model=PauseOut)
def end_pause(db: DB, user: CurrentUser, shift_id: uuid.UUID, pause_id: uuid.UUID, body: PauseIn):
    shift = get_shift_for(db, user, shift_id)
    p = db.get(ShiftPause, pause_id)
    if p is None or p.shift_id != shift.id:
        raise HTTPException(404, "Pause introuvable")
    if p.ended_at is None:
        p.ended_at = body.at or now()
        minutes = round((p.ended_at - p.started_at).total_seconds() / 60)
        journal(db, site_id=shift.site_id, agent_id=user.id, shift_id=shift.id, kind=JournalKind.pause,
                text=f"Fin de pause ({minutes} min)", at=p.ended_at, ref_id=p.id)
        db.commit()
    return p


@router.get("/shifts/{shift_id}/pauses", response_model=list[PauseOut])
def list_pauses(db: DB, user: CurrentUser, shift_id: uuid.UUID):
    shift = get_shift_for(db, user, shift_id)
    return db.scalars(select(ShiftPause).where(ShiftPause.shift_id == shift.id).order_by(ShiftPause.started_at)).all()


@router.get("/poste/summary")
def poste_summary(db: DB, user: CurrentUser, site_id: uuid.UUID):
    """Compteurs pour l'accueil de l'appli (badges des tuiles)."""
    get_site_for(db, user, site_id)
    t = now()
    instr = db.scalars(select(Instruction.id).where(
        Instruction.site_id == site_id,
        or_(Instruction.valid_from.is_(None), Instruction.valid_from <= t),
        or_(Instruction.valid_to.is_(None), Instruction.valid_to >= t),
    )).all()
    acked = db.scalar(select(func.count()).select_from(InstructionAck).where(
        InstructionAck.user_id == user.id, InstructionAck.instruction_id.in_(instr))) if instr else 0
    keys = list_keys(db, user, site_id)
    return {
        "instructions_unread": len(instr) - (acked or 0),
        "keys_out": sum(k.is_out for k in keys),
        "visitors_present": db.scalar(select(func.count()).select_from(Visit).where(
            Visit.site_id == site_id, Visit.left_at.is_(None))) or 0,
    }
