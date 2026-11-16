"""The classroom's refusals (`stoa.services.classroom.ClassroomErrorCode`).

Read by the student and the teacher entering a help request's classroom.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.classroom_unavailable": {
        "de": "Das Klassenzimmer ist gerade nicht verfügbar. Versuche es gleich noch einmal.",
        "en": "The classroom is not available right now. Please try again shortly.",
        "fr": "La salle de classe n'est pas disponible pour le moment. Réessaie dans un instant.",
        "it": "L'aula non è disponibile al momento. Riprova tra poco.",
    },
}
