"""AI teacher tool refusals (`stoa.services.ai_teacher_tools_errors.AiTeacherToolsErrorCode`).

Read by teachers and admins: `du`, `vous`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.ai_draft_not_found": {
        "de": "Dieser Entwurf wurde nicht gefunden.",
        "en": "This draft was not found.",
        "fr": "Ce brouillon est introuvable.",
        "it": "Questa bozza non è stata trovata.",
    },
    "error.draft_already_archived": {
        "de": "Dieser Entwurf ist schon archiviert.",
        "en": "This draft is already archived.",
        "fr": "Ce brouillon est déjà archivé.",
        "it": "Questa bozza è già archiviata.",
    },
    "error.draft_already_reviewed": {
        "de": "Dieser Entwurf wurde schon angenommen oder abgelehnt.",
        "en": "This draft has already been accepted or rejected.",
        "fr": "Ce brouillon a déjà été accepté ou refusé.",
        "it": "Questa bozza è già stata accettata o rifiutata.",
    },
    "error.draft_question_unavailable": {
        "de": "Die Frage, aus der dieser Entwurf entstand, ist nicht mehr verfügbar.",
        "en": "The question this draft was made from is no longer available.",
        "fr": "La question à l'origine de ce brouillon n'est plus disponible.",
        "it": "La domanda da cui è nata questa bozza non è più disponibile.",
    },
    "error.draft_type_unsupported": {
        "de": "Diese Art von Entwurf wird nicht unterstützt.",
        "en": "This draft type is not supported.",
        "fr": "Ce type de brouillon n'est pas pris en charge.",
        "it": "Questo tipo di bozza non è supportato.",
    },
    "error.draft_option_unsupported": {
        "de": "Dieser Wert für «{field}» wird nicht unterstützt.",
        "en": "This value for “{field}” is not supported.",
        "fr": "Cette valeur pour « {field} » n'est pas prise en charge.",
        "it": "Questo valore per «{field}» non è supportato.",
    },
    "error.question_of_another_student": {
        "de": "Diese Frage gehört zu einer anderen Schülerin oder einem anderen Schüler.",
        "en": "This question belongs to another student.",
        "fr": "Cette question appartient à un autre élève.",
        "it": "Questa domanda appartiene a un altro studente.",
    },
    "error.subject_unsupported": {
        "de": "Dieses Fach wird nicht unterstützt.",
        "en": "This subject is not supported.",
        "fr": "Cette matière n'est pas prise en charge.",
        "it": "Questa materia non è supportata.",
    },
    "error.topic_required": {
        "de": "Wähle mindestens ein Thema.",
        "en": "Choose at least one topic.",
        "fr": "Choisissez au moins un thème.",
        "it": "Scegli almeno un argomento.",
    },
    "error.exercise_count_invalid": {
        "de": "Die Anzahl Aufgaben muss zwischen 1 und {max} liegen.",
        "en": "The number of exercises must be between 1 and {max}.",
        "fr": "Le nombre d'exercices doit être compris entre 1 et {max}.",
        "it": "Il numero di esercizi deve essere compreso tra 1 e {max}.",
    },
}
