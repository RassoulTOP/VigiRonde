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
from app.ai import ReportContext, template_report
from app.models import (
    Alert,
    Checkpoint,
    CheckpointScan,
    Company,
    Incident,
    Instruction,
    JournalEntry,
    KeyMovement,
    PositionPing,
    ReportTemplate,
    RoundRun,
    RoundTemplate,
    Shift,
    Site,
    SiteKey,
    User,
    Visit,
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


# Modèles de rapport (inspirés des rapports utilisés sur le terrain)
B = "boolean"
REPORT_TEMPLATES = [
    ("Anomalie ronde", "surete", "autre", 2, "🧭", [
        ("point", "Point de contrôle concerné", "text", None, True),
        ("type_anomalie", "Type d'anomalie", "select", ["Point inaccessible", "QR code illisible ou absent",
         "Éclairage défaillant", "Porte ou fenêtre non sécurisée", "Obstacle sur le parcours", "Autre"], True),
    ]),
    ("Prise en compte de véhicule", "surete", "autre", 1, "🚗", [
        ("plaque", "Immatriculation", "text", None, True),
        ("marque_modele", "Marque / modèle", "text", None, False),
        ("couleur", "Couleur", "text", None, False),
        ("conducteur", "Conducteur", "text", None, False),
        ("motif", "Motif", "select", ["Livraison", "Prestataire", "Visiteur", "Stationnement non autorisé", "Véhicule suspect"], True),
    ]),
    ("Alarme incendie / feu avéré", "securite", "incendie", 4, "🔥", [
        ("zone", "Zone / détecteur", "text", None, True),
        ("levee_de_doute", "Résultat de la levée de doute", "select", ["Feu avéré", "Fausse alarme", "Travaux / poussière", "Cause inconnue"], True),
        ("secours", "Secours appelés (18 / 112)", B, None, False),
        ("evacuation", "Évacuation déclenchée", B, None, False),
        ("extincteur", "Extincteur utilisé", B, None, False),
    ]),
    ("Alarme intrusion / intrusion", "surete", "intrusion", 4, "🚨", [
        ("zone", "Zone", "text", None, True),
        ("levee_de_doute", "Résultat de la levée de doute", "select", ["Intrusion avérée", "Fausse alarme", "Animal", "Cause technique"], True),
        ("forces_ordre", "Police / gendarmerie prévenue", B, None, False),
        ("degradations", "Dégradations constatées", B, None, False),
    ]),
    ("Alarme technique", "securite", "alarme_technique", 2, "⚙️", [
        ("equipement", "Équipement concerné", "text", None, True),
        ("code_defaut", "Message / code défaut", "text", None, False),
        ("astreinte", "Technicien d'astreinte prévenu", B, None, False),
    ]),
    ("Vol", "surete", "vol", 3, "🎒", [
        ("objets", "Objets dérobés", "textarea", None, True),
        ("lieu", "Lieu", "text", None, True),
        ("forces_ordre", "Police / gendarmerie prévenue", B, None, False),
    ]),
    ("Dégradation", "surete", "degradation", 2, "🧱", [
        ("nature", "Nature", "select", ["Tag", "Vitre brisée", "Clôture endommagée", "Serrure forcée", "Autre"], True),
        ("lieu", "Lieu", "text", None, True),
    ]),
    ("Personne suspecte", "surete", "personne_suspecte", 3, "👤", [
        ("signalement", "Signalement (tenue, taille, signes…)", "textarea", None, False),
        ("direction", "Direction de fuite", "text", None, False),
        ("forces_ordre", "Police / gendarmerie prévenue", B, None, False),
    ]),
    ("Secours à personne / malaise", "securite", "malaise", 5, "⛑️", [
        ("consciente", "Victime consciente", B, None, False),
        ("gestes", "Gestes effectués", "multiselect", ["Mise en sécurité", "PLS", "Massage cardiaque", "Défibrillateur (DAE)", "Aucun"], False),
        ("secours", "Secours appelés", "select", ["SAMU (15)", "Pompiers (18)", "112", "Aucun"], True),
        ("heure_secours", "Heure d'arrivée des secours", "time", None, False),
    ]),
    ("Ouverture / fermeture du site", "intervention", "autre", 1, "🔑", [
        ("action", "Action", "select", ["Ouverture", "Fermeture"], True),
        ("alarme", "Alarme", "select", ["Mise en service", "Mise hors service", "Sans objet"], True),
    ]),
    ("État des lieux locaux de repos", "etat_des_lieux", "autre", 1, "🧹", [
        ("proprete", "Propreté", "select", ["Correcte", "À améliorer", "Insuffisante"], True),
        ("equipements_hs", "Équipements hors service", "multiselect", ["Micro-ondes", "Réfrigérateur", "Chauffage", "Sanitaires", "Point d'eau"], False),
    ]),
]
CATEGORY_TO_TEMPLATE = {"intrusion": "Alarme intrusion / intrusion", "vol": "Vol", "degradation": "Dégradation",
                        "incendie": "Alarme incendie / feu avéré", "alarme_technique": "Alarme technique",
                        "porte_ouverte": "Anomalie ronde", "personne_suspecte": "Personne suspecte",
                        "malaise": "Secours à personne / malaise", "autre": "Anomalie ronde"}

INSTRUCTIONS = [
    ("Procédure d'alarme incendie", "En cas de déclenchement : levée de doute immédiate, appel du 18 si feu avéré, "
     "puis prévenir le PC sécurité et le client. Ne jamais réarmer la centrale sans levée de doute.", True),
    ("Contrôle des accès", "Tout visiteur doit être inscrit au registre (nom, société, véhicule, personne visitée) "
     "et porter un badge visiteur. Aucun accès sans accord du client après 20 h.", False),
    ("Remise des clés", "Les clés ne sont remises qu'aux personnes de la liste d'habilitation du client, contre "
     "inscription au registre des clés.", False),
]
TEMP_INSTRUCTIONS = [
    ("Travaux sur la clôture sud", "Entreprise de BTP présente du lundi au vendredi de 8 h à 17 h côté clôture sud. "
     "Vérifier la fermeture du chantier lors de la première ronde de nuit."),
    ("Livraison exceptionnelle", "Livraison prévue cette semaine en dehors des horaires habituels : vérifier le bon "
     "de livraison et prévenir le responsable logistique."),
]
KEY_LABELS = [("Clé local technique", "Armoire à clés n°1"), ("Badge accès toiture", "Armoire à clés n°1"),
              ("Clé portail livraison", "Poste de garde"), ("Clé armoire électrique TGBT", "Armoire à clés n°2"),
              ("Passe général", "Coffre du poste"), ("Clé chaufferie", "Armoire à clés n°2")]
VISITORS = [("Jean Dupont", "Maintenance Atlantique", "Maintenance ascenseur"), ("Nadia Belkacem", "Nettoyage Pro 33", "Nettoyage"),
            ("Paul Mercier", "Transports Garonne", "Livraison"), ("Sophie Arnaud", "Bureau de contrôle", "Vérification extincteurs"),
            ("Hugo Lambert", "Client", "Réunion"), ("Inès Moreau", "Électricité Sud-Ouest", "Intervention TGBT")]
QUICK = ["RAS", "Ouverture du portail", "Fermeture du portail", "Livraison réceptionnée", "Éclairage vérifié",
         "Passage véhicule autorisé", "Alarme acquittée", "Contrôle des extincteurs"]


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
        self.journal, self.alerts, self.visits, self.key_moves = [], [], [], []
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
            # Consignes permanentes + une consigne temporaire
            for title, body, important in INSTRUCTIONS:
                db.add(Instruction(site_id=s.id, title=title, body=body, important=important))
            t_title, t_body = self.rng.choice(TEMP_INSTRUCTIONS)
            db.add(Instruction(site_id=s.id, title=t_title, body=t_body, important=True,
                               valid_from=self.now - timedelta(days=2), valid_to=self.now + timedelta(days=5)))
            # Clés confiées au poste
            s._keys = []
            for label, where in self.rng.sample(KEY_LABELS, k=self.rng.randint(4, 6)):
                k = SiteKey(site_id=s.id, label=label, code=f"CLE-{uuid.uuid4().hex[:8]}", location_hint=where)
                db.add(k)
                s._keys.append(k)
            db.flush()

        # Modèles de rapport (communs à tous les sites)
        self.report_templates = {}
        for idx, (name, cat, inc_cat, sev, icon, fields) in enumerate(REPORT_TEMPLATES):
            t = ReportTemplate(
                company_id=company.id, name=name, category=cat, incident_category=inc_cat, default_severity=sev,
                icon=icon, order_index=idx, site_ids=[],
                fields=[{"key": k, "label": lab, "type": typ, "options": opts, "required": req}
                        for k, lab, typ, opts, req in fields],
            )
            db.add(t)
            self.report_templates[name] = t
        db.flush()

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
        self.log(site, agent, sid, a_start, "service",
                 "Prise de service" + (" — HORS du périmètre du site" if outside else " (dans le périmètre)"), sp)
        a_end = pe + timedelta(minutes=rng.gauss(3, 4))
        ongoing = a_end > now
        if not ongoing:
            shift.update(actual_end=a_end, end_location=wkt(*sp), status="terminee")
            self.log(site, agent, sid, a_end, "service", "Fin de service", sp)

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
        # Main courante : événements courants, visiteurs, clés, test PTI
        for _ in range(rng.randint(1, 4)):
            t = a_start + timedelta(seconds=rng.uniform(0, (horizon_end - a_start).total_seconds()))
            self.log(site, agent, sid, t, "evenement", rng.choice(QUICK), sp)
        if rng.random() < 0.6:
            self.alerts.append({"id": uuid.uuid4(), "agent_id": agent.id, "shift_id": sid, "site_id": site.id,
                                "kind": "test", "status": "close", "triggered_at": a_start + timedelta(minutes=8),
                                "closed_at": a_start + timedelta(minutes=8), "location": wkt(*sp), "accuracy_m": 8.0,
                                "handled_by_id": None, "handled_at": None, "note": None})
            self.log(site, agent, sid, a_start + timedelta(minutes=8), "alerte", "Test du PTI réussi", sp)
        if "jour" in m["slots"] and a_start.astimezone(PARIS).hour < 12:
            for _ in range(rng.randint(0, 3)):
                name, comp, reason = rng.choice(VISITORS)
                t = a_start + timedelta(hours=rng.uniform(1, 9))
                if t >= horizon_end:
                    continue
                left = t + timedelta(minutes=rng.uniform(20, 180))
                vid = uuid.uuid4()
                plate = f"{rng.choice('ABCDEFGH')}{rng.choice('ABCDEFGH')}-{rng.randint(100, 999)}-{rng.choice('JKLMNP')}{rng.choice('QRSTUV')}"
                self.visits.append({"id": vid, "site_id": site.id, "shift_id": sid, "agent_id": agent.id,
                                    "visitor_name": name, "company": comp, "reason": reason, "host_name": None,
                                    "vehicle_plate": plate if rng.random() < 0.6 else None, "badge_number": f"V{rng.randint(1, 20):02d}",
                                    "arrived_at": t, "left_at": left if left < horizon_end else None})
                self.log(site, agent, sid, t, "visiteur", f"Arrivée visiteur : {name} ({comp})", sp, vid)
                if left < horizon_end:
                    self.log(site, agent, sid, left, "visiteur", f"Départ visiteur : {name}", sp, vid)
        if site._keys and rng.random() < 0.35:
            key = rng.choice(site._keys)
            name, comp, _ = rng.choice(VISITORS)
            t = a_start + timedelta(hours=rng.uniform(0.5, 6))
            back = t + timedelta(minutes=rng.uniform(15, 120))
            if back < horizon_end:
                for act, at in (("sortie", t), ("retour", back)):
                    self.key_moves.append({"id": uuid.uuid4(), "key_id": key.id, "agent_id": agent.id, "shift_id": sid,
                                           "action": act, "holder_name": name, "holder_company": comp, "at": at, "note": None})
                    self.log(site, agent, sid, at, "clef",
                             f"Clé « {key.label} » {'remise à' if act == 'sortie' else 'rendue par'} {name} ({comp})", sp, key.id)

    def log(self, site, agent, shift_id, at, kind, text, ll=None, ref_id=None):
        self.journal.append({"id": uuid.uuid4(), "site_id": site.id, "shift_id": shift_id, "agent_id": agent.id,
                             "occurred_at": at, "kind": kind, "text": text,
                             "location": wkt(*ll) if ll else None, "ref_id": ref_id})

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
        self.log(site, agent, shift_id, start, "ronde", f"Début de ronde « {tpl.name} »", None, rid)
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
        done = len({cp.id for cp in visit})
        self.log(site, agent, shift_id, rnd["ended_at"], "ronde",
                 f"{'Ronde interrompue' if anomaly == 'interrupted' else 'Fin de ronde'} « {tpl.name} » : "
                 f"{done}/{len(order)} points" + (f" — {rnd['comment']}" if rnd["comment"] else ""), None, rid)
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
            tpl = self.report_templates[CATEGORY_TO_TEMPLATE[cat]]
            iid = uuid.uuid4()
            title, desc = title.format(z=cp.name.lower()), desc.format(z=cp.name.lower())
            report = template_report(ReportContext(
                template_name=tpl.name, category=tpl.category, title=title, notes=desc, fields=tpl.fields,
                site_name=site.name, agent_name=agent.full_name, occurred_at=t, severity=sev))
            self.incidents.append({
                "id": iid, "site_id": site.id, "shift_id": shift_id, "round_id": None, "agent_id": agent.id,
                "occurred_at": t, "location": wkt(*p), "category": cat, "severity": sev,
                "title": title, "description_raw": desc, "report_ai": report, "status": status, "client_id": None,
                "template_id": tpl.id, "report_category": tpl.category, "answers": {},
            })
            self.log(site, agent, shift_id, t, "rapport", f"Rapport « {tpl.name} : {title} » (gravité {sev}/5)", p, iid)


def chunked_insert(conn, model, rows, size=5000):
    for i in range(0, len(rows), size):
        conn.execute(insert(model), rows[i:i + size])


def run(days: int, seed: int, reset: bool):
    if reset:
        Base.metadata.drop_all(engine)
        with engine.begin() as conn:
            for t in ("roundstatus", "shiftstatus", "scanmethod", "incidentcategory", "incidentstatus", "role",
                      "journalkind", "alertkind", "alertstatus"):
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
        chunked_insert(conn, JournalEntry, g.journal)
        chunked_insert(conn, Alert, g.alerts)
        chunked_insert(conn, Visit, g.visits)
        chunked_insert(conn, KeyMovement, g.key_moves)
    print(
        f"Données de démo créées : {len(g.sites)} sites, {len(g.agents)} agents, {len(g.shifts)} vacations, "
        f"{len(g.rounds)} rondes, {len(g.scans)} scans, {len(g.positions)} positions GPS, {len(g.incidents)} incidents, "
        f"{len(g.journal)} lignes de main courante, {len(g.visits)} visites, {len(g.key_moves)} mouvements de clés."
    )
    print(f"Comptes : admin@demo.vigironde.fr / superviseur@demo.vigironde.fr / agent@demo.vigironde.fr — mot de passe : {DEMO_PASSWORD}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    run(a.days, a.seed, a.reset)
