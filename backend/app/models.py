"""Modèle de données VigiRonde.

Toutes les géométries sont en WGS84 (SRID 4326). Les distances sont calculées
en mètres via le type `geography` de PostGIS.
"""
import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Role(str, enum.Enum):
    admin = "admin"
    superviseur = "superviseur"
    agent = "agent"


class ShiftStatus(str, enum.Enum):
    planifiee = "planifiee"
    en_cours = "en_cours"
    terminee = "terminee"
    manquee = "manquee"


class RoundStatus(str, enum.Enum):
    en_cours = "en_cours"
    terminee = "terminee"
    interrompue = "interrompue"


class ScanMethod(str, enum.Enum):
    qr = "qr"
    nfc = "nfc"
    manuel = "manuel"


class IncidentCategory(str, enum.Enum):
    intrusion = "intrusion"
    vol = "vol"
    degradation = "degradation"
    incendie = "incendie"
    alarme_technique = "alarme_technique"
    porte_ouverte = "porte_ouverte"
    personne_suspecte = "personne_suspecte"
    malaise = "malaise"
    autre = "autre"


class IncidentStatus(str, enum.Enum):
    ouvert = "ouvert"
    en_traitement = "en_traitement"
    clos = "clos"


def _enum(e):
    return Enum(e, name=e.__name__.lower(), values_callable=lambda x: [m.value for m in x])


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    siret: Mapped[str | None] = mapped_column(String(20))


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.agent)
    # Qualifications : CQP_APS, SSIAP1, SSIAP2, SST, CYNO…
    qualifications: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Site(TimestampMixin, Base):
    __tablename__ = "sites"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    site_type: Mapped[str | None] = mapped_column(String(60))
    location = mapped_column(Geometry("POINT", srid=4326))
    # Périmètre (géorepérage) : sert à vérifier les prises de service et les positions
    perimeter = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    required_qualifications: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)

    checkpoints: Mapped[list["Checkpoint"]] = relationship(
        back_populates="site", order_by="Checkpoint.order_index", cascade="all, delete-orphan"
    )


class Checkpoint(TimestampMixin, Base):
    __tablename__ = "checkpoints"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Contenu du QR code / tag NFC collé sur place
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    location = mapped_column(Geometry("POINT", srid=4326))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    instructions: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site] = relationship(back_populates="checkpoints")


class RoundTemplate(TimestampMixin, Base):
    """Parcours de ronde type : liste ordonnée de points de contrôle."""

    __tablename__ = "round_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    checkpoint_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    expected_duration_min: Mapped[int] = mapped_column(Integer, default=30)
    # Nombre de rondes attendues par vacation
    rounds_per_shift: Mapped[int] = mapped_column(Integer, default=3)


class Shift(TimestampMixin, Base):
    """Vacation : un agent sur un site sur un créneau."""

    __tablename__ = "shifts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    planned_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    planned_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    end_location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    start_inside_perimeter: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[ShiftStatus] = mapped_column(_enum(ShiftStatus), default=ShiftStatus.planifiee, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    agent: Mapped[User] = relationship()
    site: Mapped[Site] = relationship()


class RoundRun(TimestampMixin, Base):
    """Ronde effectuée."""

    __tablename__ = "rounds"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("round_templates.id", ondelete="CASCADE"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RoundStatus] = mapped_column(_enum(RoundStatus), default=RoundStatus.en_cours)
    comment: Mapped[str | None] = mapped_column(Text)

    template: Mapped[RoundTemplate] = relationship()
    scans: Mapped[list["CheckpointScan"]] = relationship(
        back_populates="round", order_by="CheckpointScan.scanned_at", cascade="all, delete-orphan"
    )


class CheckpointScan(TimestampMixin, Base):
    __tablename__ = "checkpoint_scans"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checkpoints.id", ondelete="CASCADE"))
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float)
    method: Mapped[ScanMethod] = mapped_column(_enum(ScanMethod), default=ScanMethod.qr)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)

    round: Mapped[RoundRun] = relationship(back_populates="scans")
    checkpoint: Mapped[Checkpoint] = relationship()


class PositionPing(Base):
    """Position GPS envoyée par l'appli pendant le service (jamais hors service : RGPD)."""

    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), index=True)
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rounds.id", ondelete="SET NULL"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location = mapped_column(Geometry("POINT", srid=4326))
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    # Identifiant côté appli, pour dédoublonner les envois hors-ligne
    client_id: Mapped[str | None] = mapped_column(String(64), unique=True)


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rounds.id", ondelete="SET NULL"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    category: Mapped[IncidentCategory] = mapped_column(_enum(IncidentCategory), default=IncidentCategory.autre)
    severity: Mapped[int] = mapped_column(Integer, default=2)  # 1 (faible) à 5 (critique)
    title: Mapped[str] = mapped_column(String(200))
    description_raw: Mapped[str] = mapped_column(Text)  # notes / dictée de l'agent
    report_ai: Mapped[str | None] = mapped_column(Text)  # rapport mis en forme (IA ou modèle)
    # Rapport à modèle : type de rapport + réponses au formulaire
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_templates.id", ondelete="SET NULL"))
    report_category: Mapped[str | None] = mapped_column(String(40))  # surete, securite, intervention…
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[IncidentStatus] = mapped_column(_enum(IncidentStatus), default=IncidentStatus.ouvert)
    client_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    attachments: Mapped[list["Attachment"]] = relationship(cascade="all, delete-orphan")
    site: Mapped[Site] = relationship()
    agent: Mapped[User] = relationship()


class Attachment(TimestampMixin, Base):
    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int] = mapped_column(Integer)


# ======================================================================
# Phase 2 bis : rapports à modèles, main courante, PTI, consignes, clés,
# visiteurs, pauses (fonctions inspirées du terrain).
# ======================================================================
class ReportTemplate(TimestampMixin, Base):
    """Modèle de rapport (« Anomalie ronde », « Prise en compte de véhicule »…) avec son formulaire."""

    __tablename__ = "report_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))  # surete | securite | intervention | etat_des_lieux | technique
    incident_category: Mapped[IncidentCategory] = mapped_column(_enum(IncidentCategory), default=IncidentCategory.autre)
    default_severity: Mapped[int] = mapped_column(Integer, default=2)
    icon: Mapped[str | None] = mapped_column(String(8))
    # [{key, label, type: text|textarea|number|select|multiselect|boolean|time, options?, required?, help?}]
    fields: Mapped[list] = mapped_column(JSONB, default=list)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)  # vide = tous
    order_index: Mapped[int] = mapped_column(Integer, default=0)


class JournalKind(str, enum.Enum):
    service = "service"
    ronde = "ronde"
    rapport = "rapport"
    evenement = "evenement"
    note = "note"
    pause = "pause"
    clef = "clef"
    visiteur = "visiteur"
    consigne = "consigne"
    alerte = "alerte"


class JournalEntry(TimestampMixin, Base):
    """Main courante : tout ce qui se passe pendant la vacation, horodaté et géolocalisé."""

    __tablename__ = "journal"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[JournalKind] = mapped_column(_enum(JournalKind), default=JournalKind.note)
    text: Mapped[str] = mapped_column(Text)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # ronde, rapport, visite…

    agent: Mapped[User] = relationship()


class AlertKind(str, enum.Enum):
    sos = "sos"
    immobilite = "immobilite"
    chute = "chute"
    test = "test"


class AlertStatus(str, enum.Enum):
    active = "active"
    prise_en_charge = "prise_en_charge"
    annulee = "annulee"
    close = "close"


class Alert(TimestampMixin, Base):
    """Alerte PTI / DATI (protection du travailleur isolé)."""

    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    kind: Mapped[AlertKind] = mapped_column(_enum(AlertKind))
    status: Mapped[AlertStatus] = mapped_column(_enum(AlertStatus), default=AlertStatus.active, index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    handled_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    agent: Mapped[User] = relationship(foreign_keys=[agent_id])
    site: Mapped[Site | None] = relationship()


class Instruction(TimestampMixin, Base):
    """Consigne de site (permanente ou temporaire), à lire et valider par l'agent."""

    __tablename__ = "instructions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    important: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class InstructionAck(Base):
    __tablename__ = "instruction_acks"
    instruction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instructions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    acked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SiteKey(TimestampMixin, Base):
    """Clé ou badge confié au poste de garde."""

    __tablename__ = "site_keys"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(64), unique=True)  # QR / étiquette du trousseau
    location_hint: Mapped[str | None] = mapped_column(String(200))  # où elle est rangée

    movements: Mapped[list["KeyMovement"]] = relationship(order_by="KeyMovement.at", cascade="all, delete-orphan")


class KeyMovement(TimestampMixin, Base):
    __tablename__ = "key_movements"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site_keys.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(10))  # sortie | retour
    holder_name: Mapped[str] = mapped_column(String(200))  # à qui la clé est remise / qui la rend
    holder_company: Mapped[str | None] = mapped_column(String(200))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class Visit(TimestampMixin, Base):
    """Registre des visiteurs et véhicules."""

    __tablename__ = "visits"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    visitor_name: Mapped[str] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(String(300))
    host_name: Mapped[str | None] = mapped_column(String(200))  # personne visitée
    vehicle_plate: Mapped[str | None] = mapped_column(String(20))
    badge_number: Mapped[str | None] = mapped_column(String(40))
    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShiftPause(TimestampMixin, Base):
    __tablename__ = "shift_pauses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    shift_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shifts.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
