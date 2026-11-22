import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.geo import distance_m, geojson, latlon, point
from app.models import (
    Checkpoint,
    CheckpointScan,
    PositionPing,
    Role,
    RoundRun,
    RoundStatus,
    RoundTemplate,
    Shift,
    ShiftStatus,
    User,
)
from app.routers.shifts import get_shift_for
from app.schemas import (
    CheckpointReport,
    RoundEnd,
    RoundOut,
    RoundReport,
    RoundStart,
    ScanIn,
    ScanOut,
)

router = APIRouter(prefix="/rounds", tags=["rondes"])


def scan_out(sc: CheckpointScan) -> ScanOut:
    out = ScanOut.model_validate(sc)
    out.checkpoint_name = sc.checkpoint.name if sc.checkpoint else None
    return out


def round_out(r: RoundRun) -> RoundOut:
    out = RoundOut.model_validate(r, from_attributes=True)
    out.scans = [scan_out(s) for s in r.scans]
    return out


def get_round_for(db, user: User, round_id: uuid.UUID) -> RoundRun:
    r = db.get(
        RoundRun, round_id,
        options=[selectinload(RoundRun.scans).selectinload(CheckpointScan.checkpoint)],
    )
    if r is None:
        raise HTTPException(404, "Ronde introuvable")
    get_shift_for(db, user, r.shift_id)  # contrôle société + propriétaire
    return r


@router.get("", response_model=list[RoundOut])
def list_rounds(
    db: DB, user: CurrentUser, shift_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    start: datetime | None = None, end: datetime | None = None, limit: int = 100,
):
    q = (
        select(RoundRun).join(Shift, Shift.id == RoundRun.shift_id).join(User, User.id == RoundRun.agent_id)
        .where(User.company_id == user.company_id)
        .options(selectinload(RoundRun.scans).selectinload(CheckpointScan.checkpoint))
    )
    if user.role == Role.agent:
        q = q.where(RoundRun.agent_id == user.id)
    elif agent_id:
        q = q.where(RoundRun.agent_id == agent_id)
    if shift_id:
        q = q.where(RoundRun.shift_id == shift_id)
    if site_id:
        q = q.where(Shift.site_id == site_id)
    if start:
        q = q.where(RoundRun.started_at >= start)
    if end:
        q = q.where(RoundRun.started_at <= end)
    rounds = db.scalars(q.order_by(RoundRun.started_at.desc()).limit(min(limit, 500))).all()
    return [round_out(r) for r in rounds]


@router.post("", response_model=RoundOut, status_code=201)
def start_round(db: DB, user: CurrentUser, body: RoundStart):
    shift = get_shift_for(db, user, body.shift_id)
    if body.id and (existing := db.get(RoundRun, body.id)):
        if existing.shift_id != shift.id:
            raise HTTPException(409, "Identifiant de ronde déjà utilisé")
        return round_out(get_round_for(db, user, existing.id))  # renvoi hors-ligne : idempotent
    if shift.status != ShiftStatus.en_cours:
        raise HTTPException(409, "Commencez d'abord votre vacation")
    tpl = db.get(RoundTemplate, body.template_id)
    if tpl is None or tpl.site_id != shift.site_id:
        raise HTTPException(422, "Ce parcours ne correspond pas au site de la vacation")
    if db.scalar(select(RoundRun).where(RoundRun.shift_id == shift.id, RoundRun.status == RoundStatus.en_cours)):
        raise HTTPException(409, "Une ronde est déjà en cours")
    r = RoundRun(
        id=body.id or uuid.uuid4(), shift_id=shift.id, template_id=tpl.id, agent_id=shift.agent_id,
        started_at=body.at or datetime.now(UTC),
    )
    db.add(r)
    db.commit()
    return round_out(get_round_for(db, user, r.id))


@router.get("/{round_id}", response_model=RoundOut)
def get_round(db: DB, user: CurrentUser, round_id: uuid.UUID):
    return round_out(get_round_for(db, user, round_id))


@router.post("/{round_id}/scan", response_model=ScanOut, status_code=201)
def scan_checkpoint(db: DB, user: CurrentUser, round_id: uuid.UUID, body: ScanIn):
    r = get_round_for(db, user, round_id)
    if body.id and (existing := db.get(CheckpointScan, body.id)):
        if existing.round_id != r.id:
            raise HTTPException(409, "Identifiant de scan déjà utilisé")
        return scan_out(existing)  # renvoi hors-ligne : idempotent
    if r.status != RoundStatus.en_cours:
        raise HTTPException(409, "La ronde est terminée")
    cp = db.scalar(select(Checkpoint).where(Checkpoint.code == body.code))
    tpl = db.get(RoundTemplate, r.template_id)
    if cp is None or cp.id not in tpl.checkpoint_ids:
        raise HTTPException(422, "Ce point de contrôle ne fait pas partie de la ronde")
    loc = point(body.position.lat, body.position.lon) if body.position else None
    dist = distance_m(db, cp.location, loc)
    max_d = get_settings().checkpoint_max_distance_m
    accuracy = body.position.accuracy_m if body.position and body.position.accuracy_m else 0
    # Scan valide si la position est proche du point (en tenant compte de la précision GPS).
    # Sans position (GPS indisponible), le scan est accepté mais signalé.
    is_valid = dist is None or dist <= max_d + min(accuracy, 50)
    sc = CheckpointScan(
        id=body.id or uuid.uuid4(), round_id=r.id, checkpoint_id=cp.id, scanned_at=body.at or datetime.now(UTC),
        location=loc, distance_m=dist, method=body.method, is_valid=is_valid,
        note=body.note if dist is not None else ((body.note or "") + " [sans position GPS]").strip(),
    )
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return scan_out(sc)


@router.post("/{round_id}/end", response_model=RoundOut)
def end_round(db: DB, user: CurrentUser, round_id: uuid.UUID, body: RoundEnd):
    r = get_round_for(db, user, round_id)
    if r.status != RoundStatus.en_cours:
        raise HTTPException(409, "La ronde est déjà terminée")
    r.ended_at = body.at or datetime.now(UTC)
    r.status = RoundStatus.interrompue if body.interrupted else RoundStatus.terminee
    r.comment = body.comment
    db.commit()
    return round_out(get_round_for(db, user, r.id))


@router.get("/{round_id}/report", response_model=RoundReport)
def round_report(db: DB, user: CurrentUser, round_id: uuid.UUID):
    """Rapport de ronde : points passés/manqués, horaires, distances, trajet GPS et alertes."""
    r = get_round_for(db, user, round_id)
    shift = get_shift_for(db, user, r.shift_id)
    tpl = db.get(RoundTemplate, r.template_id)
    cps = {c.id: c for c in db.scalars(select(Checkpoint).where(Checkpoint.id.in_(tpl.checkpoint_ids)))}

    first_scan: dict[uuid.UUID, CheckpointScan] = {}
    for sc in r.scans:
        prev = first_scan.get(sc.checkpoint_id)
        if prev is None or (not prev.is_valid and sc.is_valid):
            first_scan[sc.checkpoint_id] = sc

    rows, missed = [], []
    for idx, cid in enumerate(tpl.checkpoint_ids):
        c = cps.get(cid)
        if c is None:
            continue
        sc = first_scan.get(cid)
        if sc is None:
            missed.append(c.name)
        rows.append(CheckpointReport(
            checkpoint_id=cid, name=c.name, order_index=idx, location=latlon(c.location),
            scanned=sc is not None,
            scanned_at=sc.scanned_at if sc else None,
            distance_m=round(sc.distance_m, 1) if sc and sc.distance_m is not None else None,
            is_valid=sc.is_valid if sc else None,
            minutes_since_start=round((sc.scanned_at - r.started_at).total_seconds() / 60, 1) if sc else None,
        ))

    # Ordre de passage respecté ?
    order = {cid: i for i, cid in enumerate(tpl.checkpoint_ids)}
    seq = [order[s.checkpoint_id] for s in sorted(first_scan.values(), key=lambda s: s.scanned_at)]
    out_of_order = seq != sorted(seq)

    # Trajet GPS de la ronde (positions rattachées à la ronde, ou à défaut à la vacation pendant la ronde)
    end_at = r.ended_at or datetime.now(UTC)
    pos_filter = (
        (PositionPing.round_id == r.id)
        | ((PositionPing.shift_id == r.shift_id) & PositionPing.recorded_at.between(r.started_at, end_at))
    )
    line = (
        select(
            func.ST_MakeLine(aggregate_order_by(PositionPing.location, PositionPing.recorded_at)).label("geom"),
            func.count().label("n"),
        )
        .where(pos_filter)
        .subquery()
    )
    track_json, walked, n_points = db.execute(
        select(func.ST_AsGeoJSON(line.c.geom), func.ST_Length(func.Geography(line.c.geom)), line.c.n)
    ).one()
    n_points = n_points or 0
    track = track_json if n_points >= 2 else None
    walked = walked if n_points >= 2 else None

    duration = (r.ended_at - r.started_at).total_seconds() / 60 if r.ended_at else None
    completion = 100 * (len(rows) - len(missed)) / len(rows) if rows else 0.0

    flags = []
    if missed:
        flags.append(f"{len(missed)} point(s) de contrôle manqué(s)")
    if any(row.is_valid is False for row in rows):
        flags.append("Scan effectué loin du point de contrôle")
    if out_of_order:
        flags.append("Ordre du parcours non respecté")
    if duration is not None and duration < 0.4 * tpl.expected_duration_min:
        flags.append("Ronde anormalement rapide")
    if duration is not None and duration > 2 * tpl.expected_duration_min:
        flags.append("Ronde anormalement longue")
    if r.status == RoundStatus.interrompue:
        flags.append("Ronde interrompue")
    if n_points < 2:
        flags.append("Aucun trajet GPS enregistré")

    site = shift.site
    return RoundReport(
        round=round_out(r),
        site={"id": str(site.id), "name": site.name, "address": site.address, "location": latlon(site.location),
              "perimeter": geojson(site.perimeter)},
        agent={"id": str(shift.agent.id), "full_name": shift.agent.full_name},
        template={"id": str(tpl.id), "name": tpl.name},
        duration_min=round(duration, 1) if duration is not None else None,
        expected_duration_min=tpl.expected_duration_min,
        completion_pct=round(completion, 1),
        checkpoints=rows,
        missed_checkpoints=missed,
        out_of_order=out_of_order,
        distance_walked_m=round(walked, 1) if walked is not None else None,
        track=json.loads(track) if track else None,
        flags=flags,
    )
