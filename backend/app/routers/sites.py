import secrets
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DB, CurrentUser, Manager
from app.geo import geojson, latlon, point, polygon
from app.models import Checkpoint, RoundTemplate, Site
from app.schemas import (
    CheckpointIn,
    CheckpointOut,
    RoundTemplateIn,
    RoundTemplateOut,
    SiteIn,
    SiteOut,
)

router = APIRouter(tags=["sites & parcours"])


def checkpoint_out(c: Checkpoint) -> CheckpointOut:
    return CheckpointOut(
        id=c.id, name=c.name, code=c.code, order_index=c.order_index,
        instructions=c.instructions, location=latlon(c.location),
    )


def site_out(s: Site) -> SiteOut:
    return SiteOut(
        id=s.id, name=s.name, client_name=s.client_name, address=s.address, site_type=s.site_type,
        required_qualifications=s.required_qualifications or [],
        location=latlon(s.location), perimeter=geojson(s.perimeter),
        checkpoints=[checkpoint_out(c) for c in s.checkpoints],
    )


def get_site_or_404(db, user, site_id: uuid.UUID) -> Site:
    s = db.get(Site, site_id)
    if s is None or s.company_id != user.company_id:
        raise HTTPException(404, "Site introuvable")
    return s


@router.get("/sites", response_model=list[SiteOut])
def list_sites(db: DB, user: CurrentUser):
    sites = db.scalars(
        select(Site).where(Site.company_id == user.company_id)
        .options(selectinload(Site.checkpoints)).order_by(Site.name)
    ).all()
    return [site_out(s) for s in sites]


@router.get("/sites/{site_id}", response_model=SiteOut)
def get_site(db: DB, user: CurrentUser, site_id: uuid.UUID):
    return site_out(get_site_or_404(db, user, site_id))


@router.post("/sites", response_model=SiteOut, status_code=201)
def create_site(db: DB, user: Manager, body: SiteIn):
    s = Site(
        company_id=user.company_id, name=body.name, client_name=body.client_name,
        address=body.address, site_type=body.site_type,
        location=point(body.location.lat, body.location.lon),
        perimeter=polygon([(p.lat, p.lon) for p in body.perimeter]) if body.perimeter else None,
        required_qualifications=body.required_qualifications,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return site_out(s)


@router.post("/sites/{site_id}/checkpoints", response_model=CheckpointOut, status_code=201)
def add_checkpoint(db: DB, user: Manager, site_id: uuid.UUID, body: CheckpointIn):
    get_site_or_404(db, user, site_id)
    c = Checkpoint(
        site_id=site_id, name=body.name, code=body.code or f"VR-{secrets.token_urlsafe(9)}",
        location=point(body.location.lat, body.location.lon),
        order_index=body.order_index, instructions=body.instructions,
    )
    db.add(c)
    db.commit()
    return checkpoint_out(c)


@router.get("/round-templates", response_model=list[RoundTemplateOut])
def list_templates(db: DB, user: CurrentUser, site_id: uuid.UUID | None = None):
    q = select(RoundTemplate).join(Site).where(Site.company_id == user.company_id)
    if site_id:
        q = q.where(RoundTemplate.site_id == site_id)
    return db.scalars(q.order_by(RoundTemplate.name)).all()


@router.post("/round-templates", response_model=RoundTemplateOut, status_code=201)
def create_template(db: DB, user: Manager, body: RoundTemplateIn):
    site = get_site_or_404(db, user, body.site_id)
    valid = {c.id for c in site.checkpoints}
    if not set(body.checkpoint_ids) <= valid:
        raise HTTPException(422, "Certains points de contrôle n'appartiennent pas à ce site")
    t = RoundTemplate(**body.model_dump())
    db.add(t)
    db.commit()
    return t
