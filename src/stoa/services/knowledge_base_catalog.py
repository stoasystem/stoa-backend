"""Where the imported knowledge base hangs in the star map.

The knowledge base brings knowledge points for mathematics from the first year of
primary school to upper secondary, for English and for physics, and their
exercises. In the star map a nebula (a topic) is a field of knowledge, a star (a
unit) is one knowledge point, and the small stars around it (skills) are the
question types its exercises practise. There are no lessons for the student: a
small star's exercises are its practice, held in hidden practice sets that carry
the small star's id.

Mathematics keeps its seven nebulae; the ZAP stars stay as they are and the
knowledge base gets stars of its own beside them. English and physics are subjects
of their own. A language subject is laid out by the situations of life it is used
in and by its grammar, the same nebulae for every language.

This module holds:

- the nebulae and subjects, and the coarse stars the translation files each
  upstream knowledge point under (`grouping_units`), which the structuring step
  splits into the final stars;
- the question types of each subject;
- the final stars, read from `knowledge_base_stars.json`, and the skill and
  practice-set titles, read from `knowledge_base_skills.json`. The import script
  (scripts/knowledge_base_import.py) writes both files.
"""

from __future__ import annotations

from functools import cache
import json
from pathlib import Path
from typing import Any

SKILLS_FILE = Path(__file__).with_name("knowledge_base_skills.json")
STARS_FILE = Path(__file__).with_name("knowledge_base_stars.json")
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


#: Language subjects are laid out the same way whatever the language: nebulae for
#: the situations of life a learner talks about, and nebulae for the grammar that
#: carries it. Each nebula is (slug, titles, stars) and each star
#: (slug, titles, scope); the scope tells the import which knowledge points go
#: there. Vocabulary, everyday expressions and reading or writing tasks go to the
#: situation they are about; grammar, sounds and word formation go to grammar.
_Star = tuple[str, dict[str, str], str]
LANGUAGE_SCENARIOS: tuple[tuple[str, dict[str, str], tuple[_Star, ...]], ...] = (
    ("ich", _titles("Ich und die anderen", "Me and other people", "Moi et les autres", "Io e gli altri"), (
        ("vorstellen", _titles("Begrüssen und sich vorstellen", "Greeting and introducing yourself",
                               "Saluer et se présenter", "Salutare e presentarsi"),
         "Begrüssung, Abschied, Name, Alter, Herkunft, persönliche Angaben."),
        ("familie", _titles("Familie und Freunde", "Family and friends", "Famille et amis",
                            "Famiglia e amici"),
         "Familienmitglieder, Freundschaft, Beziehungen."),
        ("beschreiben", _titles("Aussehen, Charakter und Gefühle", "Looks, character and feelings",
                                "Apparence, caractère et sentiments", "Aspetto, carattere e sentimenti"),
         "Menschen beschreiben, Eigenschaften, Gefühle und Stimmungen."),
    )),
    ("alltag", _titles("Alltag und Zuhause", "Daily life and home", "Quotidien et maison",
                       "Vita quotidiana e casa"), (
        ("wohnen", _titles("Wohnen und Zuhause", "Home and living", "Le logement", "La casa"),
         "Zimmer, Möbel, Haushalt, Gegenstände zu Hause."),
        ("tagesablauf", _titles("Tagesablauf, Zahlen und Uhrzeit", "Daily routine, numbers and time",
                                "Journée, nombres et heure", "Giornata, numeri e ora"),
         "Zahlen, Uhrzeit, Datum, Wochentage, Monate, Tagesablauf, Gewohnheiten."),
        ("kleidung", _titles("Kleidung und Farben", "Clothes and colours", "Vêtements et couleurs",
                             "Vestiti e colori"),
         "Kleidungsstücke, Farben, was man trägt."),
    )),
    ("schule", _titles("Schule und Arbeit", "School and work", "École et travail", "Scuola e lavoro"), (
        ("klassenzimmer", _titles("Schulsachen und Klassenzimmer", "School things and the classroom",
                                  "Affaires scolaires et salle de classe", "Materiale scolastico e aula"),
         "Schulsachen, Klassenzimmer, Anweisungen im Unterricht."),
        ("lernen", _titles("Fächer und Lernen", "Subjects and learning", "Matières et apprentissage",
                           "Materie e apprendimento"),
         "Schulfächer, Stundenplan, Schulleben, Lernen und Prüfungen."),
        ("berufe", _titles("Berufe und Zukunft", "Jobs and the future", "Métiers et avenir",
                           "Professioni e futuro"),
         "Berufe, Arbeitswelt, Pläne und Träume für die Zukunft."),
    )),
    ("essen", _titles("Essen und Einkaufen", "Food and shopping", "Repas et achats", "Cibo e acquisti"), (
        ("essen-trinken", _titles("Essen und Trinken", "Food and drink", "Manger et boire",
                                  "Mangiare e bere"),
         "Lebensmittel, Mahlzeiten, Vorlieben, im Restaurant bestellen, gesund essen."),
        ("einkaufen", _titles("Einkaufen und Geld", "Shopping and money", "Achats et argent",
                              "Acquisti e soldi"),
         "Geschäfte, Preise, bezahlen, nach Waren fragen."),
    )),
    ("freizeit", _titles("Freizeit und Feste", "Free time and celebrations", "Loisirs et fêtes",
                         "Tempo libero e feste"), (
        ("hobbys", _titles("Hobbys und Sport", "Hobbies and sport", "Loisirs et sport", "Hobby e sport"),
         "Hobbys, Sport, Spiele, Vereine, Fähigkeiten."),
        ("feste", _titles("Feste und Einladungen", "Celebrations and invitations",
                          "Fêtes et invitations", "Feste e inviti"),
         "Geburtstag, Feiertage, Bräuche, einladen, Geschenke."),
        ("medien", _titles("Musik, Filme und Medien", "Music, films and media",
                           "Musique, films et médias", "Musica, film e media"),
         "Musik, Filme, Bücher, Internet, soziale Medien."),
    )),
    ("unterwegs", _titles("Unterwegs", "Out and about", "En route", "In giro"), (
        ("orte", _titles("Orte und Wege", "Places and directions", "Lieux et chemins",
                         "Luoghi e indicazioni"),
         "Orte in der Stadt, nach dem Weg fragen, Wegbeschreibung, Lage."),
        ("reisen", _titles("Verkehr und Reisen", "Transport and travel", "Transports et voyages",
                           "Trasporti e viaggi"),
         "Verkehrsmittel, Ferien, Reisen, Unterkunft."),
        ("laender", _titles("Länder und Kulturen", "Countries and cultures", "Pays et cultures",
                            "Paesi e culture"),
         "Länder, Sprachen, Nationalitäten, kulturelle Unterschiede."),
    )),
    ("natur", _titles("Natur und Umwelt", "Nature and the environment", "Nature et environnement",
                      "Natura e ambiente"), (
        ("wetter", _titles("Wetter und Jahreszeiten", "Weather and seasons", "Météo et saisons",
                           "Tempo e stagioni"),
         "Wetter, Jahreszeiten, Klima beschreiben."),
        ("tiere", _titles("Tiere und Pflanzen", "Animals and plants", "Animaux et plantes",
                          "Animali e piante"),
         "Haustiere, Wildtiere, Pflanzen, Bauernhof, Zoo."),
        ("umwelt", _titles("Umwelt und Klimaschutz", "Environment and climate", "Environnement et climat",
                           "Ambiente e clima"),
         "Umweltschutz, Klimawandel, Naturkatastrophen, nachhaltig leben."),
    )),
    ("gesundheit", _titles("Körper und Gesundheit", "Body and health", "Corps et santé",
                           "Corpo e salute"), (
        ("koerper", _titles("Körper und Krankheit", "The body and illness", "Le corps et la maladie",
                            "Il corpo e la malattia"),
         "Körperteile, Schmerzen und Krankheiten, beim Arzt."),
        ("gesund-leben", _titles("Gesund und sicher leben", "Living healthily and safely",
                                 "Vivre sain et en sécurité", "Vivere sani e sicuri"),
         "Gesunde Gewohnheiten, Bewegung, Schlaf, Sicherheit, Hilfe im Notfall."),
    )),
    ("gesellschaft", _titles("Gesellschaft und Wissen", "Society and knowledge", "Société et savoir",
                             "Società e sapere"), (
        ("technik", _titles("Wissenschaft und Technik", "Science and technology", "Sciences et technique",
                            "Scienza e tecnologia"),
         "Erfindungen, Technik, Raumfahrt, Wissenschaft, künstliche Intelligenz."),
        ("kultur", _titles("Geschichte, Kunst und Literatur", "History, art and literature",
                           "Histoire, art et littérature", "Storia, arte e letteratura"),
         "Geschichte, berühmte Personen, Kunst, Literatur, Theater."),
        ("zusammenleben", _titles("Zusammenleben und Werte", "Living together and values",
                                  "Vivre ensemble et valeurs", "Convivenza e valori"),
         "Freiwilligenarbeit, Regeln, Rechte, Vorbilder, gesellschaftliche Fragen."),
    )),
    ("kommunizieren", _titles("Sich verständigen", "Communicating", "Communiquer", "Comunicare"), (
        ("hoeflich", _titles("Bitten, danken, sich entschuldigen", "Asking, thanking, apologising",
                             "Demander, remercier, s'excuser", "Chiedere, ringraziare, scusarsi"),
         "Bitten und Angebote, Dank, Entschuldigung, Erlaubnis, Hilfe anbieten, am Telefon."),
        ("meinung", _titles("Meinungen und Vorschläge", "Opinions and suggestions",
                            "Opinions et propositions", "Opinioni e proposte"),
         "Meinung äussern, zustimmen und widersprechen, Vorschläge, Ratschläge, diskutieren."),
        ("texte-lesen", _titles("Texte verstehen", "Understanding texts", "Comprendre des textes",
                                "Capire i testi"),
         "Lesestrategien, Hauptaussage, Details, Textsorten erkennen, wenn kein Lebensbereich passt."),
        ("texte-schreiben", _titles("Briefe, E-Mails und Aufsätze", "Letters, emails and essays",
                                    "Lettres, e-mails et rédactions", "Lettere, e-mail e temi"),
         "Nachrichten, Briefe, E-Mails, Berichte und Aufsätze schreiben und aufbauen."),
    )),
)
LANGUAGE_GRAMMAR: tuple[tuple[str, dict[str, str], tuple[_Star, ...]], ...] = (
    ("laute", _titles("Buchstaben und Aussprache", "Letters and pronunciation",
                      "Lettres et prononciation", "Lettere e pronuncia"), (
        ("alphabet", _titles("Alphabet und Schreibung", "Alphabet and spelling", "Alphabet et orthographe",
                             "Alfabeto e ortografia"),
         "Buchstaben, Alphabet, Gross- und Kleinschreibung, Rechtschreibung."),
        ("aussprache", _titles("Laute, Betonung und Satzmelodie", "Sounds, stress and intonation",
                               "Sons, accent et intonation", "Suoni, accento e intonazione"),
         "Laute, Lautschrift, Wortbetonung, Satzbetonung, Intonation."),
    )),
    ("woerter", _titles("Wortarten", "Parts of speech", "Classes de mots", "Parti del discorso"), (
        ("nomen", _titles("Nomen, Artikel und Mengen", "Nouns, articles and quantities",
                          "Noms, articles et quantités", "Nomi, articoli e quantità"),
         "Nomen, Plural, zählbar und unzählbar, Artikel, Mengenwörter, Genitiv."),
        ("pronomen", _titles("Pronomen", "Pronouns", "Pronoms", "Pronomi"),
         "Personal-, Possessiv-, Reflexiv-, Demonstrativ- und Indefinitpronomen."),
        ("adjektive", _titles("Adjektive, Adverbien und Vergleiche", "Adjectives, adverbs and comparison",
                              "Adjectifs, adverbes et comparaison", "Aggettivi, avverbi e comparazione"),
         "Adjektive, Adverbien, Steigerung, Vergleiche."),
        ("praepositionen", _titles("Präpositionen und Konjunktionen", "Prepositions and conjunctions",
                                   "Prépositions et conjonctions", "Preposizioni e congiunzioni"),
         "Präpositionen von Ort und Zeit, Konjunktionen, Verbindungswörter."),
        ("wortbildung", _titles("Wortbildung und Wendungen", "Word formation and phrases",
                                "Formation des mots et expressions",
                                "Formazione delle parole ed espressioni"),
         "Vorsilben, Nachsilben, zusammengesetzte Wörter, Wortfamilien, Phrasal Verbs, feste Wendungen."),
    )),
    ("verben", _titles("Verben und Zeitformen", "Verbs and tenses", "Verbes et temps", "Verbi e tempi"), (
        ("hilfsverben", _titles("Hilfsverben und Modalverben", "Auxiliary and modal verbs",
                                "Auxiliaires et verbes modaux", "Ausiliari e verbi modali"),
         "sein, haben, tun, Modalverben (können, müssen, dürfen, sollen ...)."),
        ("gegenwart", _titles("Gegenwart", "Present tenses", "Le présent", "Il presente"),
         "Einfache und Verlaufsform der Gegenwart."),
        ("vergangenheit", _titles("Vergangenheit", "Past tenses", "Le passé", "Il passato"),
         "Einfache und Verlaufsform der Vergangenheit, unregelmässige Verben, used to."),
        ("perfekt", _titles("Perfekt und Plusquamperfekt", "Perfect tenses", "Les temps composés",
                            "I tempi composti"),
         "Present Perfect, Past Perfect, Perfekt-Verlaufsformen."),
        ("zukunft", _titles("Zukunft", "Future forms", "Le futur", "Il futuro"),
         "will, going to, Gegenwart für Zukünftiges, Futur in der Vergangenheit."),
        ("passiv", _titles("Passiv", "The passive", "Le passif", "Il passivo"),
         "Passiv in allen Zeitformen."),
        ("infinite", _titles("Infinitiv, Gerundium und Partizip", "Infinitive, gerund and participle",
                             "Infinitif, gérondif et participe", "Infinito, gerundio e participio"),
         "Infinitiv, Gerundium, Partizipien, Verben mit Infinitiv oder Gerundium."),
    )),
    ("saetze", _titles("Sätze bauen", "Building sentences", "Construire des phrases",
                       "Costruire le frasi"), (
        ("fragen", _titles("Fragen, Verneinung und Aufforderungen", "Questions, negation and commands",
                           "Questions, négation et impératif", "Domande, negazione e imperativo"),
         "Fragesätze, Fragewörter, Frageanhängsel, Verneinung, Imperativ, Ausrufe."),
        ("satzmuster", _titles("Satzglieder und Satzmuster", "Sentence parts and patterns",
                               "Éléments et types de phrases", "Elementi e schemi della frase"),
         "Wortstellung, Satzglieder, there is / there are, einfache Satzmuster."),
        ("nebensaetze", _titles("Nebensätze", "Subordinate clauses", "Subordonnées", "Subordinate"),
         "Relativsätze, Adverbialsätze, Objekt- und Subjektsätze."),
        ("bedingungen", _titles("Bedingungssätze und Konjunktiv", "Conditionals and the subjunctive",
                                "Conditionnel et subjonctif", "Periodo ipotetico e congiuntivo"),
         "if-Sätze, Wünsche, irreale Aussagen, Konjunktiv."),
        ("indirekte-rede", _titles("Indirekte Rede", "Reported speech", "Discours indirect",
                                   "Discorso indiretto"),
         "Aussagen, Fragen und Bitten wiedergeben, Zeitverschiebung."),
        ("stil", _titles("Betonung, Inversion und Ellipse", "Emphasis, inversion and ellipsis",
                         "Mise en relief, inversion et ellipse", "Enfasi, inversione ed ellissi"),
         "Hervorhebung, Inversion, Auslassung, Satzverknüpfung im Text."),
    )),
)
#: The language subjects and the prefix of their nebula ids. German, French or
#: Italian learning gets the same nebulae by an entry here once it has content.
LANGUAGE_SUBJECTS: dict[str, str] = {"english": "englisch"}


def _language_topics() -> list[dict[str, Any]]:
    nebulae = (*LANGUAGE_SCENARIOS, *LANGUAGE_GRAMMAR)
    return [
        {"topic_id": f"{prefix}-{slug}", "subject_id": subject_id, "titles": titles, "order": order}
        for subject_id, prefix in LANGUAGE_SUBJECTS.items()
        for order, (slug, titles, _stars) in enumerate(nebulae, start=1)
    ]


def _language_units() -> tuple[dict[str, Any], ...]:
    return tuple(
        {"unit_id": f"{prefix}-{slug}-{star}", "topic_id": f"{prefix}-{slug}",
         "titles": titles, "description": scope}
        for prefix in LANGUAGE_SUBJECTS.values()
        for slug, _nebula_titles, stars in (*LANGUAGE_SCENARIOS, *LANGUAGE_GRAMMAR)
        for star, titles, scope in stars
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
        "description": "Englisch von der Primarstufe bis zur Sekundarstufe II, geordnet nach "
                       "Lebensbereichen und Grammatik.",
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


#: The small stars: what kind of task an exercise is, per subject, in map order.
#: Each is (slug, titles, scope); the scope tells the structuring step which
#: exercises it holds. A knowledge point shows only the types it has exercises of.
QUESTION_TYPES: dict[str, tuple[tuple[str, dict[str, str], str], ...]] = {
    "mathematics": (
        ("kopfrechnen", _titles("Kopfrechnen-Trick", "Mental maths tricks", "Astuces de calcul mental",
                                "Trucchi di calcolo mentale"),
         "Im Kopf rechnen, Rechentricks, Ergebnisse, die man auswendig weiss (Einmaleins)."),
        ("rechnen", _titles("Rechnen und Umformen", "Calculating and transforming", "Calculer et transformer",
                            "Calcolare e trasformare"),
         "Mehrschrittige oder schriftliche Rechnungen, Terme umformen, Gleichungen lösen, Werte bestimmen."),
        ("begriffe", _titles("Begriffe verstehen", "Understanding concepts", "Comprendre les notions",
                             "Capire i concetti"),
         "Definitionen, Eigenschaften, richtig oder falsch, Begriffe und Fälle unterscheiden."),
        ("darstellen", _titles("Darstellen und Zerlegen", "Representing and decomposing",
                               "Représenter et décomposer", "Rappresentare e scomporre"),
         "Zahlen zerlegen und zusammensetzen, Stellenwerte, Brüche, Figuren und Körper darstellen, "
         "Ansichten und Netze, Diagramme ablesen."),
        ("vergleichen", _titles("Vergleichen und Ordnen", "Comparing and ordering", "Comparer et ordonner",
                                "Confrontare e ordinare"),
         "Grösser, kleiner, gleich; der Reihe nach ordnen; Reihenfolge und Position."),
        ("sachaufgaben", _titles("Sachaufgaben", "Word problems", "Problèmes", "Problemi"),
         "Aufgaben aus dem Alltag oder einer Sachsituation, die man in Mathematik übersetzt."),
        ("schliessen", _titles("Formeln und Schlussfolgern", "Formulas and reasoning",
                               "Formules et raisonnement", "Formule e ragionamento"),
         "Formeln anwenden oder herleiten, Zusammenhänge erkennen, Muster fortsetzen, begründen, beweisen."),
    ),
    "english": (
        ("wortschatz", _titles("Wortschatz", "Vocabulary", "Vocabulaire", "Lessico"),
         "Bedeutung von Wörtern und Wendungen, das passende Wort wählen."),
        ("grammatik", _titles("Grammatik anwenden", "Using grammar", "Appliquer la grammaire",
                              "Applicare la grammatica"),
         "Lücke mit der richtigen Form füllen, Zeitform, Wortform, Satzbau."),
        ("saetze", _titles("Den richtigen Satz wählen", "Choosing the right sentence",
                           "Choisir la bonne phrase", "Scegliere la frase giusta"),
         "Welcher Satz ist richtig oder passt zu einer Aussage, ohne Gesprächssituation."),
        ("situationen", _titles("Situationen meistern", "Handling situations", "Se débrouiller en situation",
                                "Cavarsela nelle situazioni"),
         "Was man in einer Situation oder auf eine Äusserung sagt, Dialoge, Höflichkeit."),
        ("lesen", _titles("Leseverstehen", "Reading comprehension", "Compréhension écrite",
                          "Comprensione del testo"),
         "Fragen zu einem kurzen Text, Hauptaussage, Details, Textsorte."),
        ("aussprache", _titles("Aussprache und Schreibung", "Pronunciation and spelling",
                               "Prononciation et orthographe", "Pronuncia e ortografia"),
         "Laute, Betonung, Buchstaben, Rechtschreibung."),
    ),
    "physics": (
        ("begriffe", _titles("Begriffe verstehen", "Understanding concepts", "Comprendre les notions",
                             "Capire i concetti"),
         "Definitionen, Grössen und Einheiten, Gesetze erkennen, richtig oder falsch."),
        ("rechnen", _titles("Berechnen", "Calculating", "Calculer", "Calcolare"),
         "Mit Formeln rechnen, Werte und Einheiten bestimmen."),
        ("erklaeren", _titles("Phänomene erklären", "Explaining phenomena", "Expliquer des phénomènes",
                              "Spiegare fenomeni"),
         "Alltagsbeobachtungen und Vorgänge physikalisch erklären, Vorhersagen."),
        ("experiment", _titles("Experimente und Messen", "Experiments and measuring",
                               "Expériences et mesures", "Esperimenti e misure"),
         "Versuchsaufbau, Messgeräte, Messfehler, Ergebnisse auswerten."),
        ("diagramme", _titles("Diagramme und Graphen", "Charts and graphs", "Diagrammes et graphiques",
                              "Diagrammi e grafici"),
         "Graphen, Schaltpläne, Tabellen lesen und deuten."),
    ),
}
#: At most this many upstream knowledge points go into one star.
MAX_POINTS_PER_STAR = 12
#: Question types that deepen a knowledge point rather than make it: a star
#: lights from its core small stars, and these glow beside it when done.
EXTENSION_TYPES: dict[str, frozenset[str]] = {
    "mathematics": frozenset({"schliessen"}),
    "physics": frozenset({"experiment", "diagramme"}),
    "english": frozenset({"lesen", "aussprache"}),
}


def is_extension(subject_id: str, question_type: str) -> bool:
    return question_type in EXTENSION_TYPES.get(subject_id, frozenset())


def question_types(subject_id: str) -> dict[str, str]:
    """type slug → German title and scope, for tagging an exercise of the subject."""
    return {slug: f"{titles['de']}: {scope}" for slug, titles, scope in QUESTION_TYPES.get(subject_id, ())}


def question_type_titles(subject_id: str, slug: str) -> dict[str, str]:
    return next(titles for found, titles, _scope in QUESTION_TYPES[subject_id] if found == slug)


def skill_id(unit_id: str, question_type: str) -> str:
    """The small star of one question type around one knowledge point."""
    return f"{unit_id}--{question_type}"


def topics() -> list[dict[str, Any]]:
    """The nebulae of the new subjects."""
    return [
        *_language_topics(),
        *_subject_topics("physics", PHYSICS_TOPICS),
    ]


def grouping_units() -> list[dict[str, Any]]:
    """The coarse stars the translation files knowledge points under, before the
    structuring step splits them into knowledge-point stars."""
    return [
        {**unit, "subject_id": subject_of_topic(unit["topic_id"])}
        for unit in (*MATH_UNITS, *_language_units(), *PHYSICS_UNITS)
    ]


def topic_of_group(group_id: str) -> str:
    """The nebula a coarse star - one of the knowledge base's or a ZAP one - lies in."""
    if group_id in ZAP_UNITS:
        return group_id.rsplit("-u", 1)[0]
    return next(unit["topic_id"] for unit in grouping_units() if unit["unit_id"] == group_id)


@cache
def _stars_data() -> dict[str, Any]:
    if not STARS_FILE.exists():
        return {}
    return json.loads(STARS_FILE.read_text(encoding="utf-8"))


def units() -> list[dict[str, Any]]:
    """The knowledge-point stars of the knowledge base, in map order within each nebula."""
    stars = _stars_data().get("stars") or {}
    return [{"unit_id": unit_id, **star} for unit_id, star in stars.items()]


def subject_of_topic(topic_id: str) -> str:
    for subject_id, prefix in LANGUAGE_SUBJECTS.items():
        if topic_id.startswith(f"{prefix}-"):
            return subject_id
    if topic_id.startswith("physik-"):
        return "physics"
    return "mathematics"


def unit_choices(subject_id: str) -> dict[str, str]:
    """coarse star id → German title and scope, for filing a knowledge point of the subject."""
    if subject_id == "mathematics":
        added = {u["unit_id"]: f"{u['titles']['de']}: {u['description']}" for u in MATH_UNITS}
        return {**ZAP_UNITS, **added}
    if subject_id == "physics":
        return {u["unit_id"]: f"{u['titles']['de']}: {u['description']}" for u in PHYSICS_UNITS}
    if subject_id in LANGUAGE_SUBJECTS:
        prefix = f"{LANGUAGE_SUBJECTS[subject_id]}-"
        return {
            u["unit_id"]: f"{u['titles']['de']}: {u['description']}"
            for u in _language_units() if u["unit_id"].startswith(prefix)
        }
    return {}


def title_translations() -> dict[str, dict[str, str]]:
    """en/fr/it titles of every subject, nebula, star and practice set this module adds."""
    rows = [*SUBJECTS, *topics(), *units()]
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        content_id = row.get("unit_id") or row.get("topic_id") or row["subject_id"]
        out[content_id] = {locale: row["titles"][locale] for locale in LOCALES if locale != "de"}
    for lesson_id, titles in practice_sets().items():
        out[lesson_id] = {locale: titles[locale] for locale in LOCALES if locale != "de"}
    return out


@cache
def _skills_data() -> dict[str, Any]:
    if not SKILLS_FILE.exists():
        return {}
    return json.loads(SKILLS_FILE.read_text(encoding="utf-8"))


def skills() -> dict[str, dict[str, Any]]:
    """The small stars: skill id → subject, unit and titles by locale."""
    return dict(_skills_data().get("skills") or {})


def practice_sets() -> dict[str, dict[str, str]]:
    """The titles of the hidden practice sets, by lesson id and locale."""
    return dict(_skills_data().get("practiceSets") or {})
