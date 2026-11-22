"""Prépare une vacation « à commencer » pour le compte agent de démo (pour tester l'appli mobile).

    python -m app.demo_shift                 # vacation de 8 h qui commence maintenant
    python -m app.demo_shift --site "Tour"   # sur un site précis
Les vacations en cours de ce compte sont clôturées.
"""
import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Shift, ShiftStatus, Site, User

DEMO_AGENT = "agent@demo.vigironde.fr"


def main(site_filter: str | None, hours: int) -> None:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        agent = db.scalar(select(User).where(User.email == DEMO_AGENT))
        if agent is None:
            raise SystemExit("Compte de démo introuvable : lancez d'abord python -m app.seed --reset")
        for s in db.scalars(select(Shift).where(Shift.agent_id == agent.id, Shift.status == ShiftStatus.en_cours)):
            s.status, s.actual_end = ShiftStatus.terminee, now
        q = select(Site).where(Site.company_id == agent.company_id).order_by(Site.name)
        if site_filter:
            q = q.where(Site.name.ilike(f"%{site_filter}%"))
        site = db.scalars(q).first()
        if site is None:
            raise SystemExit("Site introuvable")
        db.add(Shift(agent_id=agent.id, site_id=site.id, planned_start=now - timedelta(minutes=5),
                     planned_end=now + timedelta(hours=hours)))
        db.commit()
        print(f"Vacation prête pour {agent.full_name} sur « {site.name} » ({hours} h).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site")
    ap.add_argument("--hours", type=int, default=8)
    a = ap.parse_args()
    main(a.site, a.hours)
