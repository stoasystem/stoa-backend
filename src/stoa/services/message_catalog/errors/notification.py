"""Notification refusals (`stoa.services.notification_errors.NotificationErrorCode`).

Read by students, parents, teachers and the people who run the platform:
`du`, `vous`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.notification_event_type_unsupported": {
        "de": "Diese Art von Benachrichtigung wird nicht unterstützt.",
        "en": "This notification type is not supported.",
        "fr": "Ce type de notification n'est pas pris en charge.",
        "it": "Questo tipo di notifica non è supportato.",
    },
    "error.notification_status_unsupported": {
        "de": "Dieser Benachrichtigungsstatus wird nicht unterstützt.",
        "en": "This notification status is not supported.",
        "fr": "Ce statut de notification n'est pas pris en charge.",
        "it": "Questo stato di notifica non è supportato.",
    },
    "error.notification_recipient_role_required": {
        "de": "Gib an, für welche Rolle die Benachrichtigung bestimmt ist.",
        "en": "Name the role the notification is for.",
        "fr": "Indiquez à quel rôle la notification est destinée.",
        "it": "Indica a quale ruolo è destinata la notifica.",
    },
    "error.notification_owner_required": {
        "de": "Diese Benachrichtigung braucht die Person, der der Inhalt gehört.",
        "en": "This notification needs the person who owns its content.",
        "fr": "Cette notification doit indiquer la personne à qui appartient son contenu.",
        "it": "Questa notifica deve indicare la persona a cui appartiene il contenuto.",
    },
    "error.notification_preference_category_unsupported": {
        "de": "Diese Benachrichtigungskategorie gibt es nicht.",
        "en": "This notification category does not exist.",
        "fr": "Cette catégorie de notifications n'existe pas.",
        "it": "Questa categoria di notifiche non esiste.",
    },
    "error.notification_preference_channels_invalid": {
        "de": "Die Kanäle einer Kategorie müssen als Liste von Einstellungen angegeben werden.",
        "en": "A category's channels must be given as a set of settings.",
        "fr": "Les canaux d'une catégorie doivent être indiqués sous forme de réglages.",
        "it": "I canali di una categoria devono essere indicati come insieme di impostazioni.",
    },
    "error.notification_preference_channel_unsupported": {
        "de": "Diesen Benachrichtigungskanal gibt es nicht.",
        "en": "This notification channel does not exist.",
        "fr": "Ce canal de notification n'existe pas.",
        "it": "Questo canale di notifica non esiste.",
    },
    "error.notification_preference_value_invalid": {
        "de": "Ein Kanal kann nur ein- oder ausgeschaltet werden.",
        "en": "A channel can only be switched on or off.",
        "fr": "Un canal peut seulement être activé ou désactivé.",
        "it": "Un canale può solo essere attivato o disattivato.",
    },
    "error.push_platform_unsupported": {
        "de": "Push-Benachrichtigungen werden auf diesem Gerätetyp nicht unterstützt.",
        "en": "Push notifications are not supported on this device type.",
        "fr": "Les notifications push ne sont pas prises en charge sur ce type d'appareil.",
        "it": "Le notifiche push non sono supportate su questo tipo di dispositivo.",
    },
    "error.push_token_required": {
        "de": "Für Push-Benachrichtigungen fehlt die Kennung des Geräts.",
        "en": "The device's push token is missing.",
        "fr": "L'identifiant push de l'appareil est manquant.",
        "it": "Manca l'identificativo push del dispositivo.",
    },
    "error.push_token_not_found": {
        "de": "Dieses Gerät ist nicht für Push-Benachrichtigungen angemeldet.",
        "en": "This device is not registered for push notifications.",
        "fr": "Cet appareil n'est pas inscrit aux notifications push.",
        "it": "Questo dispositivo non è registrato per le notifiche push.",
    },
    "error.notification_transition_unsupported": {
        "de": "Eine Benachrichtigung kann nur gelesen oder archiviert werden.",
        "en": "A notification can only be marked read or archived.",
        "fr": "Une notification peut seulement être marquée comme lue ou archivée.",
        "it": "Una notifica può solo essere segnata come letta o archiviata.",
    },
    "error.notification_not_found": {
        "de": "Diese Benachrichtigung wurde nicht gefunden.",
        "en": "This notification was not found.",
        "fr": "Cette notification est introuvable.",
        "it": "Questa notifica non è stata trovata.",
    },
    "error.websocket_connection_id_required": {
        "de": "Der Live-Verbindung fehlt ihre Kennung.",
        "en": "The live connection has no id.",
        "fr": "La connexion en direct n'a pas d'identifiant.",
        "it": "La connessione in tempo reale non ha un identificativo.",
    },
    "error.websocket_channel_required": {
        "de": "Wähle mindestens einen Kanal für die Live-Verbindung.",
        "en": "Choose at least one channel for the live connection.",
        "fr": "Choisissez au moins un canal pour la connexion en direct.",
        "it": "Scegli almeno un canale per la connessione in tempo reale.",
    },
    "error.websocket_connection_not_found": {
        "de": "Diese Live-Verbindung besteht nicht mehr.",
        "en": "This live connection no longer exists.",
        "fr": "Cette connexion en direct n'existe plus.",
        "it": "Questa connessione in tempo reale non esiste più.",
    },
    "error.notification_event_id_required": {
        "de": "Der Benachrichtigung fehlt ihre Kennung.",
        "en": "The notification has no id.",
        "fr": "La notification n'a pas d'identifiant.",
        "it": "La notifica non ha un identificativo.",
    },
    "error.email_unsubscribe_link_invalid": {
        "de": "Dieser Abmeldelink ist ungültig. Sie können die E-Mails in STOA in den Benachrichtigungseinstellungen abschalten.",
        "en": "This unsubscribe link is not valid. You can turn these emails off in STOA's notification settings.",
        "fr": "Ce lien de désabonnement n'est pas valide. Vous pouvez désactiver ces e-mails dans les paramètres de notification de STOA.",
        "it": "Questo link di disiscrizione non è valido. Può disattivare queste e-mail nelle impostazioni delle notifiche di STOA.",
    },
}
