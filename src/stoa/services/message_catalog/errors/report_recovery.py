"""Why report recovery refused (`stoa.services.report_recovery_errors`).

Every reader is an administrator in the console, so the copy is impersonal, as
the console's own copy is. A job's target result renders these too, from the
code and params it stores.
"""

TEXT: dict[str, dict[str, str]] = {
    # ── One report ───────────────────────────────────────────────────────────
    "error.report_delivery_not_failed": {
        "de": "Die Zustellung dieses Berichts ist nicht fehlgeschlagen. Es gibt nichts erneut zu senden.",
        "en": "This report's delivery has not failed, so there is nothing to resend.",
        "fr": "L'envoi de ce rapport n'a pas échoué : il n'y a rien à renvoyer.",
        "it": "L'invio di questo rapporto non è fallito: non c'è nulla da reinviare.",
    },
    "error.report_html_artifact_missing": {
        "de": "Zu diesem Bericht ist keine HTML-Fassung gespeichert. Er kann erst nach einer Reparatur erneut gesendet werden.",
        "en": "No HTML version of this report is stored. It can be resent only after it is repaired.",
        "fr": "Aucune version HTML de ce rapport n'est enregistrée. Il ne pourra être renvoyé qu'après réparation.",
        "it": "Non è salvata alcuna versione HTML di questo rapporto. Potrà essere reinviato solo dopo una riparazione.",
    },
    "error.report_recipient_unlinked": {
        "de": "Der Elternteil ist nicht mehr mit diesem Kind verbunden. Der Bericht wird nicht erneut gesendet.",
        "en": "The parent is no longer linked to this student, so the report is not resent.",
        "fr": "Le parent n'est plus lié à cet élève : le rapport n'est pas renvoyé.",
        "it": "Il genitore non è più collegato a questo allievo: il rapporto non viene reinviato.",
    },
    "error.report_recipient_unsubscribed": {
        "de": "Der Elternteil hat die Wochenberichte per E-Mail abbestellt. Der Bericht wird nicht erneut gesendet.",
        "en": "The parent unsubscribed from weekly report emails, so the report is not resent.",
        "fr": "Le parent s'est désabonné des rapports hebdomadaires par e-mail : le rapport n'est pas renvoyé.",
        "it": "Il genitore ha disattivato i rapporti settimanali via e-mail: il rapporto non viene reinviato.",
    },
    "error.report_recipient_email_missing": {
        "de": "Im Profil des Elternteils ist keine E-Mail-Adresse hinterlegt. Der Bericht kann nicht erneut gesendet werden.",
        "en": "The parent's profile has no email address, so the report cannot be resent.",
        "fr": "Le profil du parent n'a pas d'adresse e-mail : le rapport ne peut pas être renvoyé.",
        "it": "Il profilo del genitore non ha un indirizzo e-mail: il rapporto non può essere reinviato.",
    },
    "error.report_resend_failed": {
        "de": "Der Bericht konnte nicht erneut gesendet werden. Er bleibt als fehlgeschlagen markiert und kann später nochmals gesendet werden.",
        "en": "The report could not be resent. It stays marked as failed and can be resent later.",
        "fr": "Le rapport n'a pas pu être renvoyé. Il reste marqué comme en échec et pourra être renvoyé plus tard.",
        "it": "Non è stato possibile reinviare il rapporto. Resta segnato come fallito e potrà essere reinviato più tardi.",
    },
    "error.report_generation_not_failed": {
        "de": "Die Erstellung dieses Berichts ist nicht fehlgeschlagen. Es gibt nichts erneut zu versuchen.",
        "en": "This report's generation has not failed, so there is nothing to retry.",
        "fr": "La génération de ce rapport n'a pas échoué : il n'y a rien à relancer.",
        "it": "La generazione di questo rapporto non è fallita: non c'è nulla da ritentare.",
    },
    "error.report_generation_retry_in_progress": {
        "de": "Für diesen Bericht läuft bereits ein neuer Erstellungsversuch, oder er ist nicht mehr fehlgeschlagen.",
        "en": "A generation retry for this report is already running, or the report is no longer failed.",
        "fr": "Une nouvelle génération de ce rapport est déjà en cours, ou le rapport n'est plus en échec.",
        "it": "È già in corso un nuovo tentativo di generazione di questo rapporto, oppure il rapporto non è più fallito.",
    },
    "error.report_generation_retry_failed": {
        "de": "Der Bericht konnte erneut nicht erstellt werden. Er bleibt als fehlgeschlagen markiert und kann später nochmals versucht werden.",
        "en": "The report could not be generated again. It stays marked as failed and can be retried later.",
        "fr": "Le rapport n'a de nouveau pas pu être généré. Il reste marqué comme en échec et pourra être relancé plus tard.",
        "it": "Non è stato di nuovo possibile generare il rapporto. Resta segnato come fallito e potrà essere ritentato più tardi.",
    },
    # ── A recovery job ───────────────────────────────────────────────────────
    "error.recovery_reason_required": {
        "de": "Bitte einen Grund für die Wiederherstellung angeben.",
        "en": "Give a reason for the recovery.",
        "fr": "Indiquez un motif pour la récupération.",
        "it": "Indica un motivo per il recupero.",
    },
    "error.recovery_status_filter_unsupported": {
        "de": "Dieser Auftrag stellt nur Berichte im Status {required_status} wieder her.",
        "en": "This job recovers only reports with the status {required_status}.",
        "fr": "Cette tâche ne récupère que les rapports au statut {required_status}.",
        "it": "Questa attività recupera solo i rapporti con lo stato {required_status}.",
    },
    "error.resume_result_filter_required": {
        "de": "Bitte mindestens ein Ergebnis wählen, dessen Ziele fortgesetzt werden sollen.",
        "en": "Choose at least one result whose targets should be resumed.",
        "fr": "Choisissez au moins un résultat dont les cibles doivent être reprises.",
        "it": "Scegli almeno un risultato i cui obiettivi devono essere ripresi.",
    },
    "error.resume_result_filter_unsupported": {
        "de": "Ziele mit dem Ergebnis {result_filter} können nicht fortgesetzt werden.",
        "en": "Targets with the result {result_filter} cannot be resumed.",
        "fr": "Les cibles au résultat {result_filter} ne peuvent pas être reprises.",
        "it": "Gli obiettivi con il risultato {result_filter} non possono essere ripresi.",
    },
    "error.recovery_preview_stale": {
        "de": "Seit der Vorschau haben sich die betroffenen Berichte geändert. Bitte eine neue Vorschau erstellen.",
        "en": "The affected reports changed since the preview. Create a new preview.",
        "fr": "Les rapports concernés ont changé depuis l'aperçu. Créez un nouvel aperçu.",
        "it": "I rapporti interessati sono cambiati dall'anteprima. Crea una nuova anteprima.",
    },
    "error.recovery_job_no_eligible_targets": {
        "de": "Kein Bericht in dieser Auswahl kann wiederhergestellt werden. Es wurde kein Auftrag angelegt.",
        "en": "No report in this selection can be recovered, so no job was created.",
        "fr": "Aucun rapport de cette sélection ne peut être récupéré : aucune tâche n'a été créée.",
        "it": "Nessun rapporto di questa selezione può essere recuperato: non è stata creata alcuna attività.",
    },
    "error.recovery_job_not_found": {
        "de": "Dieser Wiederherstellungsauftrag wurde nicht gefunden.",
        "en": "This recovery job was not found.",
        "fr": "Cette tâche de récupération est introuvable.",
        "it": "Questa attività di recupero non è stata trovata.",
    },
    "error.recovery_job_already_terminal": {
        "de": "Dieser Wiederherstellungsauftrag ist bereits abgeschlossen.",
        "en": "This recovery job has already finished.",
        "fr": "Cette tâche de récupération est déjà terminée.",
        "it": "Questa attività di recupero è già terminata.",
    },
    "error.recovery_job_not_cancellable": {
        "de": "Dieser Wiederherstellungsauftrag kann nicht mehr abgebrochen werden.",
        "en": "This recovery job can no longer be cancelled.",
        "fr": "Cette tâche de récupération ne peut plus être annulée.",
        "it": "Questa attività di recupero non può più essere annullata.",
    },
    "error.source_recovery_job_not_terminal": {
        "de": "Ein Auftrag kann erst fortgesetzt werden, wenn er beendet ist.",
        "en": "A job can be resumed only once it has finished.",
        "fr": "Une tâche ne peut être reprise qu'une fois terminée.",
        "it": "Un'attività può essere ripresa solo quando è terminata.",
    },
    "error.source_recovery_job_incomplete": {
        "de": "Der Datensatz dieses Auftrags ist unvollständig und muss repariert werden, bevor er fortgesetzt werden kann.",
        "en": "This job's record is incomplete and needs repair before it can be resumed.",
        "fr": "L'enregistrement de cette tâche est incomplet et doit être réparé avant de pouvoir la reprendre.",
        "it": "Il record di questa attività è incompleto e va riparato prima di poterla riprendere.",
    },
    "error.recovery_job_type_not_resumable": {
        "de": "Aufträge dieser Art können nicht fortgesetzt werden.",
        "en": "Jobs of this type cannot be resumed.",
        "fr": "Les tâches de ce type ne peuvent pas être reprises.",
        "it": "Le attività di questo tipo non possono essere riprese.",
    },
    "error.recovery_job_record_incomplete": {
        "de": "Der Datensatz dieses Wiederherstellungsauftrags ist unvollständig und muss repariert werden.",
        "en": "This recovery job's record is incomplete and needs repair.",
        "fr": "L'enregistrement de cette tâche de récupération est incomplet et doit être réparé.",
        "it": "Il record di questa attività di recupero è incompleto e va riparato.",
    },
    "error.recovery_page_incomplete": {
        "de": "Gespeicherte Wiederherstellungsdaten sind unvollständig. Die Auswahl kann erst nach einer Reparatur gelesen werden.",
        "en": "Stored recovery records are incomplete. The selection can be read only after they are repaired.",
        "fr": "Des données de récupération enregistrées sont incomplètes. La sélection ne pourra être lue qu'après réparation.",
        "it": "Alcuni dati di recupero salvati sono incompleti. La selezione potrà essere letta solo dopo una riparazione.",
    },
    # ── Recorded on a job's target result ────────────────────────────────────
    "error.report_record_incomplete": {
        "de": "Der Datensatz dieses Berichts ist unvollständig. Er wurde übersprungen.",
        "en": "This report's record is incomplete, so it was skipped.",
        "fr": "L'enregistrement de ce rapport est incomplet : il a été ignoré.",
        "it": "Il record di questo rapporto è incompleto: è stato saltato.",
    },
    "error.report_no_longer_eligible": {
        "de": "Dieser Bericht kommt nicht mehr für die Wiederherstellung infrage. Er wurde übersprungen.",
        "en": "This report no longer qualifies for recovery, so it was skipped.",
        "fr": "Ce rapport ne remplit plus les conditions de récupération : il a été ignoré.",
        "it": "Questo rapporto non è più idoneo al recupero: è stato saltato.",
    },
    "error.recovery_target_cancelled": {
        "de": "Der Auftrag wurde abgebrochen, bevor dieser Bericht an der Reihe war.",
        "en": "The job was cancelled before this report was attempted.",
        "fr": "La tâche a été annulée avant que ce rapport ne soit traité.",
        "it": "L'attività è stata annullata prima che questo rapporto fosse elaborato.",
    },
}
