"""Moderation refusals (`stoa.services.moderation_errors.ModerationErrorCode`).

Read by the student or teacher reporting content and by the moderators:
`du`, `vous`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.question_not_writable": {
        "de": "Zu dieser Frage kann gerade keine Meldung erstellt werden.",
        "en": "No report can be made about this question right now.",
        "fr": "Aucun signalement ne peut être fait sur cette question pour le moment.",
        "it": "Al momento non è possibile segnalare questa domanda.",
    },
    "error.moderation_case_not_found": {
        "de": "Dieser Moderationsfall wurde nicht gefunden.",
        "en": "This moderation case was not found.",
        "fr": "Ce cas de modération est introuvable.",
        "it": "Questo caso di moderazione non è stato trovato.",
    },
    "error.case_image_not_found": {
        "de": "Zu diesem Moderationsfall gibt es kein Bild.",
        "en": "This moderation case has no image.",
        "fr": "Ce cas de modération n'a pas d'image.",
        "it": "Questo caso di moderazione non ha un'immagine.",
    },
    "error.case_image_unavailable": {
        "de": "Das Bild dieses Falls kann gerade nicht geladen werden. Versuche es später noch einmal.",
        "en": "This case's image cannot be loaded right now. Try again later.",
        "fr": "L'image de ce cas ne peut pas être chargée pour le moment. Réessayez plus tard.",
        "it": "Al momento non è possibile caricare l'immagine di questo caso. Riprova più tardi.",
    },
    "error.image_case_not_reportable": {
        "de": "Bildfälle werden nur von der Moderation eröffnet.",
        "en": "Image cases are opened by moderation only.",
        "fr": "Les cas portant sur une image sont ouverts uniquement par la modération.",
        "it": "I casi relativi alle immagini vengono aperti solo dalla moderazione.",
    },
    "error.reported_message_not_found": {
        "de": "Die gemeldete Nachricht wurde nicht gefunden.",
        "en": "The reported message was not found.",
        "fr": "Le message signalé est introuvable.",
        "it": "Il messaggio segnalato non è stato trovato.",
    },
    "error.no_ai_answer_to_report": {
        "de": "Zu dieser Frage gibt es keine KI-Antwort, die gemeldet werden könnte.",
        "en": "This question has no AI answer to report.",
        "fr": "Cette question n'a pas de réponse de l'IA à signaler.",
        "it": "Questa domanda non ha una risposta dell'IA da segnalare.",
    },
    "error.no_teacher_reply_to_report": {
        "de": "Zu dieser Frage gibt es keine Antwort einer Lehrperson, die gemeldet werden könnte.",
        "en": "This question has no teacher reply to report.",
        "fr": "Cette question n'a pas de réponse d'enseignant à signaler.",
        "it": "Questa domanda non ha una risposta dell'insegnante da segnalare.",
    },
}
