"""The misconception each rule-inferred error cause records (`stoa.services.error_causes`, #453).

A typed answer's cause is inferred by a fixed rule, so its misconception is a
fixed sentence per rule rather than one an author wrote. The receipt keeps the
sentence in every locale, like an authored one. Read by a teacher or a parent
about a student, in the third person.
"""

TEXT: dict[str, dict[str, str]] = {
    "error_cause.sign": {
        "de": "Rechnet richtig, verliert aber das Vorzeichen.",
        "en": "Calculates correctly but gets the sign wrong.",
        "fr": "Calcule correctement mais se trompe de signe.",
        "it": "Calcola correttamente ma sbaglia il segno.",
    },
    "error_cause.close": {
        "de": "Kommt fast auf das Ergebnis, verrechnet oder verrundet sich aber knapp.",
        "en": "Nearly reaches the result but slips in a calculation or in rounding.",
        "fr": "Arrive presque au résultat mais fait une petite erreur de calcul ou d’arrondi.",
        "it": "Arriva quasi al risultato ma sbaglia di poco un calcolo o un arrotondamento.",
    },
}
