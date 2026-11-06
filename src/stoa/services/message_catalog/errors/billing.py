"""A parent's billing pages' refusals (`stoa.services.billing_errors.BillingErrorCode`).

Read by parents, addressed as the teacher notifications are: `Sie`, `vous`,
`Lei`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.checkout_not_found": {
        "de": "Dieser Bezahlvorgang wurde nicht gefunden.",
        "en": "Checkout was not found.",
        "fr": "Ce paiement est introuvable.",
        "it": "Questo pagamento non è stato trovato.",
    },
    "error.checkout_temporarily_unavailable": {
        "de": "Der Stand des Bezahlvorgangs ist gerade nicht verfügbar. Bitte versuchen Sie es später noch einmal.",
        "en": "Checkout status is temporarily unavailable.",
        "fr": "L'état du paiement est momentanément indisponible. Veuillez réessayer plus tard.",
        "it": "Lo stato del pagamento non è al momento disponibile. Riprovi più tardi.",
    },
    "error.billing_projection_temporarily_unavailable": {
        "de": "Die Abrechnungsdaten sind gerade nicht verfügbar. Bitte versuchen Sie es später noch einmal.",
        "en": "Billing details are temporarily unavailable.",
        "fr": "Les détails de facturation sont momentanément indisponibles. Veuillez réessayer plus tard.",
        "it": "I dettagli di fatturazione non sono al momento disponibili. Riprovi più tardi.",
    },
    "error.allowance_projection_temporarily_unavailable": {
        "de": "Die Angaben zum Kontingent sind gerade nicht verfügbar. Bitte versuchen Sie es später noch einmal.",
        "en": "Allowance details are temporarily unavailable.",
        "fr": "Les détails du quota sont momentanément indisponibles. Veuillez réessayer plus tard.",
        "it": "I dettagli della quota non sono al momento disponibili. Riprovi più tardi.",
    },
}
