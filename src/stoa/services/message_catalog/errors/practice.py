"""Practice refusals (`stoa.services.practice_errors.PracticeErrorCode`).

Read by the student practising, addressed as the web client addresses them:
`du`, `tu`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.star_quiz_unknown_star": {
        "de": "Diesen Wissenspunkt gibt es nicht.",
        "en": "There is no such knowledge point.",
        "fr": "Ce point de connaissance n'existe pas.",
        "it": "Questo punto di conoscenza non esiste.",
    },
    "error.star_quiz_already_lit": {
        "de": "Dieser Wissenspunkt leuchtet schon.",
        "en": "This knowledge point is lit already.",
        "fr": "Ce point de connaissance est déjà allumé.",
        "it": "Questo punto di conoscenza è già acceso.",
    },
    "error.star_quiz_cooling_down": {
        "de": "Dieses Quiz kannst du später noch einmal machen.",
        "en": "This quiz can be taken again later.",
        "fr": "Tu pourras refaire ce quiz plus tard.",
        "it": "Potrai rifare questo quiz più tardi.",
    },
    "error.star_quiz_unavailable": {
        "de": "Für dieses Quiz gibt es gerade keine Aufgabe.",
        "en": "This quiz has no exercise to ask right now.",
        "fr": "Ce quiz n'a pas d'exercice à poser pour le moment.",
        "it": "Al momento questo quiz non ha esercizi da proporre.",
    },
    "error.star_quiz_not_found": {
        "de": "Dieses Quiz ist nicht offen.",
        "en": "This quiz is not open.",
        "fr": "Ce quiz n'est pas ouvert.",
        "it": "Questo quiz non è aperto.",
    },
    "error.star_quiz_finished": {
        "de": "Dieses Quiz ist schon vorbei.",
        "en": "This quiz is already over.",
        "fr": "Ce quiz est déjà terminé.",
        "it": "Questo quiz è già finito.",
    },
    "error.star_quiz_expired": {
        "de": "Dieses Quiz ist abgelaufen. Starte ein neues.",
        "en": "This quiz has expired. Start a new one.",
        "fr": "Ce quiz a expiré. Commence-en un nouveau.",
        "it": "Questo quiz è scaduto. Iniziane uno nuovo.",
    },
    "error.star_quiz_out_of_order": {
        "de": "Diese Aufgabe stellt das Quiz gerade nicht.",
        "en": "This is not the exercise the quiz is asking now.",
        "fr": "Ce n'est pas l'exercice que le quiz pose maintenant.",
        "it": "Questo non è l'esercizio che il quiz sta proponendo ora.",
    },
    "error.lesson_quiz_not_found": {
        "de": "Dieses Quiz ist nicht offen.",
        "en": "This quiz is not open.",
        "fr": "Ce quiz n'est pas ouvert.",
        "it": "Questo quiz non è aperto.",
    },
    "error.lesson_quiz_finished": {
        "de": "Dieses Quiz ist schon vorbei.",
        "en": "This quiz is already over.",
        "fr": "Ce quiz est déjà terminé.",
        "it": "Questo quiz è già finito.",
    },
    "error.lesson_quiz_expired": {
        "de": "Dieses Quiz ist abgelaufen. Starte ein neues.",
        "en": "This quiz has expired. Start a new one.",
        "fr": "Ce quiz a expiré. Commence-en un nouveau.",
        "it": "Questo quiz è scaduto. Iniziane uno nuovo.",
    },
    "error.lesson_quiz_unavailable": {
        "de": "Für dieses Quiz gibt es gerade keine Aufgabe.",
        "en": "This quiz has no exercise to ask right now.",
        "fr": "Ce quiz n'a pas d'exercice à poser pour le moment.",
        "it": "Al momento questo quiz non ha esercizi da proporre.",
    },
    "error.lesson_quiz_out_of_order": {
        "de": "Diese Aufgabe stellt das Quiz gerade nicht.",
        "en": "This is not the exercise the quiz is asking now.",
        "fr": "Ce n'est pas l'exercice que le quiz pose maintenant.",
        "it": "Questo non è l'esercizio che il quiz sta proponendo ora.",
    },
    "error.lesson_quiz_credential_invalid": {
        "de": "Mit diesem Quiz-Nachweis kann diese Lektion nicht abgeschlossen werden.",
        "en": "This quiz credential cannot complete this lesson.",
        "fr": "Cette preuve de quiz ne permet pas de terminer cette leçon.",
        "it": "Questa prova del quiz non permette di completare questa lezione.",
    },
    "error.lesson_quiz_credential_expired": {
        "de": "Dieser Quiz-Nachweis ist abgelaufen. Mach das Quiz noch einmal.",
        "en": "This quiz credential has expired. Take the quiz again.",
        "fr": "Cette preuve de quiz a expiré. Refais le quiz.",
        "it": "Questa prova del quiz è scaduta. Rifai il quiz.",
    },
    "error.lesson_exercises_unanswered": {
        "de": (
            "Beantworte zuerst jede Aufgabe dieser Lektion richtig. "
            "Noch offen: {count}."
        ),
        "en": "Answer every exercise of this lesson right before completing it. Still open: {count}.",
        "fr": (
            "Réponds d'abord correctement à chaque exercice de cette leçon. "
            "Encore à faire : {count}."
        ),
        "it": (
            "Prima rispondi correttamente a ogni esercizio di questa lezione. "
            "Ancora da fare: {count}."
        ),
    },
    "error.practice_answer_invalid": {
        "de": "Diese Antwort wird nicht unterstützt oder ist zu lang.",
        "en": "Your answer is not supported or is too large.",
        "fr": "Cette réponse n'est pas prise en charge ou est trop longue.",
        "it": "Questa risposta non è supportata o è troppo lunga.",
    },
    "error.practice_attempt_unavailable": {
        "de": "Deine Antwort konnte nicht gespeichert werden. Versuche es noch einmal.",
        "en": "Your answer could not be recorded. Please try again.",
        "fr": "Ta réponse n'a pas pu être enregistrée. Réessaie.",
        "it": "Non è stato possibile registrare la tua risposta. Riprova.",
    },
    "error.practice_attempt_not_found": {
        "de": "Dieser Lösungsversuch wurde nicht gefunden.",
        "en": "This practice attempt was not found.",
        "fr": "Cette tentative est introuvable.",
        "it": "Questo tentativo non è stato trovato.",
    },
    "error.curriculum_student_required": {
        "de": "Gib an, wessen Lernfortschritt angezeigt werden soll.",
        "en": "Name the student whose progress to show.",
        "fr": "Indique l'élève dont il faut afficher la progression.",
        "it": "Indica lo studente di cui mostrare i progressi.",
    },
    "error.curriculum_lesson_not_found": {
        "de": "Diese Lektion wurde nicht gefunden.",
        "en": "This lesson was not found.",
        "fr": "Cette leçon est introuvable.",
        "it": "Questa lezione non è stata trovata.",
    },
    "error.no_lessons_available": {
        "de": "Hier gibt es noch keine Lektionen.",
        "en": "There are no lessons here yet.",
        "fr": "Il n'y a pas encore de leçons ici.",
        "it": "Qui non ci sono ancora lezioni.",
    },
    "error.subject_unknown": {
        "de": "Dieses Fach gibt es im Lehrplan nicht.",
        "en": "This subject is not in the curriculum.",
        "fr": "Cette matière ne fait pas partie du programme.",
        "it": "Questa materia non fa parte del programma.",
    },
    "error.topic_not_found": {
        "de": "Dieses Thema wurde nicht gefunden.",
        "en": "This topic was not found.",
        "fr": "Ce thème est introuvable.",
        "it": "Questo argomento non è stato trovato.",
    },
    "error.no_topics_found": {
        "de": "Hier gibt es noch keine Themen.",
        "en": "There are no topics here yet.",
        "fr": "Il n'y a pas encore de thèmes ici.",
        "it": "Qui non ci sono ancora argomenti.",
    },
}
