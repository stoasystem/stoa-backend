"""Why the curriculum console refused a request (`stoa.services.curriculum_errors`).

Every reader is staff, addressed formally. The sentences are the ones the
console already showed for these codes (stoa-frontend `admin.json`,
`curriculum.errors.code`), so the console and the API say the same thing.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.curriculum_capability_required": {
        "de": "Ihrem Konto fehlt die Lehrplan-Berechtigung für diese Aktion.",
        "en": "Your account does not have the curriculum permission this action needs.",
        "fr": "Votre compte n’a pas l’autorisation de programme requise pour cette action.",
        "it": "Il tuo account non ha l’autorizzazione al programma necessaria per questa azione.",
    },
    "error.curriculum_version_not_found": {
        "de": "Diese Version existiert nicht mehr. Laden Sie die Arbeitsliste neu.",
        "en": "This version no longer exists. Reload the worklist.",
        "fr": "Cette version n’existe plus. Rechargez la liste de travail.",
        "it": "Questa versione non esiste più. Ricarica la lista di lavoro.",
    },
    "error.curriculum_unit_not_found": {
        "de": "Diese Lehrplaneinheit existiert nicht mehr. Laden Sie die Arbeitsliste neu.",
        "en": "This curriculum unit no longer exists. Reload the worklist.",
        "fr": "Cette unité du programme n’existe plus. Rechargez la liste de travail.",
        "it": "Questa unità del programma non esiste più. Ricarica la lista di lavoro.",
    },
    "error.validation_failed": {
        "de": "Der Inhalt hat die Validierung nicht bestanden. Starten Sie die Validierung, um die betroffenen Felder zu sehen.",
        "en": "The content did not pass validation. Run the validation to see which fields are affected.",
        "fr": "Le contenu n’a pas passé la validation. Lancez la validation pour voir les champs concernés.",
        "it": "Il contenuto non ha superato la validazione. Avvia la validazione per vedere i campi interessati.",
    },
    "error.draft_not_editable": {
        "de": "Diese Version kann nicht mehr bearbeitet werden. Legen Sie für Änderungen einen neuen Entwurf an.",
        "en": "This version can no longer be edited. Create a new draft to make changes.",
        "fr": "Cette version ne peut plus être modifiée. Créez un nouveau brouillon pour apporter des changements.",
        "it": "Questa versione non può più essere modificata. Crea una nuova bozza per apportare modifiche.",
    },
    "error.not_reviewable": {
        "de": "Diese Version kann in ihrem aktuellen Zustand nicht zur Prüfung eingereicht werden.",
        "en": "This version cannot be submitted for review in its current state.",
        "fr": "Cette version ne peut pas être soumise à la relecture dans son état actuel.",
        "it": "Questa versione non può essere inviata in revisione nel suo stato attuale.",
    },
    "error.not_in_review": {
        "de": "Diese Version ist nicht in Prüfung und kann daher weder freigegeben noch zurückgewiesen werden.",
        "en": "This version is not in review, so it cannot be approved or sent back.",
        "fr": "Cette version n’est pas en relecture : elle ne peut être ni approuvée ni renvoyée.",
        "it": "Questa versione non è in revisione, quindi non può essere approvata né rimandata indietro.",
    },
    "error.not_approved": {
        "de": "Nur eine freigegebene Version kann veröffentlicht werden.",
        "en": "Only an approved version can be published.",
        "fr": "Seule une version approuvée peut être publiée.",
        "it": "Solo una versione approvata può essere pubblicata.",
    },
    "error.rollback_target_not_publishable": {
        "de": "Diese Version kann nicht wiederhergestellt werden.",
        "en": "This version cannot be restored.",
        "fr": "Cette version ne peut pas être restaurée.",
        "it": "Questa versione non può essere ripristinata.",
    },
    "error.stale_pointer": {
        "de": "In der Zwischenzeit wurde eine andere Version veröffentlicht. Laden Sie die Arbeitsliste neu und prüfen Sie die aktuelle Version.",
        "en": "Someone else published a different version in the meantime. Reload the worklist and check the current version.",
        "fr": "Une autre version a été publiée entre-temps. Rechargez la liste de travail et vérifiez la version actuelle.",
        "it": "Nel frattempo è stata pubblicata un’altra versione. Ricarica la lista di lavoro e controlla la versione attuale.",
    },
    "error.exercise_id_conflict": {
        "de": "Eine Übungs-ID dieser Version gehört bereits zu einer anderen Lektion. Geben Sie der Übung eine eigene ID.",
        "en": "An exercise ID in this version already belongs to another lesson. Give the exercise its own ID.",
        "fr": "Un identifiant d’exercice de cette version appartient déjà à une autre leçon. Donnez à l’exercice son propre identifiant.",
        "it": "Un ID di esercizio di questa versione appartiene già a un’altra lezione. Assegna all’esercizio un ID proprio.",
    },
    "error.active_assignments_block_archive": {
        "de": "Diese Lektion ist noch Lernenden zugewiesen und kann noch nicht archiviert werden.",
        "en": "This lesson is still assigned to students and cannot be archived yet.",
        "fr": "Cette leçon est encore attribuée à des élèves et ne peut pas encore être archivée.",
        "it": "Questa lezione è ancora assegnata ad allievi e non può ancora essere archiviata.",
    },
    "error.migration_confirmation_mismatch": {
        "de": "Das Bestätigungstoken passt nicht zu diesem Probelauf. Starten Sie den Probelauf erneut und verwenden Sie dessen Token.",
        "en": "The confirmation token does not match this dry run. Run the dry run again and use its token.",
        "fr": "Le jeton de confirmation ne correspond pas à cet essai. Relancez l’essai et utilisez son jeton.",
        "it": "Il token di conferma non corrisponde a questa prova. Ripeti la prova e usa il suo token.",
    },
    "error.migration_not_ready": {
        "de": "Der Probelauf hat Konflikte oder Fehler gefunden. Beheben Sie diese, bevor Sie die Migration anwenden.",
        "en": "The dry run found conflicts or errors. Resolve them before applying the migration.",
        "fr": "L’essai a trouvé des conflits ou des erreurs. Corrigez-les avant d’appliquer la migration.",
        "it": "La prova ha trovato conflitti o errori. Risolvili prima di applicare la migrazione.",
    },
    "error.migration_not_found": {
        "de": "Diese Migration wurde nicht gefunden. Prüfen Sie die Migrations-ID.",
        "en": "This migration was not found. Check the migration ID.",
        "fr": "Cette migration est introuvable. Vérifiez l’identifiant de migration.",
        "it": "Questa migrazione non è stata trovata. Controlla l’ID della migrazione.",
    },
    "error.invalid_manifest": {
        "de": "Das Manifest ist unvollständig oder ungültig. Prüfen Sie die Lektionen und ihre IDs.",
        "en": "The manifest is incomplete or invalid. Check the lessons and their IDs.",
        "fr": "Le manifeste est incomplet ou non valide. Vérifiez les leçons et leurs identifiants.",
        "it": "Il manifesto è incompleto o non valido. Controlla le lezioni e i loro ID.",
    },
}
