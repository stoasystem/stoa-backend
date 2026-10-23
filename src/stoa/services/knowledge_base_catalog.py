"""Where the imported knowledge base hangs in the star map.

The knowledge base brings knowledge points for mathematics from the first year of
primary school to upper secondary, for English and for physics. Each knowledge
point becomes one skill, and one lesson practising it, under one star (a unit) of
a nebula (a topic). Mathematics keeps its seven nebulae: what the ZAP stars did
not cover gets stars of its own in the nebula of its field. English and physics
are subjects of their own with nebulae of their own.

This module holds the rows the seed writes for those stars, nebulae and subjects,
their titles in de/en/fr/it, and the skill vocabulary of the imported knowledge
points, read from `knowledge_base_skills.json` next to it. The import script
(scripts/knowledge_base_import.py) writes that file; it lists, per skill, the star
it hangs under and its title in the four languages.
"""

from __future__ import annotations

from functools import cache
import json
from pathlib import Path
from typing import Any

SKILLS_FILE = Path(__file__).with_name("knowledge_base_skills.json")
LOCALES = ("de", "en", "fr", "it")


def _titles(de: str, en: str, fr: str, it: str) -> dict[str, str]:
    return {"de": de, "en": en, "fr": fr, "it": it}


#: Stars added to the mathematics nebulae, in the order they follow the ZAP stars.
#: The description tells the import which knowledge points belong there.
MATH_UNITS: tuple[dict[str, Any], ...] = (
    {
        "unit_id": "zahlen-u5", "topic_id": "zahlen",
        "titles": _titles("Zahlaufbau und Grundrechenarten", "Number sense and the four operations",
                          "Construction des nombres et quatre opérations",
                          "Struttura dei numeri e quattro operazioni"),
        "description": "Zählen, Zahlen bis zu einer Million lesen und schreiben, Addition, "
                       "Subtraktion, Einmaleins, Division mit Rest, schriftliches Rechnen.",
    },
    {
        "unit_id": "zahlen-u6", "topic_id": "zahlen",
        "titles": _titles("Negative und rationale Zahlen", "Negative and rational numbers",
                          "Nombres négatifs et rationnels", "Numeri negativi e razionali"),
        "description": "Positive und negative Zahlen, Gegenzahl, Betrag, Rechnen mit rationalen Zahlen.",
    },
    {
        "unit_id": "zahlen-u7", "topic_id": "zahlen",
        "titles": _titles("Potenzen, Wurzeln und reelle Zahlen", "Powers, roots and real numbers",
                          "Puissances, racines et nombres réels", "Potenze, radici e numeri reali"),
        "description": "Potenzen, Quadrat- und Kubikwurzeln, irrationale und reelle Zahlen, "
                       "Wurzelterme, wissenschaftliche Schreibweise.",
    },
    {
        "unit_id": "zahlen-u8", "topic_id": "zahlen",
        "titles": _titles("Komplexe Zahlen", "Complex numbers", "Nombres complexes", "Numeri complessi"),
        "description": "Imaginäre Einheit, Rechnen mit komplexen Zahlen, Gaußsche Zahlenebene.",
    },
    {
        "unit_id": "zahlen-u9", "topic_id": "zahlen",
        "titles": _titles("Mengen und Logik", "Sets and logic", "Ensembles et logique", "Insiemi e logica"),
        "description": "Mengen und Mengenoperationen, Aussagen, notwendige und hinreichende "
                       "Bedingungen, Quantoren.",
    },
    {
        "unit_id": "gleichungen-u3", "topic_id": "gleichungen",
        "titles": _titles("Terme und Termumformungen", "Algebraic expressions",
                          "Expressions algébriques", "Espressioni algebriche"),
        "description": "Variablen und Terme, Polynome addieren und multiplizieren, binomische "
                       "Formeln, Faktorisieren, Bruchterme.",
    },
    {
        "unit_id": "gleichungen-u4", "topic_id": "gleichungen",
        "titles": _titles("Gleichungssysteme", "Systems of equations", "Systèmes d'équations",
                          "Sistemi di equazioni"),
        "description": "Lineare Gleichungssysteme mit zwei oder drei Unbekannten.",
    },
    {
        "unit_id": "gleichungen-u5", "topic_id": "gleichungen",
        "titles": _titles("Ungleichungen", "Inequalities", "Inéquations", "Disequazioni"),
        "description": "Lineare und quadratische Ungleichungen, Ungleichungssysteme, "
                       "Eigenschaften von Ungleichungen.",
    },
    {
        "unit_id": "gleichungen-u6", "topic_id": "gleichungen",
        "titles": _titles("Quadratische Gleichungen", "Quadratic equations",
                          "Équations du second degré", "Equazioni di secondo grado"),
        "description": "Quadratische Gleichungen lösen, quadratische Ergänzung, Lösungsformel, Diskriminante.",
    },
    {
        "unit_id": "gleichungen-u7", "topic_id": "gleichungen",
        "titles": _titles("Funktionen", "Functions", "Fonctions", "Funzioni"),
        "description": "Funktionsbegriff, lineare, quadratische und umgekehrt proportionale "
                       "Funktionen, Eigenschaften von Funktionen.",
    },
    {
        "unit_id": "gleichungen-u8", "topic_id": "gleichungen",
        "titles": _titles("Exponential- und Logarithmusfunktionen", "Exponential and logarithmic functions",
                          "Fonctions exponentielles et logarithmes",
                          "Funzioni esponenziali e logaritmiche"),
        "description": "Potenzen mit rationalen Exponenten, Exponentialfunktionen, Logarithmen, "
                       "Logarithmusfunktionen, Wachstumsmodelle.",
    },
    {
        "unit_id": "gleichungen-u9", "topic_id": "gleichungen",
        "titles": _titles("Trigonometrische Funktionen", "Trigonometric functions",
                          "Fonctions trigonométriques", "Funzioni trigonometriche"),
        "description": "Bogenmass, Sinus, Kosinus und Tangens am Einheitskreis, ihre Graphen, "
                       "trigonometrische Formeln und Identitäten.",
    },
    {
        "unit_id": "gleichungen-u10", "topic_id": "gleichungen",
        "titles": _titles("Ableitungen", "Derivatives", "Dérivées", "Derivate"),
        "description": "Änderungsrate, Ableitung, Ableitungsregeln, Monotonie, Extremwerte.",
    },
    {
        "unit_id": "geometrie-u5", "topic_id": "geometrie",
        "titles": _titles("Linien, Winkel und Dreiecke", "Lines, angles and triangles",
                          "Droites, angles et triangles", "Rette, angoli e triangoli"),
        "description": "Strecken, Geraden, Winkel, Parallelen und Senkrechten, Dreiecke, "
                       "Kongruenz, Winkelsätze.",
    },
    {
        "unit_id": "geometrie-u6", "topic_id": "geometrie",
        "titles": _titles("Vierecke und Kreise", "Quadrilaterals and circles",
                          "Quadrilatères et cercles", "Quadrilateri e cerchi"),
        "description": "Eigenschaften von Vierecken, Kreis, Sehnen, Tangenten, Winkel am Kreis.",
    },
    {
        "unit_id": "geometrie-u7", "topic_id": "geometrie",
        "titles": _titles("Ähnlichkeit und Trigonometrie im Dreieck", "Similarity and triangle trigonometry",
                          "Similitude et trigonométrie du triangle",
                          "Similitudine e trigonometria del triangolo"),
        "description": "Ähnliche Figuren, Strahlensätze, Sinus, Kosinus und Tangens im "
                       "rechtwinkligen Dreieck, Sinus- und Kosinussatz.",
    },
    {
        "unit_id": "geometrie-u8", "topic_id": "geometrie",
        "titles": _titles("Vektoren", "Vectors", "Vecteurs", "Vettori"),
        "description": "Vektoren in der Ebene und im Raum, Vektoroperationen, Skalarprodukt.",
    },
    {
        "unit_id": "geometrie-u9", "topic_id": "geometrie",
        "titles": _titles("Analytische Geometrie", "Analytic geometry", "Géométrie analytique",
                          "Geometria analitica"),
        "description": "Geraden- und Kreisgleichungen, Ellipse, Hyperbel und Parabel.",
    },
    {
        "unit_id": "geometrie-u10", "topic_id": "geometrie",
        "titles": _titles("Raumgeometrie", "Solid geometry", "Géométrie dans l'espace", "Geometria solida"),
        "description": "Lage von Punkten, Geraden und Ebenen im Raum, Körper, Winkel und "
                       "Abstände im Raum.",
    },
    {
        "unit_id": "daten-u3", "topic_id": "daten",
        "titles": _titles("Wahrscheinlichkeit", "Probability", "Probabilités", "Probabilità"),
        "description": "Zufallsexperimente, Ereignisse, Wahrscheinlichkeiten berechnen, "
                       "bedingte Wahrscheinlichkeit.",
    },
    {
        "unit_id": "daten-u4", "topic_id": "daten",
        "titles": _titles("Statistik", "Statistics", "Statistique", "Statistica"),
        "description": "Daten erheben, Stichproben, Streuung, Häufigkeitsverteilungen, "
                       "Zusammenhänge zwischen zwei Merkmalen.",
    },
    {
        "unit_id": "daten-u5", "topic_id": "daten",
        "titles": _titles("Zufallsvariablen und Verteilungen", "Random variables and distributions",
                          "Variables aléatoires et lois", "Variabili aleatorie e distribuzioni"),
        "description": "Zufallsvariablen, Erwartungswert, Binomial-, hypergeometrische und Normalverteilung.",
    },
)

#: Units the import may file mathematics knowledge points under: the ZAP stars and
#: the stars above. Titles of the ZAP stars live in the seed and curriculum_translations.
ZAP_UNITS: dict[str, str] = {
    "zahlen-u1": "Rechnen mit natürlichen Zahlen und Dezimalzahlen",
    "zahlen-u2": "Stellenwerte und Zahlenstrahl",
    "zahlen-u3": "Teiler und Vielfache",
    "zahlen-u4": "Muster und Folgen (auch arithmetische und geometrische Folgen)",
    "brueche-u1": "Brüche verstehen und kürzen (auch Dezimalbrüche einführen)",
    "brueche-u2": "Brüche rechnen",
    "gleichungen-u1": "Einfache Gleichungen lösen",
    "gleichungen-u2": "Gleichungen aus Sachaufgaben",
    "geometrie-u1": "Fläche und Umfang",
    "geometrie-u2": "Volumen und Oberfläche (auch Satz des Pythagoras)",
    "geometrie-u3": "Koordinaten und Abbildungen (Spiegelung, Drehung, Verschiebung)",
    "geometrie-u4": "Räumliches Vorstellen (Ansichten, Netze, Körper erkennen)",
    "prozentrechnung-u1": "Prozentwert berechnen",
    "prozentrechnung-u2": "Verhältnisse und Proportionalität",
    "groessen-u1": "Masseinheiten umrechnen (Länge, Fläche, Gewicht, Hohlmass)",
    "groessen-u2": "Geld und Preise",
    "groessen-u3": "Zeit, Geschwindigkeit und Weg (auch Uhrzeit, Kalender)",
    "daten-u1": "Durchschnitt und Diagramme",
    "daten-u2": "Kombinatorik",
}


def _subject_topics(subject_id: str, topics: tuple[tuple[str, dict[str, str]], ...]) -> list[dict]:
    return [
        {"topic_id": topic_id, "subject_id": subject_id, "titles": titles, "order": order}
        for order, (topic_id, titles) in enumerate(topics, start=1)
    ]


#: English: one nebula per strand, one star per school stage. Which star a
#: knowledge point goes to follows from its strand and grade alone.
ENGLISH_STAGES: tuple[tuple[str, dict[str, str]], ...] = (
    ("u1", _titles("Primarstufe", "Primary level", "Degré primaire", "Scuola elementare")),
    ("u2", _titles("Sekundarstufe I", "Lower secondary", "Secondaire I", "Secondario I")),
    ("u3", _titles("Sekundarstufe II", "Upper secondary", "Secondaire II", "Secondario II")),
)
ENGLISH_TOPICS: tuple[tuple[str, dict[str, str]], ...] = (
    ("englisch-aussprache", _titles("Buchstaben und Aussprache", "Letters and pronunciation",
                                    "Lettres et prononciation", "Lettere e pronuncia")),
    ("englisch-wortschatz", _titles("Wortschatz", "Vocabulary", "Vocabulaire", "Lessico")),
    ("englisch-grammatik", _titles("Grammatik", "Grammar", "Grammaire", "Grammatica")),
    ("englisch-alltag", _titles("Alltagssprache", "Everyday expressions", "Expressions courantes",
                                "Espressioni quotidiane")),
    ("englisch-lesen-schreiben", _titles("Lesen und Schreiben", "Reading and writing",
                                         "Lecture et écriture", "Lettura e scrittura")),
)

#: Physics: nebulae by field, stars by area; the import files each knowledge point
#: under the star whose description fits it.
PHYSICS_TOPICS: tuple[tuple[str, dict[str, str]], ...] = (
    ("physik-mechanik", _titles("Mechanik", "Mechanics", "Mécanique", "Meccanica")),
    ("physik-elektrizitaet", _titles("Elektrizität und Magnetismus", "Electricity and magnetism",
                                     "Électricité et magnétisme", "Elettricità e magnetismo")),
    ("physik-waerme", _titles("Wärme und Materie", "Heat and matter", "Chaleur et matière",
                              "Calore e materia")),
    ("physik-optik-akustik", _titles("Schall und Licht", "Sound and light", "Son et lumière",
                                     "Suono e luce")),
    ("physik-modern", _titles("Moderne Physik", "Modern physics", "Physique moderne", "Fisica moderna")),
    ("physik-praxis", _titles("Messen und Experimentieren", "Measuring and experimenting",
                              "Mesurer et expérimenter", "Misurare e sperimentare")),
)
PHYSICS_UNITS: tuple[dict[str, Any], ...] = (
    {"unit_id": "physik-mechanik-u1", "topic_id": "physik-mechanik",
     "titles": _titles("Bewegung", "Motion", "Mouvement", "Moto"),
     "description": "Geschwindigkeit, Beschleunigung, gleichförmige und beschleunigte Bewegung, "
                    "freier Fall, Wurf, Bezugssystem."},
    {"unit_id": "physik-mechanik-u2", "topic_id": "physik-mechanik",
     "titles": _titles("Kräfte und Newtonsche Gesetze", "Forces and Newton's laws",
                       "Forces et lois de Newton", "Forze e leggi di Newton"),
     "description": "Kraft, Gewicht, Reibung, Federkraft, Kräftegleichgewicht, Newtonsche Gesetze, "
                    "Hebel und Rollen."},
    {"unit_id": "physik-mechanik-u3", "topic_id": "physik-mechanik",
     "titles": _titles("Dichte, Druck und Auftrieb", "Density, pressure and buoyancy",
                       "Masse volumique, pression et poussée", "Densità, pressione e spinta"),
     "description": "Masse und Dichte, Druck in Festkörpern, Flüssigkeiten und Gasen, Luftdruck, Auftrieb."},
    {"unit_id": "physik-mechanik-u4", "topic_id": "physik-mechanik",
     "titles": _titles("Arbeit, Energie und Impuls", "Work, energy and momentum",
                       "Travail, énergie et quantité de mouvement", "Lavoro, energia e quantità di moto"),
     "description": "Arbeit, Leistung, kinetische und potentielle Energie, Energieerhaltung, "
                    "Wirkungsgrad, Impuls und Stösse."},
    {"unit_id": "physik-mechanik-u5", "topic_id": "physik-mechanik",
     "titles": _titles("Kreisbewegung und Gravitation", "Circular motion and gravitation",
                       "Mouvement circulaire et gravitation", "Moto circolare e gravitazione"),
     "description": "Kreisbewegung, Zentripetalkraft, Gravitationsgesetz, Satelliten und Planeten."},
    {"unit_id": "physik-mechanik-u6", "topic_id": "physik-mechanik",
     "titles": _titles("Schwingungen und Wellen", "Oscillations and waves", "Oscillations et ondes",
                       "Oscillazioni e onde"),
     "description": "Harmonische Schwingung, Pendel, Resonanz, mechanische Wellen, Interferenz."},
    {"unit_id": "physik-elektrizitaet-u1", "topic_id": "physik-elektrizitaet",
     "titles": _titles("Stromkreise", "Electric circuits", "Circuits électriques", "Circuiti elettrici"),
     "description": "Ladung, Strom, Spannung, Widerstand, Ohmsches Gesetz, Serien- und "
                    "Parallelschaltung, elektrische Leistung, Sicherheit im Haushalt."},
    {"unit_id": "physik-elektrizitaet-u2", "topic_id": "physik-elektrizitaet",
     "titles": _titles("Elektrisches Feld", "Electric field", "Champ électrique", "Campo elettrico"),
     "description": "Coulombsches Gesetz, elektrisches Feld, Potential, Kondensator, geladene "
                    "Teilchen im Feld."},
    {"unit_id": "physik-elektrizitaet-u3", "topic_id": "physik-elektrizitaet",
     "titles": _titles("Magnetismus und Induktion", "Magnetism and induction",
                       "Magnétisme et induction", "Magnetismo e induzione"),
     "description": "Magnete, Magnetfeld des Stroms, Lorentzkraft, Elektromotor, Induktion, "
                    "Generator, Wechselstrom, Transformator, elektromagnetische Wellen."},
    {"unit_id": "physik-waerme-u1", "topic_id": "physik-waerme",
     "titles": _titles("Temperatur und Aggregatzustände", "Temperature and states of matter",
                       "Température et états de la matière", "Temperatura e stati della materia"),
     "description": "Temperatur, Schmelzen, Verdampfen, Kondensieren, Wärmeübertragung, "
                    "spezifische Wärmekapazität, Wärmekraftmaschinen."},
    {"unit_id": "physik-waerme-u2", "topic_id": "physik-waerme",
     "titles": _titles("Teilchenmodell und Gase", "Particle model and gases",
                       "Modèle particulaire et gaz", "Modello particellare e gas"),
     "description": "Teilchenmodell, Brownsche Bewegung, Gasgesetze, innere Energie, Hauptsätze "
                    "der Wärmelehre, Festkörper und Flüssigkeiten."},
    {"unit_id": "physik-optik-akustik-u1", "topic_id": "physik-optik-akustik",
     "titles": _titles("Schall", "Sound", "Son", "Suono"),
     "description": "Entstehung und Ausbreitung von Schall, Tonhöhe, Lautstärke, Klangfarbe, Lärmschutz."},
    {"unit_id": "physik-optik-akustik-u2", "topic_id": "physik-optik-akustik",
     "titles": _titles("Licht und Optik", "Light and optics", "Lumière et optique", "Luce e ottica"),
     "description": "Lichtausbreitung, Reflexion, Brechung, Linsen, Auge, Totalreflexion, "
                    "Interferenz und Beugung von Licht."},
    {"unit_id": "physik-modern-u1", "topic_id": "physik-modern",
     "titles": _titles("Atome, Kerne und Quanten", "Atoms, nuclei and quanta",
                       "Atomes, noyaux et quanta", "Atomi, nuclei e quanti"),
     "description": "Atommodelle, Photoeffekt, Welle-Teilchen-Dualismus, Radioaktivität, "
                    "Kernspaltung und Kernfusion, Energiequellen."},
    {"unit_id": "physik-praxis-u1", "topic_id": "physik-praxis",
     "titles": _titles("Messen und Experimentieren", "Measuring and experimenting",
                       "Mesurer et expérimenter", "Misurare e sperimentare"),
     "description": "Messen von Länge und Zeit, Messfehler, Versuche planen und auswerten, "
                    "fächerübergreifende Projekte."},
)

SUBJECTS: tuple[dict[str, Any], ...] = (
    {
        "subject_id": "english",
        "titles": _titles("Englisch", "English", "Anglais", "Inglese"),
        "description": "Englisch von der Primarstufe bis zur Sekundarstufe II: Wortschatz, "
                       "Grammatik, Alltagssprache, Lesen und Schreiben.",
        "accent": "teal",
        "order": 2,
    },
    {
        "subject_id": "physics",
        "titles": _titles("Physik", "Physics", "Physique", "Fisica"),
        "description": "Physik der Sekundarstufen I und II: Mechanik, Elektrizität, Wärme, "
                       "Schall und Licht, moderne Physik.",
        "accent": "navy",
        "order": 3,
    },
)

#: Grade levels of the imported lessons, the curriculum's grade vocabulary
#: (learning_profile_service): years 1-9 by name, upper secondary as one stage.
GRADE_LEVELS: dict[int, str] = {
    1: "grade_1_primary", 2: "grade_2_primary", 3: "grade_3_primary",
    4: "grade_4_primary", 5: "grade_5_primary", 6: "grade_6_primary",
    7: "grade_7_secondary", 8: "grade_8_secondary", 9: "grade_9_secondary",
}
UPPER_SECONDARY = "grade_secondary_ii"
#: The grade levels a subject's lessons are filed under, for its subject and topic rows.
SUBJECT_GRADE_LEVELS: dict[str, tuple[str, ...]] = {
    "english": (*(GRADE_LEVELS[g] for g in range(3, 10)), UPPER_SECONDARY),
    "physics": (GRADE_LEVELS[8], GRADE_LEVELS[9], UPPER_SECONDARY),
}


def grade_level(grade: int) -> str:
    return GRADE_LEVELS.get(grade, UPPER_SECONDARY)


def english_unit_id(topic_id: str, grade: int) -> str:
    stage = "u1" if grade <= 6 else "u2" if grade <= 9 else "u3"
    return f"{topic_id}-{stage}"


def _english_units() -> tuple[dict[str, Any], ...]:
    return tuple(
        {"unit_id": f"{topic_id}-{stage}", "topic_id": topic_id, "titles": titles, "description": ""}
        for topic_id, _ in ENGLISH_TOPICS
        for stage, titles in ENGLISH_STAGES
    )


def topics() -> list[dict[str, Any]]:
    """The nebulae of the new subjects."""
    return [
        *_subject_topics("english", ENGLISH_TOPICS),
        *_subject_topics("physics", PHYSICS_TOPICS),
    ]


def units() -> list[dict[str, Any]]:
    """Every star this module adds, with its subject and its order within its nebula."""
    rows: list[dict[str, Any]] = []
    next_order: dict[str, int] = {}
    for unit in (*MATH_UNITS, *_english_units(), *PHYSICS_UNITS):
        topic_id = unit["topic_id"]
        if topic_id not in next_order:
            existing = sum(1 for zap in ZAP_UNITS if zap.startswith(f"{topic_id}-"))
            next_order[topic_id] = existing + 1
        rows.append({**unit, "subject_id": subject_of_topic(topic_id), "order": next_order[topic_id]})
        next_order[topic_id] += 1
    return rows


def subject_of_topic(topic_id: str) -> str:
    if topic_id.startswith("englisch-"):
        return "english"
    if topic_id.startswith("physik-"):
        return "physics"
    return "mathematics"


def unit_choices(subject_id: str) -> dict[str, str]:
    """unit id → German title and scope, for filing a knowledge point of the subject."""
    if subject_id == "mathematics":
        added = {u["unit_id"]: f"{u['titles']['de']}: {u['description']}" for u in MATH_UNITS}
        return {**ZAP_UNITS, **added}
    if subject_id == "physics":
        return {u["unit_id"]: f"{u['titles']['de']}: {u['description']}" for u in PHYSICS_UNITS}
    return {}


def title_translations() -> dict[str, dict[str, str]]:
    """en/fr/it titles of every subject, nebula and star this module adds."""
    rows = [*SUBJECTS, *topics(), *units()]
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        content_id = row.get("unit_id") or row.get("topic_id") or row["subject_id"]
        out[content_id] = {locale: row["titles"][locale] for locale in LOCALES if locale != "de"}
    return out


@cache
def skills() -> dict[str, dict[str, Any]]:
    """The imported skill vocabulary: skill id → subject, unit and titles by locale."""
    if not SKILLS_FILE.exists():
        return {}
    data = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
    return dict(data.get("skills") or {})
