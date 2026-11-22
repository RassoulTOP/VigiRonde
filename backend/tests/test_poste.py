"""Fonctions de poste : rapports à modèles, main courante, PTI, consignes, clés, visiteurs, pauses."""
import uuid
from datetime import UTC, datetime, timedelta

from app.seed import offset
from tests.conftest import login

SITE = (44.90, -0.60)


def setup_site_and_shift(client, chef, agent):
    corners = [offset(*SITE, dx, dy) for dx, dy in [(-50, -50), (50, -50), (50, 50), (-50, 50)]]
    site = client.post("/sites", headers=chef, json={
        "name": "Site poste", "location": {"lat": SITE[0], "lon": SITE[1]},
        "perimeter": [{"lat": a, "lon": b} for a, b in corners]}).json()
    me = client.get("/auth/me", headers=agent).json()
    now = datetime.now(UTC)
    shift = client.post("/shifts", headers=chef, json={
        "agent_id": me["id"], "site_id": site["id"],
        "planned_start": (now - timedelta(minutes=10)).isoformat(),
        "planned_end": (now + timedelta(hours=8)).isoformat()}).json()
    r = client.post(f"/shifts/{shift['id']}/start", headers=agent,
                    json={"position": {"lat": SITE[0], "lon": SITE[1], "accuracy_m": 5}})
    assert r.status_code == 200
    return site, shift


def test_fonctions_de_poste(client):
    chef, agent, autre = login(client, "chef@test.fr"), login(client, "agent@test.fr"), login(client, "autre@test.fr")
    site, shift = setup_site_and_shift(client, chef, agent)

    # --- Rapport à modèle : brouillon puis envoi, rapport mis en forme ---
    tpl = client.post("/report-templates", headers=chef, json={
        "name": "Prise en compte de véhicule", "category": "surete", "default_severity": 1,
        "fields": [{"key": "plaque", "label": "Immatriculation", "type": "text", "required": True},
                   {"key": "motif", "label": "Motif", "type": "select", "options": ["Livraison", "Visiteur"]}]}).json()
    assert client.post("/report-templates", headers=agent, json={"name": "x", "category": "surete"}).status_code == 403
    assert [t["name"] for t in client.get("/report-templates", headers=agent, params={"site_id": site["id"]}).json()] \
        == ["Prise en compte de véhicule"]
    draft = client.post("/reports/draft", headers=agent, json={
        "site_id": site["id"], "template_id": tpl["id"], "title": "Camion devant le portail",
        "description": "camion blanc garé devant le portail le chauffeur attend la livraison",
        "answers": {"plaque": "AB-123-CD", "motif": "Livraison"}}).json()
    assert draft["source"] in ("ia", "modele")
    assert "AB-123-CD" in draft["text"] and "Site poste" in draft["text"]
    inc_id = str(uuid.uuid4())
    body = {"id": inc_id, "site_id": site["id"], "shift_id": shift["id"], "category": "autre", "severity": 1,
            "title": "Camion devant le portail", "description_raw": "camion blanc", "template_id": tpl["id"],
            "answers": {"plaque": "AB-123-CD"}}
    inc = client.post("/incidents", headers=agent, json=body).json()
    assert inc["id"] == inc_id and inc["report_category"] == "surete" and inc["answers"]["plaque"] == "AB-123-CD"
    # Sans rapport fourni, le serveur le rédige en tâche de fond
    assert client.get(f"/incidents/{inc_id}", headers=agent).json()["report_ai"]

    # --- Main courante : événement en un geste, idempotent, + entrées automatiques ---
    eid = str(uuid.uuid4())
    for _ in range(2):
        r = client.post("/journal", headers=agent, json={"id": eid, "shift_id": shift["id"], "text": "Ouverture du portail"})
        assert r.status_code == 201
    texts = [e["text"] for e in client.get("/journal", headers=agent, params={"shift_id": shift["id"]}).json()]
    assert texts.count("Ouverture du portail") == 1
    assert any(t.startswith("Prise de service (dans le périmètre)") for t in texts)
    assert any("Prise en compte de véhicule" in t for t in texts)
    assert client.get("/journal", headers=autre, params={"shift_id": shift["id"]}).status_code == 403

    # --- PTI : test, SOS, prise en charge, clôture ; fausse alerte annulée ---
    test = client.post("/alerts", headers=agent, json={"kind": "test", "shift_id": shift["id"]}).json()
    assert test["status"] == "close"
    sos_id = str(uuid.uuid4())
    sos = client.post("/alerts", headers=agent, json={
        "id": sos_id, "kind": "sos", "position": {"lat": SITE[0], "lon": SITE[1], "accuracy_m": 6}}).json()
    assert sos["status"] == "active" and sos["site_name"] == "Site poste" and sos["location"]["lat"] == SITE[0]
    assert client.post("/alerts", headers=agent, json={"id": sos_id, "kind": "sos"}).json()["id"] == sos_id
    active = client.get("/alerts", headers=chef, params={"active": True}).json()
    assert [a["id"] for a in active] == [sos_id]
    assert client.post(f"/alerts/{sos_id}/handle", headers=agent, json={}).status_code == 403
    h = client.post(f"/alerts/{sos_id}/handle", headers=chef, json={"note": "Appel de l'agent en cours"}).json()
    assert h["status"] == "prise_en_charge" and h["handled_by_name"] == "Chef"
    assert client.get(f"/alerts/{sos_id}", headers=agent).json()["handled_by_name"] == "Chef"
    assert client.post(f"/alerts/{sos_id}/close", headers=chef, json={}).json()["status"] == "close"
    fa = client.post("/alerts", headers=agent, json={"kind": "immobilite"}).json()
    assert client.post(f"/alerts/{fa['id']}/cancel", headers=agent, json={}).json()["status"] == "annulee"

    # --- Consignes : liste, validation, compteur ---
    c1 = client.post("/instructions", headers=chef, json={"site_id": site["id"], "title": "Alarme incendie",
                                                         "body": "Levée de doute puis 18.", "important": True}).json()
    client.post("/instructions", headers=chef, json={
        "site_id": site["id"], "title": "Ancienne consigne", "body": "Expirée",
        "valid_to": (datetime.now(UTC) - timedelta(days=1)).isoformat()})
    lst = client.get("/instructions", headers=agent, params={"site_id": site["id"]}).json()
    assert [i["title"] for i in lst] == ["Alarme incendie"] and lst[0]["acked_at"] is None
    assert client.get("/poste/summary", headers=agent, params={"site_id": site["id"]}).json()["instructions_unread"] == 1
    for _ in range(2):
        assert client.post(f"/instructions/{c1['id']}/ack", headers=agent, json={"shift_id": shift["id"]}).json()["acked_at"]
    assert client.get("/poste/summary", headers=agent, params={"site_id": site["id"]}).json()["instructions_unread"] == 0

    # --- Clés : sortie, double sortie refusée, retour ---
    from app import db as dbmod
    from app.models import SiteKey
    s = next(client.app.dependency_overrides[dbmod.get_db]())
    k = SiteKey(site_id=uuid.UUID(site["id"]), label="Clé chaufferie", code=f"CLE-{uuid.uuid4().hex[:6]}")
    s.add(k)
    s.commit()
    mid = str(uuid.uuid4())
    out = client.post(f"/keys/{k.id}/movements", headers=agent, json={
        "id": mid, "action": "sortie", "holder_name": "Jean Technicien", "holder_company": "Maintenance", "shift_id": shift["id"]}).json()
    assert out["is_out"] and out["holder_name"] == "Jean Technicien"
    assert client.post(f"/keys/{k.id}/movements", headers=agent, json={"id": mid, "action": "sortie", "holder_name": "Jean Technicien"}).status_code == 201
    assert client.post(f"/keys/{k.id}/movements", headers=agent, json={"action": "sortie", "holder_name": "Autre"}).status_code == 409
    back = client.post(f"/keys/{k.id}/movements", headers=agent, json={"action": "retour", "holder_name": "Jean Technicien"}).json()
    assert back["is_out"] is False

    # --- Visiteurs : arrivée (idempotente), présents, départ ---
    vid = str(uuid.uuid4())
    for _ in range(2):
        v = client.post("/visits", headers=agent, json={"id": vid, "site_id": site["id"], "shift_id": shift["id"],
                                                        "visitor_name": "Nadia B.", "company": "Nettoyage",
                                                        "vehicle_plate": "ab 456 cd"}).json()
    assert v["vehicle_plate"] == "AB-456-CD"
    assert len(client.get("/visits", headers=agent, params={"site_id": site["id"], "present": True}).json()) == 1
    assert client.post(f"/visits/{vid}/exit", headers=agent, json={}).json()["left_at"]
    assert client.get("/visits", headers=agent, params={"site_id": site["id"], "present": True}).json() == []

    # --- Pause : début, visible dans la vacation, fin ---
    pid = str(uuid.uuid4())
    assert client.post(f"/shifts/{shift['id']}/pauses", headers=agent, json={"id": pid}).status_code == 201
    assert client.post(f"/shifts/{shift['id']}/pauses", headers=agent, json={}).status_code == 409
    assert client.get("/shifts/current", headers=agent).json()["active_pause_id"] == pid
    assert client.post(f"/shifts/{shift['id']}/pauses/{pid}/end", headers=agent, json={}).json()["ended_at"]
    assert client.get("/shifts/current", headers=agent).json()["active_pause_id"] is None

    texts = [e["text"] for e in client.get("/journal", headers=chef, params={"shift_id": shift["id"]}).json()]
    for expected in ("Test du PTI réussi", "Alerte SOS déclenchée", "Consigne lue et validée : « Alarme incendie »",
                     "Clé « Clé chaufferie » remise à Jean Technicien (Maintenance)", "Début de pause"):
        assert expected in texts, expected
    assert any(t.startswith("Arrivée visiteur : Nadia B.") for t in texts)
