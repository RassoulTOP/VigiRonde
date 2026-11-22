import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.config import get_settings
from app.deps import DB, CurrentUser, Manager
from app.geo import point
from app.models import Attachment, Incident, IncidentCategory, IncidentStatus, Role, Site
from app.routers.shifts import get_shift_for
from app.schemas import AttachmentOut, IncidentIn, IncidentOut, IncidentUpdate

router = APIRouter(prefix="/incidents", tags=["incidents"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/heic", "image/webp", "video/mp4", "audio/m4a", "audio/mpeg"}
MAX_BYTES = 15 * 1024 * 1024


def incident_out(i: Incident) -> IncidentOut:
    out = IncidentOut.model_validate(i)
    out.site_name = i.site.name if i.site else None
    out.agent_name = i.agent.full_name if i.agent else None
    return out


def _load(db, user, incident_id: uuid.UUID) -> Incident:
    i = db.get(
        Incident, incident_id,
        options=[selectinload(Incident.attachments), joinedload(Incident.site), joinedload(Incident.agent)],
    )
    if i is None or i.site.company_id != user.company_id:
        raise HTTPException(404, "Incident introuvable")
    if user.role == Role.agent and i.agent_id != user.id:
        raise HTTPException(403, "Accès refusé")
    return i


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    db: DB, user: CurrentUser, site_id: uuid.UUID | None = None,
    status: IncidentStatus | None = None, category: IncidentCategory | None = None,
    min_severity: int | None = None, start: datetime | None = None, end: datetime | None = None,
    limit: int = 100,
):
    q = (
        select(Incident).join(Site).where(Site.company_id == user.company_id)
        .options(selectinload(Incident.attachments), joinedload(Incident.site), joinedload(Incident.agent))
    )
    if user.role == Role.agent:
        q = q.where(Incident.agent_id == user.id)
    if site_id:
        q = q.where(Incident.site_id == site_id)
    if status:
        q = q.where(Incident.status == status)
    if category:
        q = q.where(Incident.category == category)
    if min_severity:
        q = q.where(Incident.severity >= min_severity)
    if start:
        q = q.where(Incident.occurred_at >= start)
    if end:
        q = q.where(Incident.occurred_at <= end)
    return [incident_out(i) for i in db.scalars(q.order_by(Incident.occurred_at.desc()).limit(min(limit, 500))).all()]


@router.post("", response_model=IncidentOut, status_code=201)
def create_incident(db: DB, user: CurrentUser, body: IncidentIn):
    site = db.get(Site, body.site_id)
    if site is None or site.company_id != user.company_id:
        raise HTTPException(404, "Site introuvable")
    if body.client_id:
        existing = db.scalar(select(Incident).where(Incident.client_id == body.client_id))
        if existing:  # renvoi hors-ligne déjà reçu : idempotent
            return incident_out(_load(db, user, existing.id))
    if body.shift_id:
        get_shift_for(db, user, body.shift_id)
    i = Incident(
        site_id=site.id, shift_id=body.shift_id, round_id=body.round_id, agent_id=user.id,
        occurred_at=body.occurred_at or datetime.now(UTC),
        location=point(body.position.lat, body.position.lon) if body.position else None,
        category=body.category, severity=body.severity, title=body.title,
        description_raw=body.description_raw, client_id=body.client_id,
    )
    db.add(i)
    db.commit()
    return incident_out(_load(db, user, i.id))


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(db: DB, user: CurrentUser, incident_id: uuid.UUID):
    return incident_out(_load(db, user, incident_id))


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(db: DB, user: Manager, incident_id: uuid.UUID, body: IncidentUpdate):
    i = _load(db, user, incident_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(i, k, v)
    db.commit()
    return incident_out(_load(db, user, incident_id))


@router.post("/{incident_id}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(db: DB, user: CurrentUser, incident_id: uuid.UUID, file: UploadFile):
    i = _load(db, user, incident_id)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Type de fichier non accepté : {file.content_type}")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (15 Mo max)")
    folder = os.path.join(get_settings().upload_dir, str(i.id))
    os.makedirs(folder, exist_ok=True)
    att_id = uuid.uuid4()
    ext = os.path.splitext(file.filename or "")[1][:10]
    path = os.path.join(folder, f"{att_id}{ext}")
    with open(path, "wb") as f:
        f.write(data)
    a = Attachment(
        id=att_id, incident_id=i.id, filename=os.path.basename(file.filename or f"{att_id}{ext}"),
        content_type=file.content_type, path=path, size_bytes=len(data),
    )
    db.add(a)
    db.commit()
    return a


@router.get("/{incident_id}/attachments/{attachment_id}")
def download_attachment(db: DB, user: CurrentUser, incident_id: uuid.UUID, attachment_id: uuid.UUID):
    i = _load(db, user, incident_id)
    a = next((a for a in i.attachments if a.id == attachment_id), None)
    if a is None or not os.path.exists(a.path):
        raise HTTPException(404, "Pièce jointe introuvable")
    return FileResponse(a.path, media_type=a.content_type, filename=a.filename)
