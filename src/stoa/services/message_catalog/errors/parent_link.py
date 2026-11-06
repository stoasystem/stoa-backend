"""Parent-student link refusals (`stoa.services.parent_link_service.ParentLinkErrorCode`).

Read by parents, students and administrators alike, so worded without
addressing anyone.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.link_target_not_found": {
        "de": "Zu dieser Nummer wurde kein passendes Konto gefunden.",
        "en": "No matching account was found for this number.",
        "fr": "Aucun compte correspondant n'a été trouvé pour ce numéro.",
        "it": "Non è stato trovato nessun account corrispondente a questo numero.",
    },
    "error.link_initiator_not_allowed": {
        "de": "Dieses Konto kann keine Verknüpfung anfragen.",
        "en": "This account cannot request a link.",
        "fr": "Ce compte ne peut pas demander de liaison.",
        "it": "Questo account non può richiedere un collegamento.",
    },
    "error.link_not_pending": {
        "de": "Zu diesem Konto liegt keine offene Anfrage vor.",
        "en": "There is no open request for this account.",
        "fr": "Il n'y a aucune demande en attente pour ce compte.",
        "it": "Non c'è nessuna richiesta in sospeso per questo account.",
    },
    "error.link_confirmation_not_allowed": {
        "de": "Diese Anfrage kann nur die andere Seite bestätigen.",
        "en": "Only the other side can answer this request.",
        "fr": "Seule l'autre partie peut répondre à cette demande.",
        "it": "Solo l'altra parte può rispondere a questa richiesta.",
    },
    "error.link_requires_administrator": {
        "de": "Diese Verknüpfung kann nur die Administration einrichten.",
        "en": "Only an administrator can set up this link.",
        "fr": "Seule l'administration peut établir cette liaison.",
        "it": "Solo l'amministrazione può creare questo collegamento.",
    },
    "error.link_confirmation_not_applicable": {
        "de": "Diese Verknüpfung muss nicht bestätigt werden.",
        "en": "This link does not need to be confirmed.",
        "fr": "Cette liaison n'a pas besoin d'être confirmée.",
        "it": "Questo collegamento non deve essere confermato.",
    },
    "error.link_already_active": {
        "de": "Diese Konten sind schon verknüpft.",
        "en": "These accounts are already linked.",
        "fr": "Ces comptes sont déjà liés.",
        "it": "Questi account sono già collegati.",
    },
    "error.link_request_pending": {
        "de": "Für diese Konten ist schon eine Anfrage offen.",
        "en": "A request for these accounts is already open.",
        "fr": "Une demande pour ces comptes est déjà en attente.",
        "it": "Per questi account c'è già una richiesta in sospeso.",
    },
    "error.link_request_expired": {
        "de": "Diese Anfrage ist abgelaufen. Eine neue kann gestellt werden.",
        "en": "This request has expired. A new one can be made.",
        "fr": "Cette demande a expiré. Une nouvelle demande peut être faite.",
        "it": "Questa richiesta è scaduta. Se ne può fare una nuova.",
    },
    "error.link_rejected_cooldown": {
        "de": "Diese Anfrage wurde abgelehnt. Eine neue ist erst später wieder möglich.",
        "en": "This request was declined. A new one is possible again later.",
        "fr": "Cette demande a été refusée. Une nouvelle demande sera possible plus tard.",
        "it": "Questa richiesta è stata rifiutata. Una nuova sarà possibile più avanti.",
    },
    "error.link_request_conflict": {
        "de": "Die Anfrage hat sich mit einer anderen überschnitten. Bitte noch einmal versuchen.",
        "en": "The request crossed with another one. Please try again.",
        "fr": "La demande s'est croisée avec une autre. Veuillez réessayer.",
        "it": "La richiesta si è sovrapposta a un'altra. Riprovare, per favore.",
    },
    "error.link_already_exists": {
        "de": "Für diese Konten besteht schon eine Verknüpfung.",
        "en": "A link for these accounts already exists.",
        "fr": "Une liaison existe déjà pour ces comptes.",
        "it": "Per questi account esiste già un collegamento.",
    },
    "error.link_request_rate_limited": {
        "de": "Heute wurden zu viele Anfragen gestellt. Morgen ist es wieder möglich.",
        "en": "Too many requests were made today. It is possible again tomorrow.",
        "fr": "Trop de demandes ont été faites aujourd'hui. Ce sera de nouveau possible demain.",
        "it": "Oggi sono state fatte troppe richieste. Sarà di nuovo possibile domani.",
    },
    "error.account_number_lookup_unavailable": {
        "de": "Die Kontonummer kann gerade nicht geprüft werden. Bitte später noch einmal versuchen.",
        "en": "The account number cannot be checked right now. Please try again later.",
        "fr": "Le numéro de compte ne peut pas être vérifié pour le moment. Veuillez réessayer plus tard.",
        "it": "Al momento il numero dell'account non può essere verificato. Riprovare più tardi.",
    },
}
