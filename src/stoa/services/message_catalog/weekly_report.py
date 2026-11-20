"""The weekly report STOA writes itself when the model gives none (#450).

`report_service.build_deterministic_report_fallback` writes the whole report
from the week's numbers, in the language the parent stored, as the model is
asked to. Read by a parent about their child, so German says `Sie`. `{week}`
is `email.weekly_report.week_range`, `{student}` the child's name or
`email.weekly_report.student_fallback`.
"""

TEXT: dict[str, dict[str, str]] = {
    # ── summary ──────────────────────────────────────────────────────────
    "weekly_report.summary.no_activity": {
        "de": "Für {student} wurde diese Woche ({week}) keine Lernaktivität erfasst.",
        "en": "No learning activity was recorded for {student} this week ({week}).",
        "fr": "Aucune activité d'apprentissage n'a été enregistrée pour {student} cette semaine ({week}).",
        "it": "Questa settimana ({week}) non è stata registrata nessuna attività di studio per {student}.",
    },
    "weekly_report.summary.activity": {
        "de": "Diese Woche ({week}) hat {student} {questions} Frage(n) gestellt, {lessons} Übungslektion(en) abgeschlossen und {mistakes} Fehler notiert.",
        "en": "This week ({week}), {student} asked {questions} question(s), completed {lessons} practice lesson(s) and logged {mistakes} mistake(s).",
        "fr": "Cette semaine ({week}), {student} a posé {questions} question(s), terminé {lessons} leçon(s) d'exercices et noté {mistakes} erreur(s).",
        "it": "Questa settimana ({week}) {student} ha fatto {questions} domanda/e, completato {lessons} lezione/i di esercizio e annotato {mistakes} errore/i.",
    },
    # Exercises answered right for the first time this week, none of them
    # after asking the AI: nothing about the AI is said (#450).
    "weekly_report.summary.solved_on_own": {
        "de": "{student} hat {on_own} neue Aufgabe(n) selbst gelöst.",
        "en": "{student} solved {on_own} new exercise(s) on their own.",
        "fr": "{student} a résolu seul(e) {on_own} nouvel(s) exercice(s).",
        "it": "{student} ha risolto da solo/a {on_own} nuovo/i esercizio/i.",
    },
    "weekly_report.summary.solved_split": {
        "de": "Von {total} neu gelösten Aufgabe(n) hat {student} {on_own} selbst gelöst und {with_ai} mit Hilfe der KI.",
        "en": "Of {total} newly solved exercise(s), {student} solved {on_own} on their own and {with_ai} with help from the AI.",
        "fr": "Sur {total} exercice(s) résolu(s) pour la première fois, {student} en a résolu {on_own} seul(e) et {with_ai} avec l'aide de l'IA.",
        "it": "Su {total} esercizio/i risolto/i per la prima volta, {student} ne ha risolti {on_own} da solo/a e {with_ai} con l'aiuto dell'IA.",
    },
    "weekly_report.summary.stars_lit": {
        "de": "Auf der Sternkarte leuchten {count} neue Stern(e).",
        "en": "{count} new star(s) lit up on the star map.",
        "fr": "{count} nouvelle(s) étoile(s) se sont allumée(s) sur la carte des étoiles.",
        "it": "Sulla mappa delle stelle si sono accese {count} nuova/e stella/e.",
    },
    # The stars of `stars_lit` whose right answers came mostly after asking
    # the AI, by name.
    "weekly_report.summary.stars_mostly_with_ai": {
        "de": "Vor allem mit Hilfe der KI: {stars}.",
        "en": "Lit mostly with help from the AI: {stars}.",
        "fr": "Allumée(s) surtout avec l'aide de l'IA : {stars}.",
        "it": "Accesa/e soprattutto con l'aiuto dell'IA: {stars}.",
    },
    # ── strengths ────────────────────────────────────────────────────────
    "weekly_report.strength.none": {
        "de": "Aus dieser Woche wurden keine besonderen Stärken erfasst.",
        "en": "No specific strengths were recorded from this week's activity.",
        "fr": "Aucun point fort particulier n'a été relevé cette semaine.",
        "it": "Questa settimana non sono stati rilevati punti di forza particolari.",
    },
    "weekly_report.strength.questions": {
        "de": "Diese Woche wurden Fragen gestellt und bearbeitet.",
        "en": "Questions were asked and worked through this week.",
        "fr": "Des questions ont été posées et traitées cette semaine.",
        "it": "Questa settimana sono state fatte e approfondite delle domande.",
    },
    "weekly_report.strength.practice": {
        "de": "Diese Woche wurden Übungslektionen abgeschlossen.",
        "en": "Practice lessons were completed this week.",
        "fr": "Des leçons d'exercices ont été terminées cette semaine.",
        "it": "Questa settimana sono state completate delle lezioni di esercizio.",
    },
    "weekly_report.strength.support": {
        "de": "Bei Bedarf wurde zusätzliche Hilfe angefragt.",
        "en": "Support was requested when additional help was needed.",
        "fr": "De l'aide a été demandée quand elle était nécessaire.",
        "it": "È stato chiesto aiuto quando serviva.",
    },
    "weekly_report.strength.activity": {
        "de": "Diese Woche wurde Lernaktivität erfasst.",
        "en": "Learning activity was recorded this week.",
        "fr": "Une activité d'apprentissage a été enregistrée cette semaine.",
        "it": "Questa settimana è stata registrata attività di studio.",
    },
    # ── topics, recommendations, teacher note ────────────────────────────
    "weekly_report.weak_topic.note": {
        "de": "Diese Woche {count}-mal aufgefallen.",
        "en": "Seen {count} time(s) this week.",
        "fr": "Relevé {count} fois cette semaine.",
        "it": "Emerso {count} volta/e questa settimana.",
    },
    "weekly_report.recommendation.start_practising": {
        "de": "Ermutigen Sie {student} vor dem nächsten Wochenbericht zu einer kurzen Übungseinheit.",
        "en": "Encourage {student} to do one short practice session before the next weekly report.",
        "fr": "Encouragez {student} à faire une courte séance d'exercices avant le prochain rapport hebdomadaire.",
        "it": "Incoraggi {student} a fare una breve sessione di esercizi prima del prossimo rapporto settimanale.",
    },
    "weekly_report.recommendation.review_topics": {
        "de": "In der nächsten Übungseinheit {topics} wiederholen.",
        "en": "Review {topics} in the next practice session.",
        "fr": "Revoir {topics} lors de la prochaine séance d'exercices.",
        "it": "Ripassare {topics} nella prossima sessione di esercizi.",
    },
    # The stars lit mostly after asking the AI, to be tried once more alone.
    "weekly_report.recommendation.retry_without_ai": {
        "de": "Ermutigen Sie {student}, {stars} noch einmal ohne KI zu üben.",
        "en": "Encourage {student} to practise {stars} again without asking the AI.",
        "fr": "Encouragez {student} à refaire {stars} sans demander à l'IA.",
        "it": "Incoraggi {student} a esercitarsi di nuovo su {stars} senza chiedere all'IA.",
    },
    "weekly_report.recommendation.teacher_follow_up": {
        "de": "Prüfen Sie, ob eine Rückmeldung der Lehrperson offen ist.",
        "en": "Check whether any teacher follow-up needs attention.",
        "fr": "Vérifiez si un suivi de l'enseignant attend une réponse.",
        "it": "Verifichi se c'è un riscontro dell'insegnante da seguire.",
    },
    "weekly_report.recommendation.schedule_practice": {
        "de": "Planen Sie eine kurze Übungslektion ein, um dranzubleiben.",
        "en": "Schedule one short practice lesson to keep momentum.",
        "fr": "Prévoyez une courte leçon d'exercices pour garder le rythme.",
        "it": "Pianifichi una breve lezione di esercizio per mantenere il ritmo.",
    },
    "weekly_report.recommendation.continue": {
        "de": "Mit der nächsten geplanten Übung weitermachen.",
        "en": "Continue with the next planned practice activity.",
        "fr": "Continuer avec le prochain exercice prévu.",
        "it": "Proseguire con il prossimo esercizio previsto.",
    },
    "weekly_report.teacher_note": {
        "de": "Diese Woche wurde Hilfe von einer Lehrperson angefragt; schauen Sie, ob eine Rückmeldung des Lehrteams vorliegt.",
        "en": "Teacher help was requested this week; review any follow-up from the teacher team.",
        "fr": "De l'aide d'un enseignant a été demandée cette semaine ; consultez le suivi de l'équipe enseignante.",
        "it": "Questa settimana è stato chiesto l'aiuto di un insegnante; controlli l'eventuale riscontro del team di insegnanti.",
    },
}
