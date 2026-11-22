"""Fiche des QR codes des points de contrôle, à imprimer ou à afficher à l'écran pour tester l'appli.

    python -m app.qr_sheet > /data/uploads/qr.html        (tous les sites)
    python -m app.qr_sheet --site "Tour" > fiche.html     (filtre sur le nom du site)
"""
import argparse
import html

import segno
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import Site


def render(site_filter: str | None = None) -> str:
    with SessionLocal() as db:
        q = select(Site).options(selectinload(Site.checkpoints)).order_by(Site.name)
        if site_filter:
            q = q.where(Site.name.ilike(f"%{site_filter}%"))
        sites = db.scalars(q).all()
        parts = []
        for s in sites:
            cards = "".join(
                f"""<figure>{segno.make(c.code, error="m").svg_inline(scale=5, border=2)}
                <figcaption><b>{html.escape(c.name)}</b><br><code>{html.escape(c.code)}</code></figcaption></figure>"""
                for c in sorted(s.checkpoints, key=lambda c: c.order_index)
            )
            parts.append(f"<section><h2>{html.escape(s.name)}</h2><div class=grid>{cards}</div></section>")
    return f"""<!doctype html><html lang=fr><meta charset=utf-8><title>VigiRonde – QR codes des points de contrôle</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;margin:24px;color:#0f172a}}
h1{{font-size:22px}}h2{{font-size:17px;border-bottom:2px solid #1d4ed8;padding-bottom:4px;break-after:avoid}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}}
figure{{margin:0;border:1px solid #cbd5e1;border-radius:10px;padding:10px;text-align:center;break-inside:avoid}}
figcaption{{font-size:13px;margin-top:4px}}code{{color:#475569}}section{{margin-bottom:28px}}</style>
<h1>VigiRonde — QR codes des points de contrôle (données fictives)</h1>{''.join(parts)}</html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site")
    print(render(ap.parse_args().site))
