"""Why a teacher's reply was not taken (`stoa.services.teacher_reply_service.TeacherReplyErrorCode`).

Read by the teacher who wrote it, addressed as the teacher notifications are:
`Sie`, `vous`, `Lei`. `{max}` is the limit that was passed, in characters or
blocks.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.teacher_reply_unsafe_html": {
        "de": "Die Antwort enthält HTML, das nicht erlaubt ist. Bitte entfernen Sie es.",
        "en": "The reply contains HTML that is not allowed. Please remove it.",
        "fr": "La réponse contient du HTML non autorisé. Veuillez le retirer.",
        "it": "La risposta contiene HTML non consentito. La preghiamo di rimuoverlo.",
    },
    "error.teacher_reply_private_markers": {
        "de": (
            "Die Antwort enthält einen privaten Link oder Zugangsdaten. "
            "Bitte entfernen Sie sie."
        ),
        "en": "The reply contains a private link or credentials. Please remove them.",
        "fr": "La réponse contient un lien privé ou des identifiants. Veuillez les retirer.",
        "it": "La risposta contiene un link privato o credenziali. La preghiamo di rimuoverli.",
    },
    "error.teacher_reply_block_too_long": {
        "de": "Ein Abschnitt der Antwort ist länger als {max} Zeichen. Bitte kürzen Sie ihn.",
        "en": "A part of the reply is longer than {max} characters. Please shorten it.",
        "fr": "Une partie de la réponse dépasse {max} caractères. Veuillez la raccourcir.",
        "it": "Una parte della risposta supera i {max} caratteri. La preghiamo di accorciarla.",
    },
    "error.teacher_reply_too_many_blocks": {
        "de": "Die Antwort hat mehr als {max} Abschnitte. Bitte fassen Sie sie zusammen.",
        "en": "The reply has more than {max} parts. Please combine some of them.",
        "fr": "La réponse compte plus de {max} parties. Veuillez en regrouper certaines.",
        "it": "La risposta ha più di {max} parti. La preghiamo di unirne alcune.",
    },
    "error.teacher_reply_too_long": {
        "de": "Die Antwort ist länger als {max} Zeichen. Bitte kürzen Sie sie.",
        "en": "The reply is longer than {max} characters. Please shorten it.",
        "fr": "La réponse dépasse {max} caractères. Veuillez la raccourcir.",
        "it": "La risposta supera i {max} caratteri. La preghiamo di accorciarla.",
    },
    "error.teacher_reply_empty": {
        "de": "Die Antwort ist leer. Bitte schreiben Sie etwas.",
        "en": "The reply is empty. Please write something.",
        "fr": "La réponse est vide. Veuillez écrire quelque chose.",
        "it": "La risposta è vuota. La preghiamo di scrivere qualcosa.",
    },
    "error.teacher_reply_malformed": {
        "de": "Die Antwort hat ein Format, das nicht unterstützt wird.",
        "en": "The reply is in a format that is not supported.",
        "fr": "La réponse est dans un format qui n'est pas pris en charge.",
        "it": "La risposta è in un formato non supportato.",
    },
}
