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
| Appli agent | React Native + Expo SDK 58 (TypeScript, Expo Router), GPS, scan QR, hors-ligne | ✅ Phase 2 |
| Tableau de bord superviseur | React + carte | ⏳ Phase 3 |
| IA & data | LLM (rapports), Isolation Forest (anomalies), OR-Tools (planning), prévisions | ⏳ Phase 4 |
| Production | Sécurité, RGPD, migrations, publication stores | ⏳ Phase 5 |

## Démarrage

```bash
cp .env.example .env            # puis changer JWT_SECRET
docker compose up -d --build    # base PostGIS (port 5433) + API (port 8000)
docker exec vigironde-api python -m app.seed --reset   # données de démo
docker exec vigironde-api python -m pytest -q          # tests
docker exec vigironde-api python -m app.demo_shift     # vacation « à commencer » pour l'agent de démo
docker exec vigironde-api python -m app.qr_sheet > docs/qr-codes-demo.html   # QR codes des points
```

Appli mobile (Expo Go sur iPhone / Android, même Wi-Fi que l'ordinateur) :

```bash
cd mobile && npm install && npx expo start      # puis scanner le QR code avec l'iPhone
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

## Appli agent (phase 2)

- **Connexion** sécurisée (jeton dans le trousseau iOS / Keystore Android).
- **Prise / fin de service** géolocalisée, avec contrôle immédiat « dans le périmètre du site ».
- **Rondes** : parcours ordonné, prochain point mis en avant, **scan QR** (lampe torche pour la nuit),
  saisie manuelle de secours, distance au point affichée et **scan à distance signalé** (anti-fraude).
- **Suivi GPS** pendant le service uniquement (un point / 15 s ou 10 m), rattaché à la ronde.
- **Incidents** : catégorie, gravité proposée automatiquement, description (dictée vocale), jusqu'à 6 photos.
- **Rapport de ronde sur carte** : périmètre, trajet GPS, points contrôlés / à distance / manqués, alertes.
- **Hors-ligne complet** : toutes les actions sont enregistrées sur le téléphone puis envoyées dans l'ordre ;
  identifiants générés par l'appli → aucun doublon même après plusieurs renvois. Bandeau d'état de synchronisation.
- Thème sombre (lisibilité de nuit, discrétion, batterie), retours haptiques.

## Fonctions de poste (inspirées du terrain)

- **Accueil en tuiles** : Fin de service, Rondes, Rapports, Main courante, Évt simple, Consignes, Pause, Clés,
  Visiteurs, SOS / PTI — avec badges (consignes non lues, clés sorties, visiteurs présents).
- **Rapports à modèles** (11 modèles : anomalie ronde, prise en compte de véhicule, alarme incendie, intrusion,
  alarme technique, vol, dégradation, personne suspecte, secours à personne, ouverture/fermeture, état des lieux),
  classés Sûreté / Sécurité / Intervention / État des lieux, avec champs propres à chaque modèle.
- **Rédaction du rapport par IA** (Claude) à partir des notes dictées par l'agent : rapport professionnel prêt à
  transmettre, relu par l'agent avant envoi ; sans clé API, mise en forme structurée sans rien inventer.
  Activer l'IA : ajouter `ANTHROPIC_API_KEY=...` dans `.env` puis `docker compose up -d`.
- **Main courante** automatique (prise de service, rondes, rapports, clés, visiteurs, consignes, pauses, alertes)
  + **Évènement simple** en un geste et notes libres.
- **PTI / travailleur isolé** : bouton SOS (appui long), détection de chute et d'immobilité avec pré-alarme et
  compte à rebours, test du PTI, suivi de la prise en charge par le PC sécurité. (Démonstration : un DATI
  professionnel doit être certifié.)
- **Consignes** de site (permanentes / temporaires) à valider « lu et compris », **registre des clés**,
  **registre des visiteurs** (véhicule, badge), **pauses**.

## Modèle de données

`companies` → `users` (rôles, qualifications CQP APS / SSIAP / SST) → `sites` (point + périmètre) →
`checkpoints` → `round_templates` → `shifts` (vacations) → `rounds` → `checkpoint_scans`,
`positions` (trajets GPS), `incidents` → `attachments`.
