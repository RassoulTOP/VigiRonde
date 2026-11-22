from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.deps import DB, CurrentUser, Manager
from app.geo import latlon, point
from app.models import PositionPing, Shift, ShiftStatus, User
from app.routers.shifts import get_shift_for
from app.schemas import PositionBatch

router = APIRouter(prefix="/positions", tags=["positions GPS"])


@router.post("/batch", status_code=202)
def push_positions(db: DB, user: CurrentUser, body: PositionBatch):
    """Envoi groupé des positions (l'appli les met en file d'attente hors-ligne)."""
    shift = get_shift_for(db, user, body.shift_id)
    if shift.actual_start is None:
        raise HTTPException(409, "Vacation non commencée : la position n'est enregistrée que pendant le service")
    # RGPD : on ne garde que les points situés pendant le service
    end = shift.actual_end or datetime.now(UTC) + timedelta(minutes=5)
    rows = [
        {
            "agent_id": shift.agent_id, "shift_id": shift.id, "round_id": p.round_id,
            "recorded_at": p.recorded_at, "location": point(p.lat, p.lon),
            "accuracy_m": p.accuracy_m, "battery_pct": p.battery_pct, "client_id": p.client_id,
        }
        for p in body.positions
        if shift.actual_start <= p.recorded_at <= end
    ]
    if rows:
        db.execute(insert(PositionPing).values(rows).on_conflict_do_nothing(index_elements=["client_id"]))
        db.commit()
    return {"received": len(body.positions), "stored": len(rows), "ignored_outside_shift": len(body.positions) - len(rows)}


@router.get("/live")
def live_positions(db: DB, user: Manager):
    """Dernière position connue de chaque agent en service (carte en direct du superviseur)."""
    last = (
        select(PositionPing.shift_id, func.max(PositionPing.recorded_at).label("t"))
        .group_by(PositionPing.shift_id).subquery()
    )
    q = (
        select(PositionPing, Shift, User)
        .join(last, (last.c.shift_id == PositionPing.shift_id) & (last.c.t == PositionPing.recorded_at))
        .join(Shift, Shift.id == PositionPing.shift_id)
        .join(User, User.id == PositionPing.agent_id)
        .where(Shift.status == ShiftStatus.en_cours, User.company_id == user.company_id)
    )
    return [
        {
            "agent_id": str(u.id), "agent_name": u.full_name, "shift_id": str(s.id), "site_id": str(s.site_id),
            "recorded_at": p.recorded_at, "position": latlon(p.location),
            "accuracy_m": p.accuracy_m, "battery_pct": p.battery_pct,
        }
        for p, s, u in db.execute(q).all()
    ]

