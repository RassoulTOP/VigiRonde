"""Schémas des fonctions terrain : rapports à modèles, main courante, PTI, consignes, clés, visiteurs, pauses."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.geo import latlon
from app.models import AlertKind, AlertStatus, IncidentCategory, JournalKind
from app.schemas import GpsFix, LatLon

FieldType = Literal["text", "textarea", "number", "select", "multiselect", "boolean", "time"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _geom(v):
    return v if v is None or isinstance(v, (dict, LatLon)) else latlon(v)


# ---------- Rapports à modèles ----------
class TemplateField(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    label: str
    type: FieldType = "text"
    options: list[str] | None = None
    required: bool = False
    help: str | None = None


class ReportTemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    category: str = Field(pattern=r"^(surete|securite|intervention|etat_des_lieux|technique)$")
    incident_category: IncidentCategory = IncidentCategory.autre
    default_severity: int = Field(default=2, ge=1, le=5)
    icon: str | None = None
    fields: list[TemplateField] = []
    site_ids: list[uuid.UUID] = []
    order_index: int = 0


class ReportTemplateOut(ReportTemplateIn, ORM):
    id: uuid.UUID


class DraftIn(BaseModel):
    site_id: uuid.UUID
    template_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    answers: dict = {}
    severity: int | None = Field(default=None, ge=1, le=5)
    occurred_at: datetime | None = None


class DraftOut(BaseModel):
    text: str
    source: Literal["ia", "modele"]


# ---------- Main courante ----------
class JournalIn(BaseModel):
    id: uuid.UUID | None = None
    shift_id: uuid.UUID
    kind: Literal["evenement", "note"] = "evenement"
    text: str = Field(min_length=1, max_length=2000)
    position: GpsFix | None = None
    at: datetime | None = None


class JournalOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    shift_id: uuid.UUID | None
    agent_id: uuid.UUID
    agent_name: str | None = None
    occurred_at: datetime
    kind: JournalKind
    text: str
    location: LatLon | None = None
    ref_id: uuid.UUID | None

    @field_validator("location", mode="before")
    @classmethod
    def _loc(cls, v):
        return _geom(v)


# ---------- PTI / alertes ----------
class AlertIn(BaseModel):
    id: uuid.UUID | None = None
    kind: AlertKind
    shift_id: uuid.UUID | None = None
    position: GpsFix | None = None
    at: datetime | None = None
    note: str | None = None


class AlertAction(BaseModel):
    note: str | None = None


class AlertOut(ORM):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    agent_phone: str | None = None
    site_id: uuid.UUID | None
    site_name: str | None = None
    shift_id: uuid.UUID | None
    kind: AlertKind
    status: AlertStatus
    triggered_at: datetime
    location: LatLon | None = None
    accuracy_m: float | None
    handled_by_name: str | None = None
    handled_at: datetime | None
    closed_at: datetime | None
    note: str | None

    @field_validator("location", mode="before")
    @classmethod
    def _loc(cls, v):
        return _geom(v)


# ---------- Consignes ----------
class InstructionIn(BaseModel):
    site_id: uuid.UUID
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=2)
    important: bool = False
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class InstructionOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    title: str
    body: str
    important: bool
    valid_from: datetime | None
    valid_to: datetime | None
    created_at: datetime
    acked_at: datetime | None = None


class AckIn(BaseModel):
    shift_id: uuid.UUID | None = None
    at: datetime | None = None


# ---------- Clés ----------
class KeyOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    label: str
    code: str
    location_hint: str | None
    is_out: bool = False
    holder_name: str | None = None
    holder_company: str | None = None
    since: datetime | None = None


class KeyMovementIn(BaseModel):
    id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    action: Literal["sortie", "retour"]
    holder_name: str = Field(min_length=2, max_length=200)
    holder_company: str | None = None
    at: datetime | None = None
    note: str | None = None


class KeyMovementOut(ORM):
    id: uuid.UUID
    key_id: uuid.UUID
    action: str
    holder_name: str
    holder_company: str | None
    at: datetime
    note: str | None


# ---------- Visiteurs ----------
class VisitIn(BaseModel):
    id: uuid.UUID | None = None
    site_id: uuid.UUID
    shift_id: uuid.UUID | None = None
    visitor_name: str = Field(min_length=2, max_length=200)
    company: str | None = None
    reason: str | None = None
    host_name: str | None = None
    vehicle_plate: str | None = Field(default=None, max_length=20)
    badge_number: str | None = None
    at: datetime | None = None

    @field_validator("vehicle_plate")
    @classmethod
    def _plate(cls, v: str | None) -> str | None:
        return v.upper().replace(" ", "-").strip() if v else v


class VisitExit(BaseModel):
    at: datetime | None = None


class VisitOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    visitor_name: str
    company: str | None
    reason: str | None
    host_name: str | None
    vehicle_plate: str | None
    badge_number: str | None
    arrived_at: datetime
    left_at: datetime | None


# ---------- Pauses ----------
class PauseIn(BaseModel):
    id: uuid.UUID | None = None
    at: datetime | None = None


class PauseOut(ORM):
    id: uuid.UUID
    shift_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
