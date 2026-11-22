import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.deps import DB, CurrentUser, Manager
from app.geo import is_inside, point
from app.models import Role, Shift, ShiftStatus, User
from app.schemas import ShiftAction, ShiftIn, ShiftOut

router = APIRouter(prefix="/shifts", tags=["vacations"])


def shift_out(s: Shift) -> ShiftOut:
    out = ShiftOut.model_validate(s)
    out.site_name = s.site.name if s.site else None
    out.agent_name = s.agent.full_name if s.agent else None
    return out


def get_shift_for(db, user: User, shift_id: uuid.UUID) -> Shift:
    s = db.get(Shift, shift_id, options=[joinedload(Shift.site), joinedload(Shift.agent)])
    if s is None or s.site.company_id != user.company_id:
        raise HTTPException(404, "Vacation introuvable")
    if user.role == Role.agent and s.agent_id != user.id:
        raise HTTPException(403, "Cette vacation n'est pas la vôtre")
    return s


@router.get("", response_model=list[ShiftOut])
def list_shifts(
    db: DB, user: CurrentUser,
    start: datetime | None = None, end: datetime | None = None,
    agent_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    status: ShiftStatus | None = None, limit: int = 200,
):
    q = (
        select(Shift).join(Shift.site).join(Shift.agent)
        .where(User.company_id == user.company_id)
        .options(joinedload(Shift.site), joinedload(Shift.agent))
    )
    if user.role == Role.agent:
        q = q.where(Shift.agent_id == user.id)
    elif agent_id:
        q = q.where(Shift.agent_id == agent_id)
    if site_id:
        q = q.where(Shift.site_id == site_id)
    if start:
        q = q.where(Shift.planned_end >= start)
    if end:
        q = q.where(Shift.planned_start <= end)
    if status:
        q = q.where(Shift.status == status)
    shifts = db.scalars(q.order_by(Shift.planned_start.desc()).limit(min(limit, 1000))).all()
    return [shift_out(s) for s in shifts]


@router.post("", response_model=ShiftOut, status_code=201)
def create_shift(db: DB, user: Manager, body: ShiftIn):
    if body.planned_end <= body.planned_start:
        raise HTTPException(422, "La fin doit être après le début")
    agent = db.get(User, body.agent_id)
    if agent is None or agent.company_id != user.company_id:
        raise HTTPException(404, "Agent introuvable")
    s = Shift(**body.model_dump())
    db.add(s)
    db.commit()
    return shift_out(get_shift_for(db, user, s.id))


@router.get("/current", response_model=ShiftOut | None)
def current_shift(db: DB, user: CurrentUser):
    s = db.scalar(
        select(Shift).where(Shift.agent_id == user.id, Shift.status == ShiftStatus.en_cours)
        .options(joinedload(Shift.site), joinedload(Shift.agent))
    )
    return shift_out(s) if s else None


@router.post("/{shift_id}/start", response_model=ShiftOut)
def start_shift(db: DB, user: CurrentUser, shift_id: uuid.UUID, body: ShiftAction):
    s = get_shift_for(db, user, shift_id)
    if s.status != ShiftStatus.planifiee:
        raise HTTPException(409, f"Vacation déjà {s.status.value}")
    s.actual_start = body.at or datetime.now(UTC)
    if body.position:
        s.start_location = point(body.position.lat, body.position.lon)
        s.start_inside_perimeter = is_inside(db, s.site.perimeter, s.start_location)
    s.status = ShiftStatus.en_cours
    if body.notes:
        s.notes = body.notes
    db.commit()
    return shift_out(s)


@router.post("/{shift_id}/end", response_model=ShiftOut)
def end_shift(db: DB, user: CurrentUser, shift_id: uuid.UUID, body: ShiftAction):
    s = get_shift_for(db, user, shift_id)
    if s.status != ShiftStatus.en_cours:
        raise HTTPException(409, "La vacation n'est pas en cours")
    s.actual_end = body.at or datetime.now(UTC)
    if body.position:
        s.end_location = point(body.position.lat, body.position.lon)
    if body.notes:
        s.notes = ((s.notes or "") + "\n" + body.notes).strip()
    s.status = ShiftStatus.terminee
    db.commit()
    return shift_out(s)
