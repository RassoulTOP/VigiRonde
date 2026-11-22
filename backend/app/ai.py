"""Rédaction des rapports d'événement.

L'agent dicte ou tape ses notes avec ses mots ; le rapport est remis en forme dans un style
professionnel (main courante / rapport d'intervention). Avec une clé API Anthropic
(variable ANTHROPIC_API_KEY), c'est Claude qui rédige ; sinon un rapport structuré est
construit à partir du modèle de rapport, sans jamais inventer de faits.
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
PARIS = ZoneInfo("Europe/Paris")
MODEL = "claude-opus-5-5"

CATEGORY_LABELS = {
    "surete": "Sûreté",
    "securite": "Sécurité",
    "intervention": "Intervention",
    "etat_des_lieux": "État des lieux",
    "technique": "Technique",
}

SYSTEM_PROMPT = """Tu rédiges des rapports d'événement pour des agents de sécurité privée en France.
On te donne les notes brutes de l'agent (souvent dictées, avec des fautes ou du langage oral),
les réponses à un formulaire et le contexte (site, date, heure, agent).

Écris un rapport clair, factuel et professionnel, en français, prêt à être transmis au client
et au chef de poste. Règles :
- N'invente aucun fait, aucun nom, aucune heure, aucun chiffre. Si une information utile manque,
  écris « non précisé ».
- Style neutre et impersonnel de main courante (« L'agent constate… », « Il est procédé à… »).
- Corrige l'orthographe et la grammaire, garde les termes du métier (levée de doute, PC sécurité,
  SSIAP, ronde, main courante, procès-verbal…).
- Texte brut, sans Markdown. Structure exactement :
RAPPORT D'ÉVÉNEMENT — <type>
Date et heure : …
Site : …
Agent : …

Constatations :
…

Mesures prises :
…

Suites à donner / recommandations :
…
- Les recommandations doivent découler des faits rapportés ; s'il n'y en a pas, écris « aucune »."""


@dataclass
class ReportContext:
    template_name: str
    category: str | None
    title: str
    notes: str
    answers: dict = field(default_factory=dict)
    fields: list = field(default_factory=list)  # définition du formulaire, pour les libellés
    site_name: str = ""
    agent_name: str = ""
    occurred_at: datetime | None = None
    severity: int | None = None


def _answers_lines(ctx: ReportContext) -> list[str]:
    labels = {f.get("key"): f.get("label", f.get("key")) for f in ctx.fields}
    lines = []
    for key, value in ctx.answers.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, bool):
            value = "oui" if value else "non"
        elif isinstance(value, list):
            value = ", ".join(map(str, value))
        lines.append(f"- {labels.get(key, key)} : {value}")
    return lines


def _when(ctx: ReportContext) -> str:
    if not ctx.occurred_at:
        return "non précisé"
    return ctx.occurred_at.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M")


def template_report(ctx: ReportContext) -> str:
    """Rapport structuré sans IA : mise en page fiable, contenu = ce que l'agent a saisi."""
    kind = ctx.template_name + (f" ({CATEGORY_LABELS.get(ctx.category, ctx.category)})" if ctx.category else "")
    details = _answers_lines(ctx)
    notes = " ".join(ctx.notes.split())
    if notes and notes[0].islower():
        notes = notes[0].upper() + notes[1:]
    if notes and notes[-1] not in ".!?":
        notes += "."
    parts = [
        f"RAPPORT D'ÉVÉNEMENT — {kind}",
        f"Objet : {ctx.title}",
        f"Date et heure : {_when(ctx)}",
        f"Site : {ctx.site_name or 'non précisé'}",
        f"Agent : {ctx.agent_name or 'non précisé'}",
    ]
    if ctx.severity:
        parts.append(f"Gravité : {ctx.severity}/5")
    parts += ["", "Constatations :", notes or "non précisé"]
    if details:
        parts += ["", "Éléments relevés :", *details]
    return "\n".join(parts)


def _claude_report(ctx: ReportContext) -> str | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    details = "\n".join(_answers_lines(ctx)) or "(aucun)"
    user = (
        f"Type de rapport : {ctx.template_name}"
        + (f" — catégorie {CATEGORY_LABELS.get(ctx.category, ctx.category)}" if ctx.category else "")
        + f"\nObjet saisi par l'agent : {ctx.title}"
        + f"\nDate et heure : {_when(ctx)}\nSite : {ctx.site_name}\nAgent : {ctx.agent_name}"
        + (f"\nGravité estimée par l'agent : {ctx.severity}/5" if ctx.severity else "")
        + f"\n\nRéponses au formulaire :\n{details}"
        + f"\n\nNotes de l'agent (brutes) :\n<<<\n{ctx.notes}\n>>>"
    )
    try:
        client = anthropic.Anthropic(timeout=60.0, max_retries=1)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIConnectionError:
        log.warning("Claude injoignable : rapport structuré utilisé")
        return None
    except anthropic.APIStatusError as e:
        log.warning("Erreur API Claude %s : rapport structuré utilisé", e.status_code)
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None


def write_report(ctx: ReportContext) -> tuple[str, str]:
    """Renvoie (rapport, source) avec source = "ia" ou "modele"."""
    text = _claude_report(ctx)
    if text:
        return text, "ia"
    return template_report(ctx), "modele"
