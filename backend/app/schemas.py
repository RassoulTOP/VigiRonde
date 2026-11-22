import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.geo import latlon

from app.models import IncidentCategory, IncidentStatus, Role, RoundStatus, ScanMethod, ShiftStatus


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GpsFix(LatLon):
    accuracy_m: float | None = Field(default=None, ge=0)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth / utilisateurs ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    full_name: str


class UserOut(ORM):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None
    role: Role
    qualifications: list[str]
    is_active: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = None
    role: Role = Role.agent
    qualifications: list[str] = []
    password: str = Field(min_length=8)


# ---------- Sites ----------
class CheckpointIn(BaseModel):
    name: str
    code: str | None = None
    location: LatLon
    order_index: int = 0
    instructions: str | None = None


class CheckpointOut(ORM):
    id: uuid.UUID
    name: str
    code: str
    order_index: int
    instructions: str | None
    location: LatLon | None = None


class SiteIn(BaseModel):
    name: str
    client_name: str | None = None
    address: str | None = None
    site_type: str | None = None
    location: LatLon
    perimeter: list[LatLon] | None = None
    required_qualifications: list[str] = []


class SiteOut(ORM):
    id: uuid.UUID
    name: str
    client_name: str | None
    address: str | None
    site_type: str | None
    required_qualifications: list[str]
    location: LatLon | None = None
    perimeter: dict | None = None  # GeoJSON
    checkpoints: list[CheckpointOut] = []


class RoundTemplateIn(BaseModel):
    site_id: uuid.UUID
    name: str
    checkpoint_ids: list[uuid.UUID] = Field(min_length=1)
    expected_duration_min: int = Field(default=30, gt=0)
    rounds_per_shift: int = Field(default=3, ge=0)


class RoundTemplateOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    name: str
    checkpoint_ids: list[uuid.UUID]
    expected_duration_min: int
    rounds_per_shift: int


# ---------- Vacations ----------
class ShiftIn(BaseModel):
    agent_id: uuid.UUID
    site_id: uuid.UUID
    planned_start: datetime
    planned_end: datetime


class ShiftOut(ORM):
    id: uuid.UUID
    agent_id: uuid.UUID
    site_id: uuid.UUID
    site_name: str | None = None
    agent_name: str | None = None
    planned_start: datetime
    planned_end: datetime
    actual_start: datetime | None
    actual_end: datetime | None
    start_inside_perimeter: bool | None
    status: ShiftStatus
    notes: str | None


class ShiftAction(BaseModel):
    position: GpsFix | None = None
    at: datetime | None = None  # heure côté appli (utile hors-ligne)
    notes: str | None = None


# ---------- Rondes ----------
class RoundStart(BaseModel):
    shift_id: uuid.UUID
    template_id: uuid.UUID
    position: GpsFix | None = None
    at: datetime | None = None


class ScanIn(BaseModel):
    code: str
    method: ScanMethod = ScanMethod.qr
    position: GpsFix | None = None
    at: datetime | None = None
    note: str | None = None


class ScanOut(ORM):
    id: uuid.UUID
    checkpoint_id: uuid.UUID
    checkpoint_name: str | None = None
    scanned_at: datetime
    distance_m: float | None
    method: ScanMethod
    is_valid: bool
    note: str | None


class RoundEnd(BaseModel):
    position: GpsFix | None = None
    at: datetime | None = None
    comment: str | None = None
    interrupted: bool = False


class RoundOut(ORM):
    id: uuid.UUID
    shift_id: uuid.UUID
    template_id: uuid.UUID
    agent_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    status: RoundStatus
    comment: str | None
    scans: list[ScanOut] = []


class CheckpointReport(BaseModel):
    checkpoint_id: uuid.UUID
    name: str
    order_index: int
    location: LatLon | None
    scanned: bool
    scanned_at: datetime | None = None
    distance_m: float | None = None
    is_valid: bool | None = None
    minutes_since_start: float | None = None


class RoundReport(BaseModel):
    round: RoundOut
    site: dict
    agent: dict
    template: dict
    duration_min: float | None
    expected_duration_min: int
    completion_pct: float
    checkpoints: list[CheckpointReport]
    missed_checkpoints: list[str]
    out_of_order: bool
    distance_walked_m: float | None
    track: dict | None  # GeoJSON LineString
    flags: list[str]


# ---------- Positions ----------
class PositionIn(GpsFix):
    recorded_at: datetime
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    round_id: uuid.UUID | None = None
    client_id: str | None = None


class PositionBatch(BaseModel):
    shift_id: uuid.UUID
    positions: list[PositionIn] = Field(max_length=2000)


# ---------- Incidents ----------
class IncidentIn(BaseModel):
    site_id: uuid.UUID
    shift_id: uuid.UUID | None = None
    round_id: uuid.UUID | None = None
    occurred_at: datetime | None = None
    position: GpsFix | None = None
    category: IncidentCategory = IncidentCategory.autre
    severity: int = Field(default=2, ge=1, le=5)
    title: str = Field(min_length=3, max_length=200)
    description_raw: str = Field(min_length=3)
    client_id: str | None = None


class IncidentUpdate(BaseModel):
    status: IncidentStatus | None = None
    category: IncidentCategory | None = None
    severity: int | None = Field(default=None, ge=1, le=5)
    report_ai: str | None = None


class AttachmentOut(ORM):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int


class IncidentOut(ORM):
    id: uuid.UUID
    site_id: uuid.UUID
    site_name: str | None = None
    shift_id: uuid.UUID | None
    round_id: uuid.UUID | None
    agent_id: uuid.UUID
    agent_name: str | None = None
    occurred_at: datetime
    location: LatLon | None = None
    category: IncidentCategory
    severity: int
    title: str
    description_raw: str
    report_ai: str | None
    status: IncidentStatus
    attachments: list[AttachmentOut] = []

    @field_validator("location", mode="before")
    @classmethod
    def _geom_to_latlon(cls, v):
        return v if v is None or isinstance(v, (dict, LatLon)) else latlon(v)
