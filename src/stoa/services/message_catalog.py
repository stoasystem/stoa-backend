"""Every sentence this backend writes for somebody to read, in four languages.

The client draws its own shell in the language the reader chose, so a sentence
shipped from here in one language lands inside a panel written in another: a
student reading German was told `No teacher was available` under the heading
`Mitteilungen`, and a teacher was shown `Teacher help requested.` glued onto
the front of the student's own German question (#124).

One table, so there is one place to look and one place to add a locale. What
is **not** here, on purpose:

* **Error details** (`HTTPException(detail=...)`). Those are read by clients
  and logs, not by students; they stay in one language throughout the repo.
* **Content**, as opposed to copy: a student's question, the assistant's
  answer, a knowledge-point title. Those are already in whatever language they
  were written in, and `curriculum_translations` handles the titles.
* **Machine states** interpolated into a sentence (`{status}`), which are the
  value a row carries rather than something to translate.

Rows already written are never re-rendered. A stored notification or system
message is a record of what somebody was told, so only new writes come
through here (#124 decided this explicitly; there is no backfill).
"""

from __future__ import annotations

from typing import Any

from stoa.services import locale_service

TEXT: dict[str, dict[str, str]] = {
    # ── notifications ────────────────────────────────────────────────────
    "teacher_takeover.question.title": {
        "de": "Eine Lehrperson ist deiner Frage beigetreten",
        "en": "A teacher joined your question",
        "fr": "Un enseignant a rejoint ta question",
        "it": "Un insegnante si è unito alla tua domanda",
    },
    "teacher_takeover.question.summary": {
        "de": "Eine Lehrperson bearbeitet jetzt deine Frage.",
        "en": "A teacher has started working on your question.",
        "fr": "Un enseignant a commencé à traiter ta question.",
        "it": "Un insegnante ha iniziato a lavorare sulla tua domanda.",
    },
    "teacher_reply.question.title": {
        "de": "Deine Lehrperson hat geantwortet",
        "en": "Your teacher replied",
        "fr": "Ton enseignant a répondu",
        "it": "Il tuo insegnante ha risposto",
    },
    "teacher_reply.question.summary": {
        "de": "Deine Lehrperson hat deiner Frage eine Antwort hinzugefügt.",
        "en": "Your teacher added a reply to your question.",
        "fr": "Ton enseignant a ajouté une réponse à ta question.",
        "it": "Il tuo insegnante ha aggiunto una risposta alla tua domanda.",
    },
    "teacher_help.takeover.title": {
        "de": "Eine Lehrperson ist deiner Unterhaltung beigetreten",
        "en": "A teacher joined your conversation",
        "fr": "Un enseignant a rejoint ta conversation",
        "it": "Un insegnante si è unito alla tua conversazione",
    },
    "teacher_help.takeover.summary": {
        "de": "Eine Lehrperson bearbeitet jetzt deine Anfrage.",
        "en": "A teacher has started working on your request.",
        "fr": "Un enseignant a commencé à traiter ta demande.",
        "it": "Un insegnante ha iniziato a lavorare sulla tua richiesta.",
    },
    "teacher_help.reply.title": {
        "de": "Deine Lehrperson hat geantwortet",
        "en": "Your teacher replied",
        "fr": "Ton enseignant a répondu",
        "it": "Il tuo insegnante ha risposto",
    },
    "teacher_help.reply.summary": {
        "de": "Deine Lehrperson hat in deiner Unterhaltung geantwortet.",
        "en": "Your teacher answered in your conversation.",
        "fr": "Ton enseignant a répondu dans ta conversation.",
        "it": "Il tuo insegnante ha risposto nella tua conversazione.",
    },
    "teacher_help.expired.title": {
        "de": "Es war keine Lehrperson verfügbar",
        "en": "No teacher was available",
        "fr": "Aucun enseignant n'était disponible",
        "it": "Nessun insegnante era disponibile",
    },
    "teacher_help.expired.summary": {
        "de": "Deine Anfrage an eine Lehrperson ist abgelaufen.",
        "en": "Your request for a teacher expired.",
        "fr": "Ta demande d'aide à un enseignant a expiré.",
        "it": "La tua richiesta di aiuto a un insegnante è scaduta.",
    },
    "teacher_help.expired.summary_returned": {
        "de": (
            "Deine Anfrage an eine Lehrperson ist abgelaufen. "
            "Die Lehrpersonen-Hilfe dieser Woche wurde dir zurückgegeben."
        ),
        "en": (
            "Your request for a teacher expired. "
            "This week's teacher help was given back."
        ),
        "fr": (
            "Ta demande d'aide à un enseignant a expiré. "
            "L'aide d'un enseignant de cette semaine t'a été rendue."
        ),
        "it": (
            "La tua richiesta di aiuto a un insegnante è scaduta. "
            "L'aiuto dell'insegnante di questa settimana ti è stato restituito."
        ),
    },
    "moderation.update.title": {
        "de": "Meldung aktualisiert",
        "en": "Moderation case updated",
        "fr": "Signalement mis à jour",
        "it": "Segnalazione aggiornata",
    },
    "moderation.update.summary": {
        "de": "Der Status deiner Meldung ist {status}.",
        "en": "Moderation case status is {status}.",
        "fr": "Le statut de ton signalement est {status}.",
        "it": "Lo stato della tua segnalazione è {status}.",
    },
    "subscription.update.title": {
        "de": "Abo-Anfrage aktualisiert",
        "en": "Subscription request updated",
        "fr": "Demande d'abonnement mise à jour",
        "it": "Richiesta di abbonamento aggiornata",
    },
    "subscription.update.summary": {
        "de": "Der Status der Abo-Anfrage ist {status}.",
        "en": "Subscription request status is {status}.",
        "fr": "Le statut de la demande d'abonnement est {status}.",
        "it": "Lo stato della richiesta di abbonamento è {status}.",
    },
    # ── the system message that opens a teacher help request ─────────────
    "teacher_help.system_message.prefix": {
        "de": "Anfrage an eine Lehrperson gestellt.",
        "en": "Teacher help requested.",
        "fr": "Demande d'aide à un enseignant envoyée.",
        "it": "Richiesta di aiuto a un insegnante inviata.",
    },
    # ── the seed a teacher is shown beside a help request ────────────────
    "assistance.context.with_topics": {
        "de": "Die Schülerin oder der Schüler zeigt Hinweise in {subject} rund um {topics}.",
        "en": "Student has active {subject} evidence around {topics}.",
        "fr": "L'élève montre des indices en {subject} autour de {topics}.",
        "it": "Lo studente mostra indizi in {subject} su {topics}.",
    },
    "assistance.context.without_topics": {
        "de": (
            "Die Schülerin oder der Schüler hat eine offene Anfrage in {subject}, "
            "noch ohne ausreichende Hinweise auf ein Thema."
        ),
        "en": "Student has an active {subject} help request without enough topic evidence yet.",
        "fr": (
            "L'élève a une demande ouverte en {subject}, "
            "sans encore assez d'indices sur un thème."
        ),
        "it": (
            "Lo studente ha una richiesta aperta in {subject}, "
            "ancora senza indizi sufficienti su un argomento."
        ),
    },
    "assistance.focus.after_reply": {
        "de": "Sieh dir die vorherige Antwort an und mach beim offenen Schritt weiter.",
        "en": "Review the previous teacher reply and continue from the student's unresolved step.",
        "fr": "Relis la réponse précédente et reprends à l'étape restée ouverte.",
        "it": "Rileggi la risposta precedente e riprendi dal passaggio rimasto aperto.",
    },
    "assistance.focus.with_topics": {
        "de": "Kläre zuerst das Missverständnis bei {topic}, bevor du die Schritte zeigst.",
        "en": "Clarify the core misconception around {topic} before giving final steps.",
        "fr": "Clarifie d'abord le malentendu sur {topic} avant de donner les étapes.",
        "it": "Chiarisci prima l'equivoco su {topic}, poi mostra i passaggi.",
    },
    "assistance.focus.default": {
        "de": "Stell eine diagnostische Frage und erkläre dann den kleinsten nächsten Schritt.",
        "en": "Ask one diagnostic question, then explain the smallest next step.",
        "fr": "Pose une question de diagnostic, puis explique la plus petite étape suivante.",
        "it": "Fai una domanda diagnostica, poi spiega il passo successivo più piccolo.",
    },
    # ── timeline entries on the student's and the parent's pages ─────────
    "activity.teacher_help_requested": {
        "de": "Anfrage an eine Lehrperson",
        "en": "Teacher help requested",
        "fr": "Aide d'un enseignant demandée",
        "it": "Aiuto di un insegnante richiesto",
    },
    "activity.question_asked": {
        "de": "Frage gestellt",
        "en": "Question asked",
        "fr": "Question posée",
        "it": "Domanda posta",
    },
    "activity.question_answered": {
        "de": "Frage beantwortet",
        "en": "Question answered",
        "fr": "Question répondue",
        "it": "Domanda risolta",
    },
    "activity.ai_conversation": {
        "de": "Unterhaltung mit dem Assistenten",
        "en": "AI conversation",
        "fr": "Conversation avec l'assistant",
        "it": "Conversazione con l'assistente",
    },
    "activity.practice_lesson_completed": {
        "de": "Übungslektion abgeschlossen",
        "en": "Practice lesson completed",
        "fr": "Leçon d'exercices terminée",
        "it": "Lezione di esercizi completata",
    },
    "activity.practice_mistake_logged": {
        "de": "Fehler notiert",
        "en": "Practice mistake logged",
        "fr": "Erreur notée",
        "it": "Errore annotato",
    },
    "activity.practice_path_lesson": {
        "de": "Lektion im Übungspfad",
        "en": "Practice Path lesson",
        "fr": "Leçon du parcours d'exercices",
        "it": "Lezione del percorso di esercizi",
    },
    "activity.weekly_report_available": {
        "de": "Wochenbericht verfügbar",
        "en": "Weekly report available",
        "fr": "Rapport hebdomadaire disponible",
        "it": "Rapporto settimanale disponibile",
    },
    "activity.source.questions": {
        "de": "Fragen",
        "en": "Questions",
        "fr": "Questions",
        "it": "Domande",
    },
    "activity.source.practice_path": {
        "de": "Übungspfad",
        "en": "Practice Path",
        "fr": "Parcours d'exercices",
        "it": "Percorso di esercizi",
    },
    "activity.subject.unknown": {
        "de": "Allgemein",
        "en": "General",
        "fr": "Général",
        "it": "Generale",
    },
}


def text(key: str, locale: str, **values: Any) -> str:
    """One line of copy in the reader's language.

    A locale the table has no entry for falls back to the default rather than
    failing: a missing translation costs the language, never the message.
    """
    variants = TEXT[key]
    rendered = variants.get(locale) or variants[locale_service.DEFAULT_LOCALE]
    return rendered.format(**values) if values else rendered
