"""Générateur de données de démonstration VigiRonde.

Crée une société de sécurité fictive en Gironde avec sites, points de contrôle,
agents, ~60 jours d'historique (vacations, rondes, trajets GPS, incidents) et
le planning des 14 prochains jours. Des anomalies réalistes sont injectées
(retards, prises de service hors site, points manqués, rondes trop rapides,
scans à distance, ordre non respecté) pour entraîner la détection d'anomalies.

Usage :  python -m app.seed --reset [--days 60] [--seed 42]
Toutes les données sont fictives.
"""
import argparse
import math
import random
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, text

from app.db import Base, SessionLocal, engine, init_db
from app.models import (
    Checkpoint,
    CheckpointScan,
    Company,
    Incident,
    PositionPing,
    RoundRun,
    RoundTemplate,
    Shift,
    Site,
    User,
)
from app.security import hash_password

PARIS = ZoneInfo("Europe/Paris")
DEMO_PASSWORD = "VigiRonde2026!"

# (nom, client, adresse, type, lat, lon, demi-largeur m, demi-hauteur m, nb points, créneaux, qualifs)
SITES = [
    ("Entrepôt logistique Mérignac", "Logistique Atlantique (fictif)", "Av. de l'Aéroport, Mérignac",
     "entrepot", 44.8372, -0.6957, 180, 120, 9, ["jour", "nuit"], ["CQP_APS"]),
    ("Centre commercial des Rives", "Rives Commerce (fictif)", "Bordeaux Lac", "commerce",
     44.8803, -0.5647, 220, 150, 10, ["jour", "nuit"], ["CQP_APS", "SSIAP1"]),
    ("Tour Euratlantique", "Bureaux Garonne (fictif)", "Quai de Paludate, Bordeaux", "bureaux",
     44.8262, -0.5536, 60, 45, 7, ["nuit"], ["SSIAP1"]),
    ("Chantier Les Berges", "BTP Sud-Ouest (fictif)", "Rue des Berges, Bègles", "chantier",
     44.8004, -0.5483, 140, 100, 6, ["nuit"], ["CQP_APS"]),
    ("Usine Blanquefort", "Industries de l'Estuaire (fictif)", "Zone industrielle, Blanquefort",
     "industrie", 44.9102, -0.6371, 260, 180, 10, ["jour", "nuit"], ["CQP_APS", "SSIAP1"]),
    ("Résidence Campus Pessac", "Habitat Étudiant 33 (fictif)", "Av. du Campus, Pessac", "residence",
     44.8061, -0.6312, 110, 90, 6, ["nuit"], ["CQP_APS"]),
]

FIRST = ["Karim", "Julien", "Aminata", "Thomas", "Moussa", "Sarah", "Kevin", "Fatou", "Nicolas",
         "Ibrahima", "Laura", "Yanis", "Mehdi", "Claire", "Oumar", "Lucas", "Awa", "Romain"]
LAST = ["Diallo", "Martin", "Ndiaye", "Bernard", "Traoré", "Petit", "Lefèvre", "Sow", "Moreau",
        "Camara", "Garcia", "Benali", "Fofana", "Roux", "Ba", "Fournier", "Cissé", "Girard"]

INCIDENT_TEMPLATES = {
    "intrusion": [
        ("Intrusion constatée zone {z}", "Traces d'effraction sur la clôture côté {z}. Individu aperçu en fuite. Levée de doute effectuée, PC sécurité prévenu."),
        ("Clôture découpée {z}", "Grillage découpé sur environ 1 m près de {z}. Pas d'individu sur place. Photos prises, client informé."),
    ],
    "vol": [("Vol de matériel {z}", "Disparition de matériel stocké en {z}. Le local était fermé lors de la ronde précédente.")],
    "degradation": [
        ("Tags sur façade {z}", "Tags récents constatés sur la façade côté {z}."),
        ("Vitre brisée {z}", "Vitre brisée au niveau de {z}, morceaux au sol. Zone balisée."),
    ],
    "incendie": [("Départ de feu poubelle {z}", "Feu de conteneur près de {z}, éteint à l'extincteur. Pompiers non nécessaires.")],
    "alarme_technique": [
        ("Déclenchement alarme {z}", "Alarme intrusion déclenchée zone {z}. Levée de doute : aucune présence, probable défaut capteur."),
        ("Alarme technique chaufferie", "Défaut température signalé par la centrale. Technicien d'astreinte appelé."),
    ],
    "porte_ouverte": [("Porte trouvée ouverte {z}", "Porte non verrouillée lors du passage en {z}. Refermée, vérification intérieure RAS.")],
    "personne_suspecte": [("Personne suspecte aux abords {z}", "Individu rôdant près de {z} depuis plusieurs minutes. Interpellé verbalement, a quitté les lieux.")],
    "malaise": [("Malaise d'une personne {z}", "Personne prise de malaise près de {z}. Gestes de premiers secours, SAMU appelé.")],
    "autre": [("Éclairage défaillant {z}", "Plusieurs luminaires hors service en {z}, visibilité réduite.")],
}

# Poids des catégories selon le type de site
CATEGORY_WEIGHTS = {
    "entrepot": {"intrusion": 3, "vol": 3, "porte_ouverte": 4, "alarme_technique": 3, "degradation": 1, "autre": 2},
    "commerce": {"vol": 4, "personne_suspecte": 4, "degradation": 2, "malaise": 2, "alarme_technique": 2, "autre": 1},
    "bureaux": {"porte_ouverte": 4, "alarme_technique": 4, "personne_suspecte": 1, "autre": 2},
    "chantier": {"intrusion": 5, "vol": 4, "degradation": 3, "incendie": 1},
    "industrie": {"alarme_technique": 4, "intrusion": 2, "porte_ouverte": 3, "incendie": 1, "autre": 2},
    "residence": {"degradation": 3, "personne_suspecte": 3, "incendie": 1, "malaise": 1, "porte_ouverte": 2},
}
SEVERITY = {"intrusion": 4, "vol": 3, "degradation": 2, "incendie": 4, "alarme_technique": 2,
            "porte_ouverte": 1, "personne_suspecte": 2, "malaise": 4, "autre": 1}


def offset(lat: float, lon: float, dx: float, dy: float) -> tuple[float, float]:
    """Déplace un point de dx m vers l'est et dy m vers le nord."""
    return lat + dy / 111_320, lon + dx / (111_320 * math.cos(math.radians(lat)))


def dist(a, b) -> float:
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def wkt(lat: float, lon: float) -> str:
    return f"SRID=4326;POINT({lon:.7f} {lat:.7f})"


class Generator:
    def __init__(self, days: int, seed: int):
        self.rng = random.Random(seed)
        self.days = days
        self.now = datetime.now(UTC).replace(second=0, microsecond=0)
        self.shifts, self.rounds, self.scans, self.positions, self.incidents = [], [], [], [], []
        self.sites, self.agents = [], []

    # ---------------- référentiel ----------------
    def build_reference(self, db):
        company = Company(name="Gironde Sécurité Démo (fictif)", siret="00000000000000")
        db.add(company)
        db.flush()
        self.company = company
        pw = hash_password(DEMO_PASSWORD)
        db.add_all([
            User(company_id=company.id, email="admin@demo.vigironde.fr", full_name="Admin Démo",
                 role="admin", qualifications=[], password_hash=pw),
            User(company_id=company.id, email="superviseur@demo.vigironde.fr", full_name="Sophie Laurent",
                 role="superviseur", qualifications=["CQP_APS", "SSIAP2"], password_hash=pw),
            User(company_id=company.id, email="chef.nuit@demo.vigironde.fr", full_name="Mamadou Kane",
                 role="superviseur", qualifications=["CQP_APS", "SSIAP2", "SST"], password_hash=pw),
        ])
        names = set()
        while len(names) < 16:
            names.add((self.rng.choice(FIRST), self.rng.choice(LAST)))
        for i, (f, l) in enumerate(sorted(names)):
            quals = ["CQP_APS"] + (["SSIAP1"] if self.rng.random() < 0.6 else []) + (["SST"] if self.rng.random() < 0.4 else [])
            email = "agent@demo.vigironde.fr" if i == 0 else f"{f}.{l}@demo.vigironde.fr".lower()
            email = (email.replace("é", "e").replace("è", "e").replace("ï", "i").replace("ë", "e"))
            u = User(company_id=company.id, email=email, full_name=f"{f} {l}", role="agent",
                     qualifications=quals, password_hash=pw, phone=f"06{self.rng.randint(10_000_000, 99_999_999)}")
            db.add(u)
            # Profil comportemental caché (sert à générer des anomalies cohérentes)
            u._profile = {
                "late": self.rng.random() < 0.2,   # agent souvent en retard
                "sloppy": self.rng.random() < 0.15,  # rondes bâclées
            }
            self.agents.append(u)
        db.flush()

        for (name, client, addr, stype, lat, lon, hw, hh, n_cp, slots, quals) in SITES:
            corners = [offset(lat, lon, -hw, -hh), offset(lat, lon, hw, -hh), offset(lat, lon, hw, hh), offset(lat, lon, -hw, hh)]
            perim = ", ".join(f"{c[1]:.7f} {c[0]:.7f}" for c in corners + [corners[0]])
            s = Site(company_id=company.id, name=name, client_name=client, address=addr, site_type=stype,
                     location=f"SRID=4326;POINT({lon} {lat})", perimeter=f"SRID=4326;POLYGON(({perim}))",
                     required_qualifications=quals)
            db.add(s)
            db.flush()
            # Points de contrôle répartis le long du périmètre (légèrement à l'intérieur)
            cps = []
            perim_len = 4 * (hw + hh)
            zone_names = ["Portail principal", "Quai de chargement", "Local technique", "Parking nord", "Issue de secours est",
                          "Clôture sud", "Accueil", "Chaufferie", "Toiture accès", "Parking visiteurs", "Local poubelles",
                          "Stock extérieur", "Issue de secours ouest", "Cour intérieure"]
            self.rng.shuffle(zone_names)
            for k in range(n_cp):
                t = (k + 0.5) / n_cp * perim_len
                if t < 2 * hw:
                    dx, dy = -hw + t, -hh
                elif t < 2 * hw + 2 * hh:
                    dx, dy = hw, -hh + (t - 2 * hw)
                elif t < 4 * hw + 2 * hh:
                    dx, dy = hw - (t - 2 * hw - 2 * hh), hh
                else:
                    dx, dy = -hw, hh - (t - 4 * hw - 2 * hh)
                p = offset(lat, lon, dx * 0.85, dy * 0.85)
                c = Checkpoint(site_id=s.id, name=zone_names[k % len(zone_names)], code=f"VR-{uuid.uuid4().hex[:12]}",
                               location=wkt(*p), order_index=k)
                c._ll = p
                db.add(c)
                cps.append(c)
            db.flush()
            walk = sum(dist(cps[i]._ll, cps[(i + 1) % len(cps)]._ll) for i in range(len(cps)))
            full = RoundTemplate(site_id=s.id, name="Ronde complète", checkpoint_ids=[c.id for c in cps],
                                 expected_duration_min=max(10, round(walk / 1.1 / 60 + len(cps) * 1.0)), rounds_per_shift=3)
            db.add(full)
            tpls = [full]
            if n_cp >= 8:
                sub = cps[::2]
                walk2 = sum(dist(sub[i]._ll, sub[(i + 1) % len(sub)]._ll) for i in range(len(sub)))
                quick = RoundTemplate(site_id=s.id, name="Ronde rapide extérieure", checkpoint_ids=[c.id for c in sub],
                                      expected_duration_min=max(8, round(walk2 / 1.1 / 60 + len(sub) * 1.0)), rounds_per_shift=2)
                db.add(quick)
                tpls.append(quick)
            db.flush()
            s._meta = {"lat": lat, "lon": lon, "hw": hw, "hh": hh, "type": stype, "slots": slots, "cps": cps, "tpls": tpls}
            self.sites.append(s)

    # ---------------- planning & historique ----------------
    def build_activity(self):
        start_day = (self.now.astimezone(PARIS) - timedelta(days=self.days)).date()
        end_day = (self.now.astimezone(PARIS) + timedelta(days=14)).date()
        busy: dict[uuid.UUID, list[tuple[datetime, datetime]]] = {a.id: [] for a in self.agents}
        # Chaque agent a des sites habituels
        for a in self.agents:
            a._sites = self.rng.sample(self.sites, k=2)
        day = start_day
        while day <= end_day:
            for s in self.sites:
                for slot in s._meta["slots"]:
                    if slot == "jour":
                        ps = datetime(day.year, day.month, day.day, 7, 0, tzinfo=PARIS)
                    else:
                        ps = datetime(day.year, day.month, day.day, 19, 0, tzinfo=PARIS)
                    pe = ps + timedelta(hours=12)
                    agent = self.pick_agent(s, ps, pe, busy)
                    if agent is None:
                        continue
                    busy[agent.id].append((ps, pe))
                    self.simulate_shift(agent, s, ps.astimezone(UTC), pe.astimezone(UTC))
            day += timedelta(days=1)

    def pick_agent(self, site, ps, pe, busy):
        candidates = [a for a in self.agents if site in a._sites] + self.agents
        self.rng.shuffle(candidates)
        for a in candidates:
            if not set(site.required_qualifications) <= set(a.qualifications):
                continue
            # Repos minimum de 11 h entre deux vacations (droit du travail)
            if all(pe + timedelta(hours=11) <= b0 or ps >= b1 + timedelta(hours=11) for b0, b1 in busy[a.id]):
                return a
        return None

    def simulate_shift(self, agent, site, ps, pe):
        rng, now, m = self.rng, self.now, site._meta
        sid = uuid.uuid4()
        shift = {"id": sid, "agent_id": agent.id, "site_id": site.id, "planned_start": ps, "planned_end": pe,
                 "actual_start": None, "actual_end": None, "start_location": None, "end_location": None,
                 "start_inside_perimeter": None, "status": "planifiee", "notes": None}
        self.shifts.append(shift)
        if ps > now:
            return
        if rng.random() < 0.015:
            shift["status"] = "manquee"
            shift["notes"] = "Agent absent, non remplacé"
            return
        late = rng.gauss(18, 10) if agent._profile["late"] and rng.random() < 0.45 else rng.gauss(-4, 3)
        a_start = ps + timedelta(minutes=late)
        if a_start > now:
            shift["status"] = "planifiee"
            return
        outside = rng.random() < 0.03
        if outside:
            sp = offset(m["lat"], m["lon"], rng.choice([-1, 1]) * rng.uniform(600, 2500), rng.uniform(-800, 800))
        else:
            sp = offset(m["lat"], m["lon"], rng.uniform(-0.4, 0.4) * m["hw"], -m["hh"] * 0.9)
        shift.update(actual_start=a_start, start_location=wkt(*sp), start_inside_perimeter=not outside, status="en_cours")
        a_end = pe + timedelta(minutes=rng.gauss(3, 4))
        ongoing = a_end > now
        if not ongoing:
            shift.update(actual_end=a_end, end_location=wkt(*sp), status="terminee")

        # Rondes réparties sur la vacation
        horizon_end = now if ongoing else a_end
        slots = []
        for tpl in m["tpls"]:
            for k in range(tpl.rounds_per_shift):
                t = a_start + (pe - a_start) * ((k + 0.5) / tpl.rounds_per_shift) + timedelta(minutes=rng.uniform(-35, 35))
                slots.append((t, tpl))
        slots.sort(key=lambda x: x[0])
        last_end = a_start + timedelta(minutes=5)
        for t, tpl in slots:
            t = max(t, last_end + timedelta(minutes=5))
            if t >= horizon_end:
                break
            last_end = self.simulate_round(agent, site, sid, tpl, t, horizon_end, ongoing)
        # Positions d'attente au poste entre les rondes (1 point / 10 min)
        t = a_start
        while t < horizon_end:
            p = offset(sp[0], sp[1], rng.gauss(0, 6), rng.gauss(0, 6))
            self.positions.append({"agent_id": agent.id, "shift_id": sid, "round_id": None, "recorded_at": t,
                                   "location": wkt(*p), "accuracy_m": round(rng.uniform(5, 20), 1),
                                   "battery_pct": None, "client_id": None})
            t += timedelta(minutes=10)
        # Incidents
        self.simulate_incidents(agent, site, sid, a_start, horizon_end)

    def simulate_round(self, agent, site, shift_id, tpl, start, horizon_end, ongoing):
        rng = self.rng
        cps = {c.id: c for c in site._meta["cps"]}
        order = [cps[c] for c in tpl.checkpoint_ids]
        sloppy = agent._profile["sloppy"]
        r = rng.random()
        anomaly = None
        if r < (0.12 if sloppy else 0.03):
            anomaly = "skip"
        elif r < (0.20 if sloppy else 0.05):
            anomaly = "fast_remote"  # scans faits depuis un seul endroit
        elif r < (0.25 if sloppy else 0.07):
            anomaly = "order"
        elif r < (0.27 if sloppy else 0.085):
            anomaly = "interrupted"

        visit = list(order)
        if anomaly == "skip":
            for _ in range(rng.randint(1, max(1, len(visit) // 3))):
                visit.pop(rng.randrange(len(visit)))
        elif anomaly == "order":
            i, j = rng.sample(range(len(visit)), 2)
            visit[i], visit[j] = visit[j], visit[i]
        elif anomaly == "interrupted":
            visit = visit[: rng.randint(1, max(1, len(visit) // 2))]

        rid = uuid.uuid4()
        rnd = {"id": rid, "shift_id": shift_id, "template_id": tpl.id, "agent_id": agent.id, "started_at": start,
               "ended_at": None, "status": "en_cours", "comment": None}
        self.rounds.append(rnd)
        t = start
        speed = rng.uniform(1.0, 1.4)  # m/s
        pos = order[0]._ll
        anchor = visit[0]._ll
        for cp in visit:
            target = cp._ll
            if anomaly == "fast_remote":
                t += timedelta(seconds=rng.uniform(15, 45))
                here = offset(anchor[0], anchor[1], rng.gauss(0, 3), rng.gauss(0, 3))
                # L'agent reste sur place : le trajet GPS le montre immobile
                self.positions.append({"agent_id": agent.id, "shift_id": shift_id, "round_id": rid, "recorded_at": t,
                                       "location": wkt(*here), "accuracy_m": round(rng.uniform(3, 12), 1),
                                       "battery_pct": None, "client_id": None})
            else:
                d = dist(pos, target)
                steps = max(1, int(d / speed / 30))
                for k in range(1, steps + 1):
                    frac = k / steps
                    p = (pos[0] + (target[0] - pos[0]) * frac, pos[1] + (target[1] - pos[1]) * frac)
                    p = offset(p[0], p[1], rng.gauss(0, 4), rng.gauss(0, 4))
                    t += timedelta(seconds=d / speed / steps)
                    if t > horizon_end:
                        return t
                    self.positions.append({"agent_id": agent.id, "shift_id": shift_id, "round_id": rid, "recorded_at": t,
                                           "location": wkt(*p), "accuracy_m": round(rng.uniform(3, 12), 1),
                                           "battery_pct": None, "client_id": None})
                t += timedelta(seconds=rng.uniform(20, 90))
                here = offset(target[0], target[1], rng.gauss(0, 5), rng.gauss(0, 5))
                pos = target
            if t > horizon_end:
                return t
            d_cp = dist(here, target)
            self.scans.append({"id": uuid.uuid4(), "round_id": rid, "checkpoint_id": cp.id, "scanned_at": t,
                               "location": wkt(*here), "distance_m": round(d_cp, 1), "method": "qr",
                               "is_valid": d_cp <= 60, "note": None})
        if t > horizon_end and ongoing:
            return t
        rnd["ended_at"] = t + timedelta(seconds=30)
        rnd["status"] = "interrompue" if anomaly == "interrupted" else "terminee"
        if anomaly == "interrupted":
            rnd["comment"] = rng.choice(["Appel PC sécurité, ronde interrompue", "Intervention sur alarme", "Problème de badge"])
        return rnd["ended_at"]

    def simulate_incidents(self, agent, site, shift_id, start, end):
        rng, m = self.rng, site._meta
        hours = (end - start).total_seconds() / 3600
        base = {"chantier": 0.06, "commerce": 0.05, "entrepot": 0.035, "industrie": 0.03, "residence": 0.04, "bureaux": 0.02}[m["type"]]
        n = sum(1 for _ in range(int(hours)) if rng.random() < base)
        weights = CATEGORY_WEIGHTS[m["type"]]
        cats, w = zip(*weights.items())
        for _ in range(n):
            # Plus d'incidents entre 22 h et 4 h
            for _try in range(5):
                t = start + timedelta(seconds=rng.uniform(0, (end - start).total_seconds()))
                h = t.astimezone(PARIS).hour
                if h >= 22 or h < 4 or rng.random() < 0.5:
                    break
            cat = rng.choices(cats, weights=w)[0]
            cp = rng.choice(m["cps"])
            title, desc = rng.choice(INCIDENT_TEMPLATES[cat])
            sev = max(1, min(5, SEVERITY[cat] + rng.choice([-1, 0, 0, 0, 1])))
            p = offset(cp._ll[0], cp._ll[1], rng.gauss(0, 10), rng.gauss(0, 10))
            age_days = (self.now - t).days
            status = "clos" if age_days > 3 else rng.choice(["ouvert", "en_traitement", "clos"])
            self.incidents.append({
                "id": uuid.uuid4(), "site_id": site.id, "shift_id": shift_id, "round_id": None, "agent_id": agent.id,
                "occurred_at": t, "location": wkt(*p), "category": cat, "severity": sev,
                "title": title.format(z=cp.name.lower()), "description_raw": desc.format(z=cp.name.lower()),
                "report_ai": None, "status": status, "client_id": None,
            })


def chunked_insert(conn, model, rows, size=5000):
    for i in range(0, len(rows), size):
        conn.execute(insert(model), rows[i:i + size])


def run(days: int, seed: int, reset: bool):
    if reset:
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            for t in ("roundstatus", "shiftstatus", "scanmethod", "incidentcategory", "incidentstatus", "role"):
                conn.execute(text(f"DROP TYPE IF EXISTS {t} CASCADE"))
    init_db()
    g = Generator(days, seed)
    with SessionLocal() as db:
        if db.query(Company).count() and not reset:
            print("Des données existent déjà. Relancez avec --reset pour tout régénérer.")
            return
        g.build_reference(db)
        db.commit()
    g.build_activity()
    with engine.begin() as conn:
        chunked_insert(conn, Shift, g.shifts)
        chunked_insert(conn, RoundRun, g.rounds)
        chunked_insert(conn, CheckpointScan, g.scans)
        chunked_insert(conn, PositionPing, g.positions)
        chunked_insert(conn, Incident, g.incidents)
    print(
        f"Données de démo créées : {len(g.sites)} sites, {len(g.agents)} agents, {len(g.shifts)} vacations, "
        f"{len(g.rounds)} rondes, {len(g.scans)} scans, {len(g.positions)} positions GPS, {len(g.incidents)} incidents."
    )
    print(f"Comptes : admin@demo.vigironde.fr / superviseur@demo.vigironde.fr / agent@demo.vigironde.fr — mot de passe : {DEMO_PASSWORD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    run(a.days, a.seed, a.reset)
