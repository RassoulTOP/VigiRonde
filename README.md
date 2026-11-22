# VigiRonde

**Gestion intelligente des agents de sécurité** : vacations géolocalisées, rondes à points de contrôle
(QR / NFC), rapports de ronde avec trajet GPS, incidents avec photos, et — à venir — rapports d'incident
rédigés par IA, détection d'anomalies, tableau de bord analytique et planning intelligent.

> Projet personnel de Mouhamad TOP, agent de sécurité en reconversion Data / IA.
> Toutes les données de démonstration sont fictives.

## Architecture

| Partie | Technologies | État |
|---|---|---|
| API | FastAPI (Python 3.12), SQLAlchemy 2, PostgreSQL 16 + PostGIS | ✅ Phase 1 |
| Données de démo | Générateur réaliste (Gironde, 60 jours, anomalies injectées) | ✅ Phase 1 |
| Appli agent | React Native + Expo (TypeScript), GPS, scan QR, hors-ligne | ⏳ Phase 2 |
| Tableau de bord superviseur | React + carte | ⏳ Phase 3 |
| IA & data | LLM (rapports), Isolation Forest (anomalies), OR-Tools (planning), prévisions | ⏳ Phase 4 |
| Production | Sécurité, RGPD, migrations, publication stores | ⏳ Phase 5 |

## Démarrage

```bash
cp .env.example .env            # puis changer JWT_SECRET
docker compose up -d --build    # base PostGIS (port 5433) + API (port 8000)
docker exec vigironde-api python -m app.seed --reset   # données de démo
docker exec vigironde-api python -m pytest -q          # tests
```

Documentation interactive de l'API : <http://localhost:8000/docs>

Comptes de démo (mot de passe `VigiRonde2026!`) :
`admin@demo.vigironde.fr`, `superviseur@demo.vigironde.fr`, `agent@demo.vigironde.fr`.

## Fonctionnalités de l'API (phase 1)

- **Authentification JWT** et rôles `admin` / `superviseur` / `agent` ; chaque société ne voit que ses données,
  chaque agent ne voit que ses vacations, rondes et incidents.
- **Sites** avec périmètre géographique (géorepérage), **points de contrôle** (code QR/NFC) et **parcours de ronde**.
- **Vacations** : prise et fin de service avec position GPS ; contrôle « prise de service dans le périmètre ».
- **Rondes** : scan des points de contrôle avec vérification de la distance au point (anti-fraude).
- **Positions GPS** envoyées par lots (mode hors-ligne, dédoublonnage) et **uniquement pendant le service** (RGPD).
- **Carte en direct** : dernière position de chaque agent en service.
- **Rapport de ronde** : points passés / manqués avec heure et distance, ordre de passage, durée réelle vs prévue,
  distance parcourue, trajet GPS (GeoJSON) et alertes automatiques
  (points manqués, scan à distance, ronde trop rapide ou trop longue, ordre non respecté, ronde interrompue).
- **Incidents** : catégorie, gravité 1–5, position, photos / vidéos / audio, renvoi idempotent depuis le mode hors-ligne.

## Modèle de données

`companies` → `users` (rôles, qualifications CQP APS / SSIAP / SST) → `sites` (point + périmètre) →
`checkpoints` → `round_templates` → `shifts` (vacations) → `rounds` → `checkpoint_scans`,
`positions` (trajets GPS), `incidents` → `attachments`.
