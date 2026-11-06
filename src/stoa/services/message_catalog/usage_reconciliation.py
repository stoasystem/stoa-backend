"""Why a usage counter and the usage ledger agree or not (`usage_ledger_service`, #114).

Shown on the account-operations usage card to administrators and parents, in
the formal register. The English is the `explanation` sentence the summary
sent before it carried `explanationCode`, and is still that field.
"""

TEXT: dict[str, dict[str, str]] = {
    "reconciliation.counter_matches_ledger": {
        "de": "Zähler und Nutzungsprotokoll stimmen für diesen Kontingentzeitraum überein.",
        "en": "Counter and usage ledger match for this quota period.",
        "fr": "Le compteur et le journal d’utilisation concordent pour cette période de quota.",
        "it": "Contatore e registro d’uso coincidono per questo periodo di quota.",
    },
    "reconciliation.no_usage": {
        "de": "Für diese Aktion und diesen Kontingentzeitraum wurde keine Nutzung erfasst.",
        "en": "No usage was recorded for this action and quota period.",
        "fr": "Aucune utilisation n’a été enregistrée pour cette action et cette période de quota.",
        "it": "Nessun utilizzo è stato registrato per questa azione e questo periodo di quota.",
    },
    "reconciliation.ledger_only": {
        "de": "Diese Aktion wird nur im Nutzungsprotokoll erfasst und hat keinen Kontingentzähler.",
        "en": "This support-visible action is tracked only in the ledger and has no quota counter.",
        "fr": "Cette action n’est suivie que dans le journal d’utilisation et n’a pas de compteur de quota.",
        "it": "Questa azione è registrata solo nel registro d’uso e non ha un contatore di quota.",
    },
    "reconciliation.counter_over_limit": {
        "de": "Der Zählerstand {counter} liegt über dem Kontingent {limit}; prüfen Sie die Kontingentdurchsetzung und die letzten Wiederholungen, bevor Sie den Zugang ändern.",
        "en": "Counter value {counter} is above the entitlement limit {limit}; review quota enforcement and recent retries before changing access.",
        "fr": "La valeur du compteur {counter} dépasse la limite du droit d’accès {limit} ; vérifiez l’application du quota et les tentatives récentes avant de modifier l’accès.",
        "it": "Il valore del contatore {counter} supera il limite del diritto d’accesso {limit}; verifica l’applicazione della quota e i tentativi recenti prima di modificare l’accesso.",
    },
    "reconciliation.counter_stale": {
        "de": "Der Zählereintrag scheint für diesen Kontingentzeitraum veraltet zu sein; prüfen Sie das TTL-Verhalten, bevor Sie ihn für Support-Entscheidungen verwenden.",
        "en": "The counter row appears stale for this quota period; verify TTL behavior before using it for support decisions.",
        "fr": "La ligne du compteur semble périmée pour cette période de quota ; vérifiez le comportement du TTL avant de l’utiliser pour des décisions de support.",
        "it": "La riga del contatore sembra scaduta per questo periodo di quota; verifica il comportamento del TTL prima di usarla per decisioni di supporto.",
    },
    "reconciliation.counter_without_ledger": {
        "de": "Der Zähler zeigt {counter} verbraucht, aber es wurden keine passenden Protokolleinträge gefunden.",
        "en": "Counter shows {counter} consumed but no matching ledger events were found.",
        "fr": "Le compteur indique {counter} consommé(s), mais aucun événement correspondant n’a été trouvé dans le journal.",
        "it": "Il contatore indica {counter} consumati, ma non è stato trovato alcun evento corrispondente nel registro.",
    },
    "reconciliation.ledger_without_counter": {
        "de": "Das Nutzungsprotokoll zeigt {ledger} verbraucht, aber es wurde kein passender Zählereintrag gefunden.",
        "en": "Ledger shows {ledger} consumed but no matching counter row was found.",
        "fr": "Le journal indique {ledger} consommé(s), mais aucune ligne de compteur correspondante n’a été trouvée.",
        "it": "Il registro indica {ledger} consumati, ma non è stata trovata alcuna riga del contatore corrispondente.",
    },
    "reconciliation.count_mismatch": {
        "de": "Der Zählerstand {counter} und die Protokollsumme {ledger} stimmen nicht überein.",
        "en": "Counter value {counter} and ledger total {ledger} do not match.",
        "fr": "La valeur du compteur {counter} et le total du journal {ledger} ne concordent pas.",
        "it": "Il valore del contatore {counter} e il totale del registro {ledger} non coincidono.",
    },
}
