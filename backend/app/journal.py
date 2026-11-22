"""Main courante : écriture automatique des événements de la vacation."""
import uuid
from datetime import UTC, datetime

from app.models import JournalEntry, JournalKind


def journal(
    db,
    *,
    site_id: uuid.UUID,
    agent_id: uuid.UUID,
    kind: JournalKind,
    text: str,
    shift_id: uuid.UUID | None = None,
    at: datetime | None = None,
    location=None,
    ref_id: uuid.UUID | None = None,
    entry_id: uuid.UUID | None = None,
) -> JournalEntry:
    """Ajoute une ligne à la main courante (sans commit : fait partie de l'action en cours)."""
    e = JournalEntry(
        id=entry_id or uuid.uuid4(), site_id=site_id, shift_id=shift_id, agent_id=agent_id,
        occurred_at=at or datetime.now(UTC), kind=kind, text=text, location=location, ref_id=ref_id,
    )
    db.add(e)
    return e
