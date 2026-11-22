"""Modèles de rapport et rédaction assistée."""
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import ReportContext, write_report
from app.deps import DB, CurrentUser, Manager
from app.models import Incident, ReportTemplate, Site
from app.schemas_terrain import DraftIn, DraftOut, ReportTemplateIn, ReportTemplateOut

router = APIRouter(tags=["rapports"])


def templates_for(db, company_id: uuid.UUID, site_id: uuid.UUID | None = None) -> list[ReportTemplate]:
    rows = db.scalars(
        select(ReportTemplate).where(ReportTemplate.company_id == company_id)
        .order_by(ReportTemplate.order_index, ReportTemplate.name)
    ).all()
    return [t for t in rows if not site_id or not t.site_ids or site_id in t.site_ids]


@router.get("/report-templates", response_model=list[ReportTemplateOut])
def list_report_templates(db: DB, user: CurrentUser, site_id: uuid.UUID | None = None):
    return templates_for(db, user.company_id, site_id)


@router.post("/report-templates", response_model=ReportTemplateOut, status_code=201)
def create_report_template(db: DB, user: Manager, body: ReportTemplateIn):
    t = ReportTemplate(company_id=user.company_id, **body.model_dump(mode="json", exclude={"site_ids"}),
                       site_ids=body.site_ids)
    db.add(t)
    db.commit()
    return t


def context_for(db, *, site: Site, agent_name: str, template: ReportTemplate | None, title: str,
                notes: str, answers: dict, severity: int | None, occurred_at) -> ReportContext:
    return ReportContext(
        template_name=template.name if template else "Événement",
        category=template.category if template else None,
        title=title, notes=notes, answers=answers or {},
        fields=template.fields if template else [],
        site_name=site.name, agent_name=agent_name, occurred_at=occurred_at, severity=severity,
    )


@router.post("/reports/draft", response_model=DraftOut)
def draft_report(db: DB, user: CurrentUser, body: DraftIn):
    """Met en forme les notes de l'agent avant envoi (aperçu, rien n'est enregistré)."""
    site = db.get(Site, body.site_id)
    if site is None or site.company_id != user.company_id:
        raise HTTPException(404, "Site introuvable")
    tpl = db.get(ReportTemplate, body.template_id) if body.template_id else None
    if tpl is not None and tpl.company_id != user.company_id:
        raise HTTPException(404, "Modèle introuvable")
    text, source = write_report(context_for(
        db, site=site, agent_name=user.full_name, template=tpl, title=body.title,
        notes=body.description, answers=body.answers, severity=body.severity, occurred_at=body.occurred_at,
    ))
    return DraftOut(text=text, source=source)


def fill_missing_report(incident_id: uuid.UUID, bind) -> None:
    """Tâche de fond : rédige le rapport d'un incident reçu sans rapport mis en forme."""
    with Session(bind=bind) as db:
        i = db.get(Incident, incident_id)
        if i is None or i.report_ai:
            return
        tpl = db.get(ReportTemplate, i.template_id) if i.template_id else None
        text, _ = write_report(context_for(
            db, site=i.site, agent_name=i.agent.full_name, template=tpl, title=i.title,
            notes=i.description_raw, answers=i.answers, severity=i.severity, occurred_at=i.occurred_at,
        ))
        i.report_ai = text
        db.commit()
