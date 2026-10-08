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


# ── Skill points (stoa-backend#58) ────────────────────────────────────────
#
# A skill point is an exercise's skill, and stoa-frontend#9 point 12 gives it
# exactly one owner: every id below hangs under one unit. That single ownership
# is what keeps a skill from being drawn under two stars, so SKILL_UNITS is the
# one source of it - the seed, the draft validation and the mastery service all
# read it rather than keep a copy.
#
# Names follow the same mechanism as the titles above: German is the stored
# language and `translated_title` serves the other three.

SKILL_UNITS: dict[str, dict[str, str]] = {
    "mathematics": {
        "brueche-kuerzen": "brueche-u1",
        "brueche-vergleichen": "brueche-u1",
        "brueche-erweitern": "brueche-u1",
        "brueche-addieren": "brueche-u2",
        "brueche-subtrahieren": "brueche-u2",
        "brueche-multiplizieren": "brueche-u2",
        "brueche-anteil-einer-menge": "brueche-u2",
        "gleichungen-einstufig": "gleichungen-u1",
        "gleichungen-probe": "gleichungen-u1",
        "gleichungen-zweistufig": "gleichungen-u1",
        "gleichungen-aufstellen": "gleichungen-u2",
        "gleichungen-klammer": "gleichungen-u2",
        "gleichungen-textaufgabe": "gleichungen-u2",
        "geometrie-umfang-rechteck": "geometrie-u1",
        "geometrie-flaeche-rechteck": "geometrie-u1",
        "geometrie-flaeche-dreieck": "geometrie-u1",
        "geometrie-kreis-umfang": "geometrie-u1",
        "geometrie-kreis-flaeche": "geometrie-u1",
        "geometrie-kreis-radius": "geometrie-u1",
        "geometrie-volumen-quader": "geometrie-u2",
        "geometrie-volumen-wuerfel": "geometrie-u2",
        "geometrie-volumen-einheiten": "geometrie-u2",
        "geometrie-pythagoras-hypotenuse": "geometrie-u2",
        "geometrie-pythagoras-kathete": "geometrie-u2",
        "prozentrechnung-prozentwert": "prozentrechnung-u1",
        "prozentrechnung-prozentsatz": "prozentrechnung-u1",
        "prozentrechnung-grundwert": "prozentrechnung-u1",
        "prozentrechnung-rabatt": "prozentrechnung-u1",
        "prozentrechnung-mehrwertsteuer": "prozentrechnung-u1",
        "prozentrechnung-verhaeltnis-teilen": "prozentrechnung-u2",
        "prozentrechnung-direkte-proportionalitaet": "prozentrechnung-u2",
        "prozentrechnung-indirekte-proportionalitaet": "prozentrechnung-u2",
        "prozentrechnung-anwendung": "prozentrechnung-u2",
        "textaufgaben-geld-rechnen": "textaufgaben-u1",
        "textaufgaben-preis-pro-einheit": "textaufgaben-u1",
        "textaufgaben-geschwindigkeit": "textaufgaben-u1",
        "textaufgaben-fahrzeit": "textaufgaben-u1",
        "textaufgaben-zeitspanne": "textaufgaben-u1",
        "textaufgaben-zap-flaeche": "textaufgaben-u2",
        "textaufgaben-zap-verhaeltnis": "textaufgaben-u2",
        "textaufgaben-zap-mehrschritt": "textaufgaben-u2",
        "textaufgaben-zap-kreis": "textaufgaben-u2",
    },
}

SKILL_TITLES: dict[str, str] = {
    "brueche-kuerzen": "Brüche kürzen",
    "brueche-vergleichen": "Brüche vergleichen und einordnen",
    "brueche-erweitern": "Brüche erweitern",
    "brueche-addieren": "Brüche addieren",
    "brueche-subtrahieren": "Brüche subtrahieren",
    "brueche-multiplizieren": "Brüche multiplizieren",
    "brueche-anteil-einer-menge": "Bruchteil einer Menge berechnen",
    "gleichungen-einstufig": "Einstufige Gleichungen lösen",
    "gleichungen-probe": "Lösung durch Einsetzen prüfen",
    "gleichungen-zweistufig": "Zweistufige Gleichungen lösen",
    "gleichungen-aufstellen": "Gleichung aus einem Text aufstellen",
    "gleichungen-klammer": "Gleichungen mit Klammer lösen",
    "gleichungen-textaufgabe": "Textaufgaben mit Gleichungen lösen",
    "geometrie-umfang-rechteck": "Umfang des Rechtecks",
    "geometrie-flaeche-rechteck": "Fläche des Rechtecks",
    "geometrie-flaeche-dreieck": "Fläche des Dreiecks",
    "geometrie-kreis-umfang": "Umfang des Kreises",
    "geometrie-kreis-flaeche": "Fläche des Kreises",
    "geometrie-kreis-radius": "Radius und Durchmesser",
    "geometrie-volumen-quader": "Volumen des Quaders",
    "geometrie-volumen-wuerfel": "Volumen des Würfels",
    "geometrie-volumen-einheiten": "Volumeneinheiten und Liter",
    "geometrie-pythagoras-hypotenuse": "Hypotenuse mit Pythagoras",
    "geometrie-pythagoras-kathete": "Kathete mit Pythagoras",
    "prozentrechnung-prozentwert": "Prozentwert berechnen",
    "prozentrechnung-prozentsatz": "Prozentsatz berechnen",
    "prozentrechnung-grundwert": "Grundwert berechnen",
    "prozentrechnung-rabatt": "Rabatt und Preisänderung",
    "prozentrechnung-mehrwertsteuer": "Mehrwertsteuer berechnen",
    "prozentrechnung-verhaeltnis-teilen": "Menge im Verhältnis aufteilen",
    "prozentrechnung-direkte-proportionalitaet": "Direkte Proportionalität",
    "prozentrechnung-indirekte-proportionalitaet": "Indirekte Proportionalität",
    "prozentrechnung-anwendung": "Prozente in Prüfungsaufgaben",
    "textaufgaben-geld-rechnen": "Mit Geld rechnen",
    "textaufgaben-preis-pro-einheit": "Preis pro Einheit",
    "textaufgaben-geschwindigkeit": "Geschwindigkeit berechnen",
    "textaufgaben-fahrzeit": "Fahrzeit berechnen",
    "textaufgaben-zeitspanne": "Zeitspannen berechnen",
    "textaufgaben-zap-flaeche": "ZAP: Flächen anwenden",
    "textaufgaben-zap-verhaeltnis": "ZAP: Verhältnisse anwenden",
    "textaufgaben-zap-mehrschritt": "ZAP: mehrschrittig rechnen",
    "textaufgaben-zap-kreis": "ZAP: Kreis anwenden",
}

SKILL_TRANSLATIONS: dict[str, dict[str, str]] = {
    "brueche-kuerzen": {
        "en": "Reducing fractions",
        "fr": "Simplifier les fractions",
        "it": "Semplificare le frazioni",
    },
    "brueche-vergleichen": {
        "en": "Comparing and placing fractions",
        "fr": "Comparer et situer les fractions",
        "it": "Confrontare e collocare le frazioni",
    },
    "brueche-erweitern": {
        "en": "Expanding fractions",
        "fr": "Amplifier les fractions",
        "it": "Espandere le frazioni",
    },
    "brueche-addieren": {
        "en": "Adding fractions",
        "fr": "Additionner des fractions",
        "it": "Addizionare frazioni",
    },
    "brueche-subtrahieren": {
        "en": "Subtracting fractions",
        "fr": "Soustraire des fractions",
        "it": "Sottrarre frazioni",
    },
    "brueche-multiplizieren": {
        "en": "Multiplying fractions",
        "fr": "Multiplier des fractions",
        "it": "Moltiplicare frazioni",
    },
    "brueche-anteil-einer-menge": {
        "en": "A fraction of a quantity",
        "fr": "Une fraction d'une quantité",
        "it": "Una frazione di una quantità",
    },
    "gleichungen-einstufig": {
        "en": "Solving one-step equations",
        "fr": "Résoudre des équations à une étape",
        "it": "Risolvere equazioni a un passaggio",
    },
    "gleichungen-probe": {
        "en": "Checking a solution by substitution",
        "fr": "Vérifier une solution par substitution",
        "it": "Verificare una soluzione per sostituzione",
    },
    "gleichungen-zweistufig": {
        "en": "Solving two-step equations",
        "fr": "Résoudre des équations à deux étapes",
        "it": "Risolvere equazioni a due passaggi",
    },
    "gleichungen-aufstellen": {
        "en": "Setting up an equation from a text",
        "fr": "Mettre un énoncé en équation",
        "it": "Impostare un'equazione da un testo",
    },
    "gleichungen-klammer": {
        "en": "Equations with brackets",
        "fr": "Équations avec parenthèses",
        "it": "Equazioni con parentesi",
    },
    "gleichungen-textaufgabe": {
        "en": "Word problems solved with equations",
        "fr": "Problèmes résolus par équation",
        "it": "Problemi risolti con equazioni",
    },
    "geometrie-umfang-rechteck": {
        "en": "Perimeter of a rectangle",
        "fr": "Périmètre du rectangle",
        "it": "Perimetro del rettangolo",
    },
    "geometrie-flaeche-rechteck": {
        "en": "Area of a rectangle",
        "fr": "Aire du rectangle",
        "it": "Area del rettangolo",
    },
    "geometrie-flaeche-dreieck": {
        "en": "Area of a triangle",
        "fr": "Aire du triangle",
        "it": "Area del triangolo",
    },
    "geometrie-kreis-umfang": {
        "en": "Circumference of a circle",
        "fr": "Circonférence du cercle",
        "it": "Circonferenza del cerchio",
    },
    "geometrie-kreis-flaeche": {
        "en": "Area of a circle",
        "fr": "Aire du cercle",
        "it": "Area del cerchio",
    },
    "geometrie-kreis-radius": {
        "en": "Radius and diameter",
        "fr": "Rayon et diamètre",
        "it": "Raggio e diametro",
    },
    "geometrie-volumen-quader": {
        "en": "Volume of a cuboid",
        "fr": "Volume du pavé droit",
        "it": "Volume del parallelepipedo",
    },
    "geometrie-volumen-wuerfel": {
        "en": "Volume of a cube",
        "fr": "Volume du cube",
        "it": "Volume del cubo",
    },
    "geometrie-volumen-einheiten": {
        "en": "Volume units and litres",
        "fr": "Unités de volume et litres",
        "it": "Unità di volume e litri",
    },
    "geometrie-pythagoras-hypotenuse": {
        "en": "Hypotenuse with Pythagoras",
        "fr": "Hypoténuse avec Pythagore",
        "it": "Ipotenusa con Pitagora",
    },
    "geometrie-pythagoras-kathete": {
        "en": "A leg with Pythagoras",
        "fr": "Un côté de l'angle droit avec Pythagore",
        "it": "Un cateto con Pitagora",
    },
    "prozentrechnung-prozentwert": {
        "en": "Finding the percentage amount",
        "fr": "Calculer la valeur du pourcentage",
        "it": "Calcolare il valore percentuale",
    },
    "prozentrechnung-prozentsatz": {
        "en": "Finding the percentage rate",
        "fr": "Calculer le taux de pourcentage",
        "it": "Calcolare il tasso percentuale",
    },
    "prozentrechnung-grundwert": {
        "en": "Finding the base value",
        "fr": "Calculer la valeur de base",
        "it": "Calcolare il valore di base",
    },
    "prozentrechnung-rabatt": {
        "en": "Discount and price change",
        "fr": "Remise et variation de prix",
        "it": "Sconto e variazione di prezzo",
    },
    "prozentrechnung-mehrwertsteuer": {
        "en": "Calculating VAT",
        "fr": "Calculer la TVA",
        "it": "Calcolare l'IVA",
    },
    "prozentrechnung-verhaeltnis-teilen": {
        "en": "Sharing a quantity in a ratio",
        "fr": "Partager une quantité selon un rapport",
        "it": "Dividere una quantità in un rapporto",
    },
    "prozentrechnung-direkte-proportionalitaet": {
        "en": "Direct proportionality",
        "fr": "Proportionnalité directe",
        "it": "Proporzionalità diretta",
    },
    "prozentrechnung-indirekte-proportionalitaet": {
        "en": "Inverse proportionality",
        "fr": "Proportionnalité inverse",
        "it": "Proporzionalità inversa",
    },
    "prozentrechnung-anwendung": {
        "en": "Percentages in exam tasks",
        "fr": "Pourcentages dans les exercices d'examen",
        "it": "Percentuali negli esercizi d'esame",
    },
    "textaufgaben-geld-rechnen": {
        "en": "Working with money",
        "fr": "Calculer avec de l'argent",
        "it": "Calcolare con il denaro",
    },
    "textaufgaben-preis-pro-einheit": {
        "en": "Unit price",
        "fr": "Prix unitaire",
        "it": "Prezzo unitario",
    },
    "textaufgaben-geschwindigkeit": {
        "en": "Calculating speed",
        "fr": "Calculer la vitesse",
        "it": "Calcolare la velocità",
    },
    "textaufgaben-fahrzeit": {
        "en": "Calculating travel time",
        "fr": "Calculer la durée du trajet",
        "it": "Calcolare il tempo di percorrenza",
    },
    "textaufgaben-zeitspanne": {
        "en": "Calculating time spans",
        "fr": "Calculer des durées",
        "it": "Calcolare intervalli di tempo",
    },
    "textaufgaben-zap-flaeche": {
        "en": "ZAP: applying areas",
        "fr": "ZAP : appliquer les aires",
        "it": "ZAP: applicare le aree",
    },
    "textaufgaben-zap-verhaeltnis": {
        "en": "ZAP: applying ratios",
        "fr": "ZAP : appliquer les rapports",
        "it": "ZAP: applicare i rapporti",
    },
    "textaufgaben-zap-mehrschritt": {
        "en": "ZAP: multi-step calculations",
        "fr": "ZAP : calculs en plusieurs étapes",
        "it": "ZAP: calcoli a più passaggi",
    },
    "textaufgaben-zap-kreis": {
        "en": "ZAP: applying the circle",
        "fr": "ZAP : appliquer le cercle",
        "it": "ZAP: applicare il cerchio",
    },
}

TITLE_TRANSLATIONS.update(SKILL_TRANSLATIONS)


def skill_unit_id(skill_id: str) -> str | None:
    """The one unit a skill hangs under, or None when it is not in the vocabulary."""
    for skills in SKILL_UNITS.values():
        owner = skills.get(skill_id)
        if owner:
            return owner
    return None


def skill_title(skill_id: str, locale: str) -> str:
    """The skill's display name, falling back to German and then to its id."""
    return translated_title(skill_id, SKILL_TITLES.get(skill_id, skill_id), locale)
