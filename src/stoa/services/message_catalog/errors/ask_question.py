"""A question's own refusals (`stoa.services.ask_question.AskQuestionErrorCode`).

Read by the student who asked, addressed as the web client addresses them:
`du`, `tu`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.message_idempotency_conflict": {
        "de": "Dieser Nachrichtenschlüssel wurde schon für eine andere Anfrage verwendet.",
        "en": "This message key was already used for a different request.",
        "fr": "Cette clé de message a déjà été utilisée pour une autre demande.",
        "it": "Questa chiave del messaggio è già stata usata per un'altra richiesta.",
    },
    "error.message_in_progress": {
        "de": "Diese Nachricht wird noch bearbeitet. Versuche es gleich noch einmal.",
        "en": "This message is still being processed. Try again shortly.",
        "fr": "Ce message est encore en cours de traitement. Réessaie dans un instant.",
        "it": "Questo messaggio è ancora in elaborazione. Riprova tra poco.",
    },
    "error.message_daily_limit": {
        "de": "Du hast dein Tageslimit für Nachrichten erreicht. Versuche es morgen wieder.",
        "en": "Your daily message limit is reached. Try again tomorrow.",
        "fr": "Tu as atteint ta limite de messages pour aujourd'hui. Réessaie demain.",
        "it": "Hai raggiunto il limite giornaliero di messaggi. Riprova domani.",
    },
    "error.message_failed": {
        "de": "Diese Nachricht konnte nicht fertig bearbeitet werden. Sende sie noch einmal.",
        "en": "This message could not be completed. Send it again.",
        "fr": "Ce message n'a pas pu être traité jusqu'au bout. Envoie-le à nouveau.",
        "it": "Non è stato possibile completare questo messaggio. Invialo di nuovo.",
    },
    "error.message_command_expired": {
        "de": "Diese Anfrage ist abgelaufen. Sende die Nachricht noch einmal.",
        "en": "This message request expired. Send it again.",
        "fr": "Cette demande a expiré. Envoie le message à nouveau.",
        "it": "Questa richiesta è scaduta. Invia di nuovo il messaggio.",
    },
    "error.message_command_not_found": {
        "de": "Diese Anfrage ist nicht mehr verfügbar. Sende die Nachricht noch einmal.",
        "en": "This message request is unavailable. Send it again.",
        "fr": "Cette demande n'est plus disponible. Envoie le message à nouveau.",
        "it": "Questa richiesta non è più disponibile. Invia di nuovo il messaggio.",
    },
    "error.allowance_exhausted": {
        "de": "Dein wöchentliches KI-Kontingent ist aufgebraucht.",
        "en": "Weekly AI token allowance is exhausted.",
        "fr": "Ton quota hebdomadaire d'IA est épuisé.",
        "it": "La tua quota settimanale di IA è esaurita.",
    },
    "error.provider_token_count_unavailable": {
        "de": "Die Prüfung deines KI-Kontingents ist gerade nicht möglich. Sende die Nachricht noch einmal.",
        "en": "Token admission is temporarily unavailable. Retry this message.",
        "fr": "La vérification de ton quota d'IA est temporairement indisponible. Renvoie ce message.",
        "it": "Il controllo della tua quota di IA non è momentaneamente disponibile. Invia di nuovo il messaggio.",
    },
    "error.allowance_unavailable": {
        "de": (
            "Diese Antwort geht nicht verloren, während dein KI-Kontingent abgerechnet wird. "
            "Sende die Nachricht später noch einmal."
        ),
        "en": "This answer is safely recoverable while token accounting finishes.",
        "fr": (
            "Cette réponse n'est pas perdue pendant le décompte de ton quota d'IA. "
            "Renvoie le message un peu plus tard."
        ),
        "it": (
            "Questa risposta non va persa mentre si conteggia la tua quota di IA. "
            "Invia di nuovo il messaggio più tardi."
        ),
    },
}
