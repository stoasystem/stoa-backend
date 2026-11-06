"""Request validation messages a client is expected to show (`security.errors`).

Most of a 422 is for the developer of the client: a field location and
pydantic's own wording. These two are for the person filling in the
registration form, so they carry a code and are rendered from here.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.age_out_of_range": {
        "de": "Das Alter muss eine ganze Zahl zwischen {min_age} und {max_age} sein.",
        "en": "Age must be a whole number between {min_age} and {max_age}.",
        "fr": "L'âge doit être un nombre entier compris entre {min_age} et {max_age}.",
        "it": "L'età deve essere un numero intero tra {min_age} e {max_age}.",
    },
    "error.parent_contact_required": {
        "de": "Für Schülerinnen und Schüler unter {adult_age} sind Name und E-Mail-Adresse eines Elternteils nötig.",
        "en": "Parent name and parent email are required for students under {adult_age}.",
        "fr": "Pour les élèves de moins de {adult_age} ans, le nom et l'adresse e-mail d'un parent sont requis.",
        "it": "Per gli allievi con meno di {adult_age} anni servono il nome e l'indirizzo e-mail di un genitore.",
    },
}
