"""Why the practice automation proposes, refuses or did something (#495).

The automation (`adaptive_learning_service`) sends each reason as a code a
client translates: a candidate's `rationaleCode`, a refusal's `refusalCode`
and an execution result's `reasonCode`. The English is the sentence it sent
before it carried codes, and is still sent beside the code. Teachers read these,
addressed formally.
"""

TEXT: dict[str, dict[str, str]] = {
    # ── why a candidate is proposed (`rationaleCode`, its candidate type) ──
    "assignment_automation.rationale.remediation_topic": {
        "de": "Die letzten Lernspuren zeigen dieses Thema als nächstes zum Aufarbeiten.",
        "en": "Recent learning evidence points to this topic as the next reviewed remediation area.",
        "fr": "Les derniers résultats désignent ce thème comme le prochain à retravailler.",
        "it": "I risultati recenti indicano questo argomento come il prossimo da recuperare.",
    },
    "assignment_automation.rationale.curriculum_exercise": {
        "de": "Zu diesem schwachen Thema gibt es eine geprüfte Übung aus dem Lehrplan.",
        "en": "A reviewed curriculum exercise is available for this weak topic.",
        "fr": "Un exercice vérifié du programme existe pour ce thème fragile.",
        "it": "Per questo argomento debole c’è un esercizio verificato del programma.",
    },
    "assignment_automation.rationale.reviewed_ai_draft": {
        "de": "Eine von einer Lehrperson geprüfte KI-Übung passt zu diesem Lernbedarf.",
        "en": "A teacher-reviewed AI practice draft matches this learning need.",
        "fr": "Un exercice IA vérifié par un enseignant correspond à ce besoin.",
        "it": "Un esercizio IA verificato da un insegnante corrisponde a questo bisogno.",
    },
    "assignment_automation.rationale.continuation_lesson": {
        "de": "Eine kurze geprüfte Übung hält das Gelernte frisch.",
        "en": "Continue with one short reviewed practice item to keep learning memory fresh.",
        "fr": "Un court exercice vérifié garde les acquis frais.",
        "it": "Un breve esercizio verificato mantiene fresco quanto appreso.",
    },
    # ── why a candidate is not proposed or not assigned (`refusalCode`) ──
    "assignment_automation.refusal.automation_off": {
        "de": "Die Automatisierung ist für diese Regel ausgeschaltet.",
        "en": "Automation is disabled for this policy.",
        "fr": "L’automatisation est désactivée pour cette règle.",
        "it": "L’automazione è disattivata per questa regola.",
    },
    "assignment_automation.refusal.policy_paused": {
        "de": "Die Regel ist pausiert.",
        "en": "Policy is paused.",
        "fr": "La règle est en pause.",
        "it": "La regola è in pausa.",
    },
    "assignment_automation.refusal.student_out_of_scope": {
        "de": "Diese Schülerin oder dieser Schüler gehört nicht zur Regel.",
        "en": "Candidate student is outside policy scope.",
        "fr": "Cet élève n’entre pas dans le champ de la règle.",
        "it": "Questo allievo non rientra nella regola.",
    },
    "assignment_automation.refusal.source_type_not_allowed": {
        "de": "Diese Art von Übung ist in der Regel nicht vorgesehen.",
        "en": "Candidate source type is outside policy scope.",
        "fr": "Ce type d’exercice n’est pas prévu par la règle.",
        "it": "Questo tipo di esercizio non è previsto dalla regola.",
    },
    "assignment_automation.refusal.subject_out_of_scope": {
        "de": "Das Fach gehört nicht zur Regel.",
        "en": "Candidate subject is outside policy scope.",
        "fr": "La branche n’entre pas dans le champ de la règle.",
        "it": "La materia non rientra nella regola.",
    },
    "assignment_automation.refusal.topic_out_of_scope": {
        "de": "Das Thema gehört nicht zur Regel.",
        "en": "Candidate topic is outside policy scope.",
        "fr": "Le thème n’entre pas dans le champ de la règle.",
        "it": "L’argomento non rientra nella regola.",
    },
    "assignment_automation.refusal.low_confidence": {
        "de": "Die Empfehlung ist zu unsicher.",
        "en": "Candidate confidence is below policy threshold.",
        "fr": "La recommandation n’est pas assez sûre.",
        "it": "La raccomandazione non è abbastanza sicura.",
    },
    "assignment_automation.refusal.stale_candidate": {
        "de": "Die Lernspuren dazu sind zu alt.",
        "en": "Candidate evidence is outside the policy freshness window.",
        "fr": "Les résultats sur lesquels elle repose sont trop anciens.",
        "it": "I risultati su cui si basa sono troppo vecchi.",
    },
    "assignment_automation.refusal.duplicate_or_active": {
        "de": "Dazu gibt es schon eine offene, erledigte oder archivierte Aufgabe.",
        "en": "Candidate duplicates active, completed, or archived assignment work.",
        "fr": "Un devoir en cours, terminé ou archivé existe déjà à ce sujet.",
        "it": "Esiste già un compito in corso, completato o archiviato su questo.",
    },
    "assignment_automation.refusal.review_boundary_missing": {
        "de": "Die Empfehlung verlangt keine Prüfung durch eine Lehrperson.",
        "en": "Candidate does not preserve review-required automation boundaries.",
        "fr": "La recommandation ne prévoit pas de vérification par un enseignant.",
        "it": "La raccomandazione non prevede la verifica di un insegnante.",
    },
    "assignment_automation.refusal.max_assignments_reached": {
        "de": "Die Höchstzahl an Aufgaben für diese Schülerin oder diesen Schüler ist erreicht.",
        "en": "Policy maximum selected assignments for this student was reached.",
        "fr": "Le nombre maximal de devoirs pour cet élève est atteint.",
        "it": "È stato raggiunto il numero massimo di compiti per questo allievo.",
    },
    "assignment_automation.refusal.unsupported_assignment_source": {
        "de": "Daraus lässt sich keine Aufgabe erstellen.",
        "en": "Candidate source cannot create a reviewed assignment.",
        "fr": "Impossible d’en faire un devoir.",
        "it": "Non è possibile ricavarne un compito.",
    },
    "assignment_automation.refusal.source_not_assignable": {
        "de": "Diese Übung kann nicht mehr zugewiesen werden.",
        "en": "This exercise can no longer be assigned.",
        "fr": "Cet exercice ne peut plus être attribué.",
        "it": "Questo esercizio non può più essere assegnato.",
    },
    # ── what became of an approved candidate (`reasonCode`) ──
    "assignment_automation.result.created": {
        "de": "Die Aufgabe wurde erstellt.",
        "en": "Reviewed assignment created from approved automation batch.",
        "fr": "Le devoir a été créé.",
        "it": "Il compito è stato creato.",
    },
    "assignment_automation.result.not_approved": {
        "de": "Nicht ausgewählt, daher nicht zugewiesen.",
        "en": "Candidate was not approved for execution.",
        "fr": "Non sélectionné, donc pas attribué.",
        "it": "Non selezionato, quindi non assegnato.",
    },
    "assignment_automation.result.already_created": {
        "de": "Diese Aufgabe wurde bereits erstellt.",
        "en": "Automation key already created an assignment.",
        "fr": "Ce devoir a déjà été créé.",
        "it": "Questo compito è già stato creato.",
    },
    "assignment_automation.result.source_has_history": {
        "de": "Diese Übung wurde dieser Schülerin oder diesem Schüler schon einmal zugewiesen.",
        "en": "Source already has assignment history for this student.",
        "fr": "Cet exercice a déjà été attribué à cet élève.",
        "it": "Questo esercizio è già stato assegnato a questo allievo.",
    },
    "assignment_automation.result.refused": {
        "de": "Nicht zugewiesen; der Grund steht dabei.",
        "en": "Candidate was refused.",
        "fr": "Non attribué ; la raison est indiquée.",
        "it": "Non assegnato; il motivo è indicato.",
    },
    "assignment_automation.result.failed": {
        "de": "Die Aufgabe konnte nicht erstellt werden. Bitte versuchen Sie es später erneut.",
        "en": "The assignment could not be created. Please try again later.",
        "fr": "Le devoir n’a pas pu être créé. Veuillez réessayer plus tard.",
        "it": "Non è stato possibile creare il compito. Riprovi più tardi.",
    },
}
