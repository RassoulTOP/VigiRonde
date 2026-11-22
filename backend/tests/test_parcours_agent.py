"""Test de bout en bout du parcours principal : un agent prend son service,
fait une ronde avec ses points de contrôle, déclare un incident, puis le
superviseur consulte le rapport de ronde géolocalisé."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as dbmod
from app.config import get_settings
from app.main import app
from app.models import Company, User
from app.security import hash_password
from app.seed import offset

SITE = (44.8372, -0.6957)


@pytest.fixture(scope="module")
def client():
    engine = create_engine(get_settings().test_database_url)
    dbmod.Base.metadata.drop_all(engine)
    dbmod.init_db(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[dbmod.get_db] = override
    with TestSession() as s:
        c = Company(name="Test Sécurité")
        s.add(c)
        s.flush()
        for email, role in [("chef@test.fr", "superviseur"), ("agent@test.fr", "agent"), ("autre@test.fr", "agent")]:
            s.add(User(company_id=c.id, email=email, full_name=email.split("@")[0].title(), role=role,
                       qualifications=["CQP_APS"], password_hash=hash_password("motdepasse123")))
        s.commit()
    # Pas de lifespan : la base de test est déjà initialisée
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, email):
    r = client.post("/auth/login", data={"username": email, "password": "motdepasse123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_login_refuse_mauvais_mot_de_passe(client):
    r = client.post("/auth/login", data={"username": "agent@test.fr", "password": "faux"})
    assert r.status_code == 401


def test_parcours_complet(client):
    chef, agent, autre = login(client, "chef@test.fr"), login(client, "agent@test.fr"), login(client, "autre@test.fr")

    # Le superviseur crée le site, son périmètre, 3 points de contrôle et un parcours
    corners = [offset(*SITE, dx, dy) for dx, dy in [(-100, -100), (100, -100), (100, 100), (-100, 100)]]
    site = client.post("/sites", headers=chef, json={
        "name": "Entrepôt test", "location": {"lat": SITE[0], "lon": SITE[1]},
        "perimeter": [{"lat": a, "lon": b} for a, b in corners],
    }).json()
    cps = []
    for k, (dx, dy) in enumerate([(-80, -80), (80, -80), (80, 80)]):
        lat, lon = offset(*SITE, dx, dy)
        r = client.post(f"/sites/{site['id']}/checkpoints", headers=chef,
                        json={"name": f"Point {k+1}", "location": {"lat": lat, "lon": lon}, "order_index": k})
        assert r.status_code == 201
        cps.append((r.json(), (lat, lon)))
    tpl = client.post("/round-templates", headers=chef, json={
        "site_id": site["id"], "name": "Ronde test", "checkpoint_ids": [c["id"] for c, _ in cps],
        "expected_duration_min": 10,
    }).json()

    # Un agent ne peut pas créer de site
    assert client.post("/sites", headers=agent, json={"name": "x", "location": {"lat": 0, "lon": 0}}).status_code == 403

    me = client.get("/auth/me", headers=agent).json()
    now = datetime.now(UTC)
    shift = client.post("/shifts", headers=chef, json={
        "agent_id": me["id"], "site_id": site["id"],
        "planned_start": (now - timedelta(minutes=30)).isoformat(), "planned_end": (now + timedelta(hours=8)).isoformat(),
    }).json()

    # Un autre agent ne voit pas cette vacation
    assert client.post(f"/shifts/{shift['id']}/start", headers=autre, json={}).status_code == 403

    # Prise de service sur site, depuis l'entrée
    t0 = now - timedelta(minutes=25)
    lat, lon = offset(*SITE, 0, -90)
    r = client.post(f"/shifts/{shift['id']}/start", headers=agent,
                    json={"position": {"lat": lat, "lon": lon, "accuracy_m": 8}, "at": t0.isoformat()})
    assert r.status_code == 200 and r.json()["status"] == "en_cours"
    assert r.json()["start_inside_perimeter"] is True

    # Ronde : points 1 et 3 scannés (3 trop loin), point 2 oublié
    t1 = t0 + timedelta(minutes=2)
    # Identifiants générés par l'appli : un renvoi (réseau coupé puis rétabli) ne crée pas de doublon
    rnd_body = {"id": str(uuid.uuid4()), "shift_id": shift["id"], "template_id": tpl["id"], "at": t1.isoformat()}
    rnd = client.post("/rounds", headers=agent, json=rnd_body).json()
    assert rnd["id"] == rnd_body["id"]
    assert client.post("/rounds", headers=agent, json=rnd_body).status_code == 201
    (c1, p1), (c2, p2), (c3, p3) = cps
    s1_body = {"id": str(uuid.uuid4()), "code": c1["code"], "position": {"lat": p1[0], "lon": p1[1], "accuracy_m": 5},
               "at": (t1 + timedelta(minutes=2)).isoformat()}
    s1 = client.post(f"/rounds/{rnd['id']}/scan", headers=agent, json=s1_body).json()
    assert client.post(f"/rounds/{rnd['id']}/scan", headers=agent, json=s1_body).json()["id"] == s1["id"]
    assert s1["is_valid"] is True and s1["distance_m"] < 5
    far = offset(*p3, 200, 0)
    s3 = client.post(f"/rounds/{rnd['id']}/scan", headers=agent, json={
        "code": c3["code"], "position": {"lat": far[0], "lon": far[1], "accuracy_m": 5},
        "at": (t1 + timedelta(minutes=4)).isoformat()}).json()
    assert s3["is_valid"] is False and 190 < s3["distance_m"] < 210
    assert client.post(f"/rounds/{rnd['id']}/scan", headers=agent, json={"code": "INCONNU"}).status_code == 422

    # Trajet GPS envoyé en lot (comme après une coupure réseau) + doublon ignoré
    pts = [offset(*SITE, -80 + 8 * k, -80) for k in range(20)]
    batch = [{"lat": a, "lon": b, "recorded_at": (t1 + timedelta(seconds=15 * k)).isoformat(),
              "round_id": rnd["id"], "client_id": f"p{k}"} for k, (a, b) in enumerate(pts)]
    r = client.post("/positions/batch", headers=agent, json={"shift_id": shift["id"], "positions": batch})
    assert r.json()["stored"] == 20
    client.post("/positions/batch", headers=agent, json={"shift_id": shift["id"], "positions": batch[:3]})
    # Une position datée d'avant le service est refusée (RGPD)
    r = client.post("/positions/batch", headers=agent, json={"shift_id": shift["id"], "positions": [
        {"lat": 44.0, "lon": -0.5, "recorded_at": (t0 - timedelta(hours=3)).isoformat()}]})
    assert r.json()["stored"] == 0

    client.post(f"/rounds/{rnd['id']}/end", headers=agent, json={"at": (t1 + timedelta(minutes=5)).isoformat()})

    # Incident avec photo, renvoyé deux fois (idempotence hors-ligne)
    inc_body = {"site_id": site["id"], "shift_id": shift["id"], "category": "porte_ouverte", "severity": 2,
                "title": "Porte ouverte quai", "description_raw": "Porte du quai non verrouillée", "client_id": "inc-1",
                "position": {"lat": p2[0], "lon": p2[1]}}
    inc = client.post("/incidents", headers=agent, json=inc_body).json()
    assert client.post("/incidents", headers=agent, json=inc_body).json()["id"] == inc["id"]
    att_id = str(uuid.uuid4())
    for _ in range(2):
        r = client.post(f"/incidents/{inc['id']}/attachments", headers=agent, params={"attachment_id": att_id},
                        files={"file": ("photo.jpg", b"\xff\xd8\xff fake jpeg", "image/jpeg")})
        assert r.status_code == 201 and r.json()["id"] == att_id
    assert len(client.get(f"/incidents/{inc['id']}", headers=agent).json()["attachments"]) == 1

    # Rapport de ronde consulté par le superviseur
    rep = client.get(f"/rounds/{rnd['id']}/report", headers=chef).json()
    assert rep["missed_checkpoints"] == ["Point 2"]
    assert rep["completion_pct"] == pytest.approx(66.7, abs=0.1)
    assert rep["track"]["type"] == "LineString" and len(rep["track"]["coordinates"]) == 20
    assert 140 < rep["distance_walked_m"] < 160
    assert "Scan effectué loin du point de contrôle" in rep["flags"]
    assert "1 point(s) de contrôle manqué(s)" in rep["flags"]
    assert "Ronde anormalement rapide" not in rep["flags"]

    # Carte en direct : l'agent apparaît à sa dernière position
    live = client.get("/positions/live", headers=chef).json()
    assert len(live) == 1 and live[0]["agent_name"] == "Agent"

    # Fin de service
    r = client.post(f"/shifts/{shift['id']}/end", headers=agent, json={})
    assert r.json()["status"] == "terminee"
