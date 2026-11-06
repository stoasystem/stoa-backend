"""A help request's refusals (`stoa.services.help_requests.HelpRequestErrorCode`).

The first three are read by the teacher working on a request, addressed as the
teacher notifications are: `Sie`, `vous`, `Lei`. The rest are read by the
student who asked, addressed as the web client addresses them: `du`, `tu`,
`tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    # ── the teacher's writes ─────────────────────────────────────────────
    "error.help_request_not_held": {
        "de": (
            "Nur die Lehrperson, die diese Anfrage betreut oder angeboten bekommen hat, "
            "kann sie ändern."
        ),
        "en": "Only the teacher who holds or was offered this help request can change it.",
        "fr": (
            "Seul l'enseignant qui suit cette demande d'aide ou à qui elle a été proposée "
            "peut la modifier."
        ),
        "it": (
            "Solo l'insegnante che segue questa richiesta di aiuto o a cui è stata proposta "
            "può modificarla."
        ),
    },
    "error.help_request_changed": {
        "de": "Diese Anfrage hat sich geändert. Bitte laden Sie sie neu und versuchen Sie es noch einmal.",
        "en": "This help request changed. Refresh it and try again.",
        "fr": "Cette demande d'aide a changé. Actualisez-la et réessayez.",
        "it": "Questa richiesta di aiuto è cambiata. La aggiorni e riprovi.",
    },
    "error.help_request_unavailable": {
        "de": "Die Anfrage kann gerade nicht gelesen werden. Bitte versuchen Sie es gleich noch einmal.",
        "en": "The help request could not be read. Please try again shortly.",
        "fr": "La demande d'aide ne peut pas être lue pour le moment. Réessayez dans un instant.",
        "it": "Al momento non è possibile leggere la richiesta di aiuto. Riprovi tra poco.",
    },
    # ── the student asking ───────────────────────────────────────────────
    "error.teacher_support_admission_recoverable": {
        "de": "Die Hilfe durch Lehrpersonen ist kurz nicht erreichbar. Versuche es gleich noch einmal.",
        "en": "Teacher support is briefly unavailable. Please try again.",
        "fr": "L'aide des enseignants est momentanément indisponible. Réessaie dans un instant.",
        "it": "L'aiuto degli insegnanti non è disponibile per un momento. Riprova tra poco.",
    },
    "error.teacher_support_not_included": {
        "de": "Die Hilfe durch Lehrpersonen ist für dieses Konto nicht eingeschaltet.",
        "en": "Teacher support is not switched on for this account.",
        "fr": "L'aide des enseignants n'est pas activée pour ce compte.",
        "it": "L'aiuto degli insegnanti non è attivato per questo account.",
    },
    "error.teacher_support_allowance_exhausted": {
        "de": "Die Anfragen an Lehrpersonen für diese Woche sind aufgebraucht.",
        "en": "The weekly teacher-support allowance is used.",
        "fr": "Les demandes aux enseignants de cette semaine sont épuisées.",
        "it": "Le richieste agli insegnanti di questa settimana sono esaurite.",
    },
    "error.teacher_support_case_conflict": {
        "de": "Diese Anfrage passt nicht zu einer früheren Anfrage mit derselben Kennung.",
        "en": "This request does not match an earlier one with the same identity.",
        "fr": "Cette demande ne correspond pas à une demande précédente portant le même identifiant.",
        "it": "Questa richiesta non corrisponde a una precedente con lo stesso identificativo.",
    },
    "error.teacher_help_not_requested": {
        "de": "In diesem Gespräch wurde keine Lehrperson um Hilfe gebeten.",
        "en": "No teacher was asked for help in this conversation.",
        "fr": "Aucun enseignant n'a été sollicité dans cette conversation.",
        "it": "In questa conversazione non è stato chiesto aiuto a nessun insegnante.",
    },
    # ── ending a request nobody took ─────────────────────────────────────
    "error.teacher_help_request_not_found": {
        "de": "Diese Anfrage an eine Lehrperson gibt es nicht.",
        "en": "This request for a teacher does not exist.",
        "fr": "Cette demande à un enseignant n'existe pas.",
        "it": "Questa richiesta a un insegnante non esiste.",
    },
    "error.teacher_help_already_accepted": {
        "de": "Eine Lehrperson hat diese Anfrage schon angenommen.",
        "en": "A teacher has already taken this request.",
        "fr": "Un enseignant a déjà accepté cette demande.",
        "it": "Un insegnante ha già accettato questa richiesta.",
    },
    "error.teacher_help_request_closed": {
        "de": "Diese Anfrage ist schon abgeschlossen.",
        "en": "This request is already closed.",
        "fr": "Cette demande est déjà close.",
        "it": "Questa richiesta è già chiusa.",
    },
    "error.teacher_help_request_not_due": {
        "de": "Diese Anfrage läuft noch nicht ab.",
        "en": "This request is not due to expire yet.",
        "fr": "Cette demande n'arrive pas encore à expiration.",
        "it": "Questa richiesta non è ancora in scadenza.",
    },
    "error.teacher_help_request_not_withdrawable": {
        "de": "Diese Anfrage kann nicht mehr zurückgezogen werden.",
        "en": "This request can no longer be withdrawn.",
        "fr": "Cette demande ne peut plus être retirée.",
        "it": "Questa richiesta non può più essere ritirata.",
    },
    "error.teacher_help_withdrawal_unavailable": {
        "de": "Zurückziehen ist kurz nicht möglich. Versuche es gleich noch einmal.",
        "en": "Withdrawing is briefly unavailable. Please try again.",
        "fr": "Le retrait est momentanément impossible. Réessaie dans un instant.",
        "it": "Il ritiro non è possibile per un momento. Riprova tra poco.",
    },
}
