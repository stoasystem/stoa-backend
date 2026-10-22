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
    "zahlen": {"en": "Numbers and arithmetic", "fr": "Nombres et calcul", "it": "Numeri e calcolo"},
    "groessen": {
        "en": "Quantities and measures",
        "fr": "Grandeurs et mesures",
        "it": "Grandezze e misure",
    },
    "daten": {"en": "Data and counting", "fr": "Données et dénombrement", "it": "Dati e conteggio"},
    "zahlen-u1": {
        "en": "Calculating with whole numbers and decimals",
        "fr": "Calculer avec des nombres entiers et décimaux",
        "it": "Calcolare con numeri interi e decimali",
    },
    "zahlen-u2": {
        "en": "Place value and the number line",
        "fr": "Valeur de position et droite numérique",
        "it": "Valore posizionale e retta numerica",
    },
    "zahlen-u3": {
        "en": "Divisors and multiples",
        "fr": "Diviseurs et multiples",
        "it": "Divisori e multipli",
    },
    "zahlen-u4": {
        "en": "Patterns and sequences",
        "fr": "Motifs et suites",
        "it": "Schemi e successioni",
    },
    "groessen-u1": {
        "en": "Converting units",
        "fr": "Convertir des unités",
        "it": "Convertire unità di misura",
    },
    "groessen-u2": {"en": "Money and prices", "fr": "Argent et prix", "it": "Denaro e prezzi"},
    "groessen-u3": {
        "en": "Time, speed and distance",
        "fr": "Temps, vitesse et distance",
        "it": "Tempo, velocità e distanza",
    },
    "geometrie-u3": {
        "en": "Coordinates and transformations",
        "fr": "Coordonnées et transformations",
        "it": "Coordinate e trasformazioni",
    },
    "geometrie-u4": {
        "en": "Spatial reasoning",
        "fr": "Représentation spatiale",
        "it": "Visione spaziale",
    },
    "daten-u1": {
        "en": "Averages and charts",
        "fr": "Moyennes et diagrammes",
        "it": "Medie e diagrammi",
    },
    "daten-u2": {"en": "Combinatorics", "fr": "Combinatoire", "it": "Combinatoria"},
    "geometrie-l5": {
        "en": "Areas and circles in everyday life",
        "fr": "Aires et cercles au quotidien",
        "it": "Aree e cerchi nella vita quotidiana",
    },
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
        # Knowledge cards KP-BRU-GANZES, KP-BRU-ANTEILSBRUCH and
        # KP-BRU-RECHENREIHENFOLGE of the ZAP fractions batch (#106).
        "brueche-ganzes-bestimmen": "brueche-u2",
        "brueche-anteilsbruch-bestimmen": "brueche-u2",
        "brueche-rechenreihenfolge": "brueche-u2",
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
        # The ids keep their old prefix: exercises and attempts already carry them.
        # What moved is the star they hang under (the Textaufgaben topic retired).
        "textaufgaben-geld-rechnen": "groessen-u2",
        "textaufgaben-preis-pro-einheit": "groessen-u2",
        "textaufgaben-geschwindigkeit": "groessen-u3",
        "textaufgaben-fahrzeit": "groessen-u3",
        "textaufgaben-zeitspanne": "groessen-u3",
        "groessen-einheiten": "groessen-u1",
        "groessen-zeit-umrechnen": "groessen-u1",
        "zahlen-terme": "zahlen-u1",
        "zahlen-dezimal-terme": "zahlen-u1",
        "zahlen-stellenwert": "zahlen-u2",
        "zahlen-zahlenstrahl": "zahlen-u2",
        "zahlen-teiler": "zahlen-u3",
        "zahlen-muster-folgen": "zahlen-u4",
        "brueche-bruch-dezimal": "brueche-u1",
        "geometrie-abbildungen-koordinaten": "geometrie-u3",
        "geometrie-raumvorstellung": "geometrie-u4",
        "daten-durchschnitt": "daten-u1",
        "daten-diagramme": "daten-u1",
        "daten-kombinatorik": "daten-u2",
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
    "brueche-ganzes-bestimmen": "Vom Bruchteil aufs Ganze schliessen",
    "brueche-anteilsbruch-bestimmen": "Einen Anteil als Bruch angeben",
    "brueche-rechenreihenfolge": "Rechenreihenfolge in Bruchtermen",
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
    "groessen-einheiten": "Masseinheiten umrechnen",
    "groessen-zeit-umrechnen": "Zeiteinheiten in Rechnungen umrechnen",
    "zahlen-terme": "Terme mit natürlichen Zahlen berechnen",
    "zahlen-dezimal-terme": "Mit Dezimalzahlen rechnen",
    "zahlen-stellenwert": "Stellenwerte und Zahlenrätsel",
    "zahlen-zahlenstrahl": "Zahlen am Zahlenstrahl",
    "zahlen-teiler": "Teiler und Vielfache bestimmen",
    "zahlen-muster-folgen": "Folgen fortsetzen und berechnen",
    "brueche-bruch-dezimal": "Brüche und Dezimalzahlen umwandeln",
    "geometrie-abbildungen-koordinaten": "Spiegeln und Drehen im Koordinatensystem",
    "geometrie-raumvorstellung": "Körper und Figuren räumlich vorstellen",
    "daten-durchschnitt": "Mit dem Durchschnitt rechnen",
    "daten-diagramme": "Tabellen und Diagramme lesen",
    "daten-kombinatorik": "Systematisch abzählen",
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
    "brueche-ganzes-bestimmen": {
        "en": "Finding the whole from a fraction of it",
        "fr": "Retrouver le tout à partir d'une fraction",
        "it": "Risalire all'intero da una sua frazione",
    },
    "brueche-anteilsbruch-bestimmen": {
        "en": "Writing a share as a fraction",
        "fr": "Exprimer une part sous forme de fraction",
        "it": "Esprimere una parte come frazione",
    },
    "brueche-rechenreihenfolge": {
        "en": "Order of operations with fractions",
        "fr": "Priorité des opérations avec des fractions",
        "it": "Ordine delle operazioni con le frazioni",
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
    "groessen-einheiten": {
        "en": "Converting units",
        "fr": "Convertir des unités",
        "it": "Convertire unità",
    },
    "groessen-zeit-umrechnen": {
        "en": "Converting units of time in calculations",
        "fr": "Convertir des unités de temps dans un calcul",
        "it": "Convertire unità di tempo nei calcoli",
    },
    "zahlen-terme": {
        "en": "Evaluating expressions with whole numbers",
        "fr": "Calculer des expressions avec des nombres entiers",
        "it": "Calcolare espressioni con numeri interi",
    },
    "zahlen-dezimal-terme": {
        "en": "Calculating with decimals",
        "fr": "Calculer avec des nombres décimaux",
        "it": "Calcolare con i numeri decimali",
    },
    "zahlen-stellenwert": {
        "en": "Place value and number puzzles",
        "fr": "Valeur de position et énigmes de nombres",
        "it": "Valore posizionale e indovinelli numerici",
    },
    "zahlen-zahlenstrahl": {
        "en": "Numbers on the number line",
        "fr": "Nombres sur la droite numérique",
        "it": "Numeri sulla retta numerica",
    },
    "zahlen-teiler": {
        "en": "Finding divisors and multiples",
        "fr": "Trouver diviseurs et multiples",
        "it": "Trovare divisori e multipli",
    },
    "zahlen-muster-folgen": {
        "en": "Continuing and calculating sequences",
        "fr": "Prolonger et calculer des suites",
        "it": "Continuare e calcolare successioni",
    },
    "brueche-bruch-dezimal": {
        "en": "Converting fractions and decimals",
        "fr": "Convertir fractions et nombres décimaux",
        "it": "Convertire frazioni e decimali",
    },
    "geometrie-abbildungen-koordinaten": {
        "en": "Reflecting and rotating in coordinates",
        "fr": "Symétrie et rotation dans un repère",
        "it": "Simmetria e rotazione nel piano cartesiano",
    },
    "geometrie-raumvorstellung": {
        "en": "Visualising solids and figures",
        "fr": "Se représenter solides et figures",
        "it": "Immaginare solidi e figure",
    },
    "daten-durchschnitt": {
        "en": "Working with the average",
        "fr": "Calculer avec la moyenne",
        "it": "Calcolare con la media",
    },
    "daten-diagramme": {
        "en": "Reading tables and charts",
        "fr": "Lire tableaux et diagrammes",
        "it": "Leggere tabelle e diagrammi",
    },
    "daten-kombinatorik": {
        "en": "Counting systematically",
        "fr": "Dénombrer systématiquement",
        "it": "Contare in modo sistematico",
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
