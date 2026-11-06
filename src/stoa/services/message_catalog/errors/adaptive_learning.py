"""Assignment and automation refusals (`stoa.services.adaptive_learning_errors.AdaptiveLearningErrorCode`).

Read by teachers, admins and the student working an assignment: `du`,
`vous`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.question_history_unavailable": {
        "de": "Der Fragenverlauf kann gerade nicht geladen werden. Versuche es gleich noch einmal.",
        "en": "The question history cannot be loaded right now. Try again shortly.",
        "fr": "L'historique des questions ne peut pas être chargé pour le moment. Réessayez dans un instant.",
        "it": "Al momento non è possibile caricare la cronologia delle domande. Riprova tra poco.",
    },
    "error.assignment_not_found": {
        "de": "Diese Aufgabe wurde nicht gefunden.",
        "en": "This assignment was not found.",
        "fr": "Ce devoir est introuvable.",
        "it": "Questo compito non è stato trovato.",
    },
    "error.assignment_status_not_creatable": {
        "de": "Eine neue Aufgabe beginnt als Entwurf, als Empfehlung oder als zugewiesen.",
        "en": "A new assignment starts as a draft, a recommendation or assigned.",
        "fr": "Un nouveau devoir commence comme brouillon, recommandation ou devoir attribué.",
        "it": "Un nuovo compito inizia come bozza, come suggerimento o come assegnato.",
    },
    "error.assignment_status_unsupported": {
        "de": "Diesen Aufgabenstatus gibt es nicht.",
        "en": "This assignment status does not exist.",
        "fr": "Ce statut de devoir n'existe pas.",
        "it": "Questo stato del compito non esiste.",
    },
    "error.assignment_action_unsupported": {
        "de": "Diese Aktion ist für eine Aufgabe nicht möglich.",
        "en": "This action is not possible for an assignment.",
        "fr": "Cette action n'est pas possible pour un devoir.",
        "it": "Questa azione non è possibile per un compito.",
    },
    "error.assignment_not_startable": {
        "de": "Diese Aufgabe kann in ihrem jetzigen Zustand nicht begonnen werden.",
        "en": "This assignment cannot be started in its current state.",
        "fr": "Ce devoir ne peut pas être commencé dans son état actuel.",
        "it": "Questo compito non può essere iniziato nel suo stato attuale.",
    },
    "error.assignment_not_completable": {
        "de": "Diese Aufgabe kann in ihrem jetzigen Zustand nicht abgeschlossen werden.",
        "en": "This assignment cannot be completed in its current state.",
        "fr": "Ce devoir ne peut pas être terminé dans son état actuel.",
        "it": "Questo compito non può essere completato nel suo stato attuale.",
    },
    "error.assignment_not_skippable": {
        "de": "Eine abgeschlossene oder archivierte Aufgabe kann nicht übersprungen werden.",
        "en": "A completed or archived assignment cannot be skipped.",
        "fr": "Un devoir terminé ou archivé ne peut pas être passé.",
        "it": "Un compito completato o archiviato non può essere saltato.",
    },
    "error.assignment_source_type_unsupported": {
        "de": "Aus dieser Quelle kann keine Aufgabe erstellt werden.",
        "en": "An assignment cannot be made from this kind of source.",
        "fr": "Un devoir ne peut pas être créé à partir de ce type de source.",
        "it": "Non è possibile creare un compito da questo tipo di fonte.",
    },
    "error.assignment_source_not_found": {
        "de": "Die Übung oder der Entwurf für diese Aufgabe wurde nicht gefunden.",
        "en": "The exercise or draft for this assignment was not found.",
        "fr": "L'exercice ou le brouillon de ce devoir est introuvable.",
        "it": "L'esercizio o la bozza di questo compito non è stato trovato.",
    },
    "error.ai_draft_not_assignable": {
        "de": "Nur ein angenommener Übungsentwurf kann als Aufgabe vergeben werden.",
        "en": "Only an accepted practice exercise draft can be assigned.",
        "fr": "Seul un brouillon d'exercice accepté peut être attribué.",
        "it": "Solo una bozza di esercizio accettata può essere assegnata.",
    },
    "error.draft_of_another_student": {
        "de": "Dieser Entwurf gehört zu einer anderen Schülerin oder einem anderen Schüler.",
        "en": "This draft belongs to another student.",
        "fr": "Ce brouillon appartient à un autre élève.",
        "it": "Questa bozza appartiene a un altro studente.",
    },
    "error.batch_approval_required": {
        "de": "Bestätige die Auswahl, bevor die Aufgaben erstellt werden.",
        "en": "Approve the selection before the assignments are made.",
        "fr": "Approuvez la sélection avant que les devoirs soient créés.",
        "it": "Approva la selezione prima che i compiti vengano creati.",
    },
    "error.batch_candidates_required": {
        "de": "Wähle mindestens einen Vorschlag aus.",
        "en": "Choose at least one candidate.",
        "fr": "Choisissez au moins une proposition.",
        "it": "Scegli almeno una proposta.",
    },
    "error.batch_preview_stale": {
        "de": "Die Vorschau ist nicht mehr aktuell. Lade sie neu.",
        "en": "The preview is out of date. Load it again.",
        "fr": "L'aperçu n'est plus à jour. Rechargez-le.",
        "it": "L'anteprima non è più aggiornata. Ricaricala.",
    },
    "error.candidate_not_in_preview": {
        "de": "Dieser Vorschlag ist in der aktuellen Vorschau nicht ausgewählt.",
        "en": "This candidate is not selected in the current preview.",
        "fr": "Cette proposition n'est pas sélectionnée dans l'aperçu actuel.",
        "it": "Questa proposta non è selezionata nell'anteprima attuale.",
    },
    "error.candidate_preview_mismatch": {
        "de": "Dieser Vorschlag stimmt nicht mit der aktuellen Vorschau überein.",
        "en": "This candidate does not match the current preview.",
        "fr": "Cette proposition ne correspond pas à l'aperçu actuel.",
        "it": "Questa proposta non corrisponde all'anteprima attuale.",
    },
    "error.candidate_status_mismatch": {
        "de": "Der vorgeschlagene Status muss zur Zustellart der Regel passen.",
        "en": "The proposed status must match the policy's delivery mode.",
        "fr": "Le statut proposé doit correspondre au mode de remise de la règle.",
        "it": "Lo stato proposto deve corrispondere alla modalità di consegna della regola.",
    },
    "error.automation_source_type_unsupported": {
        "de": "Diese Quelle kann die Automatisierung nicht verwenden.",
        "en": "Automation cannot use this kind of source.",
        "fr": "L'automatisation ne peut pas utiliser ce type de source.",
        "it": "L'automazione non può usare questo tipo di fonte.",
    },
    "error.automation_source_type_required": {
        "de": "Wähle mindestens eine Quelle für die Automatisierung.",
        "en": "Choose at least one source for automation.",
        "fr": "Choisissez au moins une source pour l'automatisation.",
        "it": "Scegli almeno una fonte per l'automazione.",
    },
    "error.policy_value_unsupported": {
        "de": "Dieser Wert wird in der Regel nicht unterstützt.",
        "en": "This value is not supported in the policy.",
        "fr": "Cette valeur n'est pas prise en charge dans la règle.",
        "it": "Questo valore non è supportato nella regola.",
    },
    "error.policy_value_blank": {
        "de": "Die Werte einer Regel dürfen nicht leer sein.",
        "en": "A policy's values cannot be blank.",
        "fr": "Les valeurs d'une règle ne peuvent pas être vides.",
        "it": "I valori di una regola non possono essere vuoti.",
    },
}
