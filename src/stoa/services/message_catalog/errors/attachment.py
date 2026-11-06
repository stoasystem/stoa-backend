"""Upload and attachment refusals (`stoa.security.attachment_errors.AttachmentErrorCode`).

Read by a student attaching a file, addressed as the web client addresses
them: `du`, `tu`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.attachment_in_use": {
        "de": "Entferne diese Datei zuerst aus ihrer Unterhaltung oder Frage.",
        "en": "Remove this attachment from its conversation or question first.",
        "fr": "Retire d'abord ce fichier de sa conversation ou de sa question.",
        "it": "Togli prima questo file dalla sua conversazione o domanda.",
    },
    "error.upload_not_found": {
        "de": "Wähle die Datei aus oder lade sie noch einmal hoch.",
        "en": "Select or upload the file again.",
        "fr": "Choisis ou envoie à nouveau le fichier.",
        "it": "Scegli o carica di nuovo il file.",
    },
    "error.upload_expired": {
        "de": "Dieser Upload ist abgelaufen. Wähle die Datei noch einmal aus.",
        "en": "This upload expired. Select the file again.",
        "fr": "Cet envoi a expiré. Choisis à nouveau le fichier.",
        "it": "Questo caricamento è scaduto. Scegli di nuovo il file.",
    },
    "error.upload_too_large": {
        "de": "Diese Datei ist zu gross. Wähle eine kleinere Datei.",
        "en": "This file is too large. Choose a smaller file.",
        "fr": "Ce fichier est trop lourd. Choisis un fichier plus petit.",
        "it": "Questo file è troppo grande. Scegli un file più piccolo.",
    },
    "error.upload_type_not_supported": {
        "de": "Diese Art von Datei wird nicht unterstützt. Wähle eine andere Datei.",
        "en": "This file type is not supported. Choose another file.",
        "fr": "Ce type de fichier n'est pas pris en charge. Choisis un autre fichier.",
        "it": "Questo tipo di file non è supportato. Scegli un altro file.",
    },
    "error.upload_content_mismatch": {
        "de": "Diese Datei passt nicht zu ihrem Dateityp. Wähle die Datei noch einmal aus.",
        "en": "This file does not match its type. Select the file again.",
        "fr": "Ce fichier ne correspond pas à son type. Choisis à nouveau le fichier.",
        "it": "Questo file non corrisponde al suo tipo. Scegli di nuovo il file.",
    },
    "error.upload_invalid": {
        "de": "Diese Datei ist möglicherweise beschädigt. Wähle eine andere Datei.",
        "en": "This file may be damaged. Select another file.",
        "fr": "Ce fichier est peut-être endommagé. Choisis un autre fichier.",
        "it": "Questo file potrebbe essere danneggiato. Scegli un altro file.",
    },
    "error.upload_content_blocked": {
        "de": (
            "Dieses Bild kann nicht gesendet werden. Wähle ein anderes Bild "
            "oder beschreibe das Problem in Worten."
        ),
        "en": "This image cannot be sent. Choose another image or describe the problem in words.",
        "fr": (
            "Cette image ne peut pas être envoyée. Choisis une autre image "
            "ou décris le problème avec des mots."
        ),
        "it": (
            "Questa immagine non può essere inviata. Scegli un'altra immagine "
            "o descrivi il problema a parole."
        ),
    },
    "error.upload_chunk_conflict": {
        "de": (
            "Dieser Teil des Uploads passt nicht zu einem früheren Teil. "
            "Wähle die Datei noch einmal aus."
        ),
        "en": "This upload chunk conflicts with an earlier chunk. Select the file again.",
        "fr": (
            "Cette partie de l'envoi ne correspond pas à une partie précédente. "
            "Choisis à nouveau le fichier."
        ),
        "it": (
            "Questa parte del caricamento non corrisponde a una parte precedente. "
            "Scegli di nuovo il file."
        ),
    },
    "error.storage_quota_exceeded": {
        "de": "Dein Speicher ist voll. Lösche Dateien oder wechsle zu einem grösseren Abo.",
        "en": "Storage is full. Delete attachments or upgrade your plan.",
        "fr": "Ton espace de stockage est plein. Supprime des fichiers ou passe à une offre supérieure.",
        "it": "Lo spazio di archiviazione è pieno. Elimina dei file o passa a un piano superiore.",
    },
    "error.upload_service_unavailable": {
        "de": "Uploads sind gerade nicht möglich. Versuche es später noch einmal.",
        "en": "Uploads are temporarily unavailable. Try again later.",
        "fr": "L'envoi de fichiers est temporairement indisponible. Réessaie plus tard.",
        "it": "Il caricamento dei file non è momentaneamente disponibile. Riprova più tardi.",
    },
    "error.upload_code_invalid": {
        "de": "Dieser Code ist nicht mehr gültig. Lass dir auf deinem Computer einen neuen Code anzeigen.",
        "en": "This code is no longer valid. Show a new code on your computer.",
        "fr": "Ce code n'est plus valable. Affiche un nouveau code sur ton ordinateur.",
        "it": "Questo codice non è più valido. Mostra un nuovo codice sul tuo computer.",
    },
    "error.upload_code_rate_limited": {
        "de": "Zu viele Versuche. Versuche es später noch einmal.",
        "en": "Too many attempts. Try again later.",
        "fr": "Trop de tentatives. Réessaie plus tard.",
        "it": "Troppi tentativi. Riprova più tardi.",
    },
}
