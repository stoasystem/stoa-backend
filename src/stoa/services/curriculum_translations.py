"""Display-title translations for the seeded Math ZAP curriculum.

Exercise prompts stay German — the ZAP exam itself is German, so practising
in German is correct. Only the navigational titles (subject/topic/unit/lesson
names shown in cards, headers and roadmaps) are translated, so a student
reading the app in English/French/Italian is not dropped into a German label
in the middle of an otherwise-translated screen.

Keyed by the content id from stoa.db.repositories.practice_repo (subject_id,
topic_id, unit_id, lesson_id). A missing id or locale falls back to the
stored German title, so newly seeded content is never hidden while its
translation is pending.
"""
from __future__ import annotations

TITLE_TRANSLATIONS: dict[str, dict[str, str]] = {
    # subject
    "mathematics": {"en": "Mathematics", "fr": "Mathématiques", "it": "Matematica"},
    # topics
    "brueche": {"en": "Fractions", "fr": "Fractions", "it": "Frazioni"},
    "gleichungen": {"en": "Equations", "fr": "Équations", "it": "Equazioni"},
    "geometrie": {"en": "Geometry", "fr": "Géométrie", "it": "Geometria"},
    "prozentrechnung": {
        "en": "Percentages and ratios",
        "fr": "Pourcentages et proportions",
        "it": "Percentuali e proporzioni",
    },
    "textaufgaben": {"en": "Word problems", "fr": "Problèmes concrets", "it": "Problemi con testo"},
    # units
    "brueche-u1": {
        "en": "Understanding and reducing fractions",
        "fr": "Comprendre et simplifier les fractions",
        "it": "Capire e semplificare le frazioni",
    },
    "brueche-u2": {
        "en": "Calculating with fractions",
        "fr": "Calculer avec des fractions",
        "it": "Calcolare con le frazioni",
    },
    "gleichungen-u1": {
        "en": "Solving simple equations",
        "fr": "Résoudre des équations simples",
        "it": "Risolvere equazioni semplici",
    },
    "gleichungen-u2": {
        "en": "Equations from word problems",
        "fr": "Équations issues de problèmes concrets",
        "it": "Equazioni da problemi con testo",
    },
    "geometrie-u1": {"en": "Area and perimeter", "fr": "Aire et périmètre", "it": "Area e perimetro"},
    "geometrie-u2": {"en": "Volume and surface area", "fr": "Volume et surface", "it": "Volume e superficie"},
    "prozentrechnung-u1": {
        "en": "Calculating percentages",
        "fr": "Calculer des pourcentages",
        "it": "Calcolare le percentuali",
    },
    "prozentrechnung-u2": {
        "en": "Ratios and proportionality",
        "fr": "Proportions et proportionnalité",
        "it": "Rapporti e proporzionalità",
    },
    "textaufgaben-u1": {
        "en": "Combined word problems",
        "fr": "Problèmes combinés",
        "it": "Problemi combinati",
    },
    "textaufgaben-u2": {
        "en": "ZAP exam-style tasks",
        "fr": "Exercices type examen ZAP",
        "it": "Esercizi in stile esame ZAP",
    },
    # lessons
    "brueche-l1": {
        "en": "Reading and reducing fractions",
        "fr": "Lire et simplifier les fractions",
        "it": "Leggere e semplificare le frazioni",
    },
    "brueche-l2": {"en": "Equivalent fractions", "fr": "Fractions équivalentes", "it": "Frazioni equivalenti"},
    "brueche-l3": {
        "en": "Adding and subtracting fractions",
        "fr": "Additionner et soustraire des fractions",
        "it": "Addizionare e sottrarre frazioni",
    },
    "brueche-l4": {
        "en": "Multiplying fractions",
        "fr": "Multiplier des fractions",
        "it": "Moltiplicare le frazioni",
    },
    "gleichungen-l1": {
        "en": "One-step equations",
        "fr": "Équations à une étape",
        "it": "Equazioni a un passaggio",
    },
    "gleichungen-l2": {
        "en": "Two-step equations",
        "fr": "Équations à deux étapes",
        "it": "Equazioni a due passaggi",
    },
    "gleichungen-l3": {
        "en": "Setting up an equation",
        "fr": "Mettre un problème en équation",
        "it": "Impostare un'equazione",
    },
    "gleichungen-l4": {
        "en": "ZAP tasks: equations",
        "fr": "Exercices ZAP : équations",
        "it": "Esercizi ZAP: equazioni",
    },
    "geometrie-l1": {"en": "Rectangle and triangle", "fr": "Rectangle et triangle", "it": "Rettangolo e triangolo"},
    "geometrie-l2": {
        "en": "Circle area and circumference",
        "fr": "Aire et circonférence du cercle",
        "it": "Area e circonferenza del cerchio",
    },
    "geometrie-l3": {
        "en": "Volume of cuboid and cube",
        "fr": "Volume du pavé et du cube",
        "it": "Volume di parallelepipedo e cubo",
    },
    "geometrie-l4": {"en": "Pythagorean theorem", "fr": "Théorème de Pythagore", "it": "Teorema di Pitagora"},
    "prozentrechnung-l1": {
        "en": "Basic percentage problems",
        "fr": "Exercices de base sur les pourcentages",
        "it": "Esercizi di base sulle percentuali",
    },
    "prozentrechnung-l2": {
        "en": "Discount, price increase, VAT",
        "fr": "Remise, hausse de prix, TVA",
        "it": "Sconto, aumento di prezzo, IVA",
    },
    "prozentrechnung-l3": {"en": "Ratios", "fr": "Proportions", "it": "Rapporti"},
    "prozentrechnung-l4": {
        "en": "ZAP tasks: percentages & ratios",
        "fr": "Exercices ZAP : pourcentages et proportions",
        "it": "Esercizi ZAP: percentuali e rapporti",
    },
    "textaufgaben-l1": {"en": "Money and shopping", "fr": "Argent et achats", "it": "Denaro e acquisti"},
    "textaufgaben-l2": {
        "en": "Time, speed, distance",
        "fr": "Temps, vitesse, distance",
        "it": "Tempo, velocità, distanza",
    },
    "textaufgaben-l3": {
        "en": "ZAP 2023-2025: task type A",
        "fr": "ZAP 2023-2025 : type d'exercice A",
        "it": "ZAP 2023-2025: tipo di esercizio A",
    },
    "textaufgaben-l4": {
        "en": "ZAP 2023-2025: task type B",
        "fr": "ZAP 2023-2025 : type d'exercice B",
        "it": "ZAP 2023-2025: tipo di esercizio B",
    },
}


def translated_title(content_id: str, title: str, locale: str) -> str:
    """Return the display title in the requested locale, falling back to German."""
    if locale == "de":
        return title
    return TITLE_TRANSLATIONS.get(content_id, {}).get(locale, title)
