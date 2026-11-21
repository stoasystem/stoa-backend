"""An unexpected failure (`stoa.unexpected_failure.ServerErrorCode`).

Read by students, parents and teachers alike, addressed as the sign-in copy
is: `du` in German, `vous` in French, `tu` in Italian.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.internal_error": {
        "de": (
            "Etwas ist bei uns schiefgelaufen. Versuche es später noch einmal. Wenn das "
            "Problem bleibt, wende dich an den Support und gib die angezeigte Referenz an."
        ),
        "en": (
            "Something went wrong on our side. Try again later. If the problem "
            "continues, contact support and share the reference shown."
        ),
        "fr": (
            "Une erreur s'est produite de notre côté. Réessayez plus tard. Si le problème "
            "persiste, contactez le support en indiquant la référence affichée."
        ),
        "it": (
            "Qualcosa è andato storto da parte nostra. Riprova più tardi. Se il problema "
            "persiste, contatta il supporto indicando il riferimento mostrato."
        ),
    },
}
