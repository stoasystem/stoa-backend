"""The rate admission's refusals (`stoa.services.rate_limit_errors.RateLimitErrorCode`).

Read by the student asking for a hint: `du`, `tu`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.hint_daily_limit": {
        "de": "Du hast dein Tageslimit von {limit} Tipps erreicht. Versuche es morgen wieder.",
        "en": "You have reached your daily limit of {limit} hints. Try again tomorrow.",
        "fr": "Tu as atteint ta limite de {limit} indices pour aujourd'hui. Réessaie demain.",
        "it": "Hai raggiunto il limite giornaliero di {limit} suggerimenti. Riprova domani.",
    },
    "error.rate_operation_conflict": {
        "de": "Dieser Anfrageschlüssel wurde schon für eine andere Anfrage verwendet.",
        "en": "This idempotency key was already used for another request.",
        "fr": "Cette clé de requête a déjà été utilisée pour une autre demande.",
        "it": "Questa chiave di richiesta è già stata usata per un'altra richiesta.",
    },
    "error.rate_limit_unavailable": {
        "de": "Dein Kontingent kann gerade nicht geprüft werden. Versuche es gleich noch einmal.",
        "en": "Usage admission is temporarily unavailable. Please try again.",
        "fr": "Ton quota ne peut pas être vérifié pour le moment. Réessaie dans un instant.",
        "it": "Al momento non è possibile verificare la tua quota. Riprova tra poco.",
    },
}
