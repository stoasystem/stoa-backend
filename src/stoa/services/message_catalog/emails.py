"""The copy of three emails that used to speak one language each (#278).

Each is rendered in the language its recipient stored, never in the language
of the request that sent it: an invitation is sent from a reviewer's request,
a weekly report from a job, so the request names the wrong person (#124).

Teachers and parents are addressed formally, like every other message this
backend writes to them. A digest goes to students too, so its own lines name
nobody.
"""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    # ── the teacher activation email ─────────────────────────────────────
    "email.teacher_activation.subject": {
        "de": "STOA - Ihre Freischaltung als Lehrperson",
        "en": "STOA - Your activation as a teacher",
        "fr": "STOA - Votre activation en tant qu'enseignant",
        "it": "STOA - La Sua attivazione come insegnante",
    },
    "email.teacher_activation.greeting": {
        "de": "Hallo {name},",
        "en": "Hello {name},",
        "fr": "Bonjour {name},",
        "it": "Buongiorno {name},",
    },
    "email.teacher_activation.greeting_anonymous": {
        "de": "Hallo,",
        "en": "Hello,",
        "fr": "Bonjour,",
        "it": "Buongiorno,",
    },
    "email.teacher_activation.intro": {
        "de": (
            "Ihre Bewerbung als Lehrperson bei STOA wurde geprüft und freigegeben. "
            "Über den folgenden Link können Sie Ihr Konto einrichten und freischalten:"
        ),
        "en": (
            "Your application to teach with STOA has been reviewed and approved. "
            "Use the link below to set up and activate your account:"
        ),
        "fr": (
            "Votre candidature comme enseignant chez STOA a été examinée et acceptée. "
            "Le lien ci-dessous vous permet de configurer et d'activer votre compte :"
        ),
        "it": (
            "La Sua candidatura come insegnante presso STOA è stata esaminata e approvata. "
            "Con il link seguente può configurare e attivare il Suo account:"
        ),
    },
    "email.teacher_activation.action": {
        "de": "Konto freischalten",
        "en": "Activate account",
        "fr": "Activer le compte",
        "it": "Attivare l'account",
    },
    "email.teacher_activation.expiry": {
        "de": "Der Link ist einmalig verwendbar und gültig bis {expires}.",
        "en": "The link can be used once and is valid until {expires}.",
        "fr": "Ce lien est à usage unique et valable jusqu'au {expires}.",
        "it": "Il link è utilizzabile una sola volta ed è valido fino al {expires}.",
    },
    # ── the unsubscribe line under each notification email (#363) ─────────
    #
    # Why this email came, then the link that stops this kind of email.
    "email.unsubscribe.reason.weekly_report": {
        "de": "Sie erhalten diese E-Mail, weil STOA Ihnen Wochenberichte über Ihr Kind sendet.",
        "en": "You are receiving this email because STOA sends you weekly reports about your child.",
        "fr": "Vous recevez cet e-mail parce que STOA vous envoie des rapports hebdomadaires sur votre enfant.",
        "it": "Riceve questa e-mail perché STOA Le invia rapporti settimanali su Suo/a figlio/a.",
    },
    "email.unsubscribe.reason.dispatch_reminder": {
        "de": "Sie erhalten diese E-Mail, weil STOA Ihnen Hilfeanfragen zuweist.",
        "en": "You are receiving this email because STOA offers you help requests.",
        "fr": "Vous recevez cet e-mail parce que STOA vous attribue des demandes d'aide.",
        "it": "Riceve questa e-mail perché STOA Le assegna richieste di aiuto.",
    },
    "email.unsubscribe.reason.notification_digest": {
        "de": "Sie erhalten diese E-Mail, weil Sie Zusammenfassungen Ihrer Mitteilungen per E-Mail eingeschaltet haben.",
        "en": "You are receiving this email because you turned on notification digests by email.",
        "fr": "Vous recevez cet e-mail parce que vous avez activé les résumés de notifications par e-mail.",
        "it": "Riceve questa e-mail perché ha attivato i riepiloghi delle notifiche via e-mail.",
    },
    "email.unsubscribe.action": {
        "de": "Diese E-Mails abbestellen",
        "en": "Unsubscribe from these emails",
        "fr": "Se désabonner de ces e-mails",
        "it": "Non ricevere più queste e-mail",
    },
    # ── the notification digest email ────────────────────────────────────
    #
    # The subject and the heading of the body; each item below it is the
    # notification's own title and summary.
    "email.notification_digest.title": {
        "de": "STOA - Zusammenfassung der Mitteilungen",
        "en": "STOA notification digest",
        "fr": "STOA - Résumé des notifications",
        "it": "STOA - Riepilogo delle notifiche",
    },
    # ── the weekly report email to a parent ──────────────────────────────
    #
    # The fixed frame around the report; what the report says about the week
    # is generated content and is not here.
    "email.weekly_report.subject": {
        "de": "STOA - Wochenbericht für {student}",
        "en": "STOA weekly report for {student}",
        "fr": "STOA - Rapport hebdomadaire de {student}",
        "it": "STOA - Rapporto settimanale di {student}",
    },
    "email.weekly_report.title": {
        "de": "Wochenbericht für {student}",
        "en": "Weekly report for {student}",
        "fr": "Rapport hebdomadaire de {student}",
        "it": "Rapporto settimanale di {student}",
    },
    # Stands in for {student} when the report names nobody.
    "email.weekly_report.student_fallback": {
        "de": "Ihr Kind",
        "en": "your child",
        "fr": "votre enfant",
        "it": "Suo/a figlio/a",
    },
    "email.weekly_report.week": {
        "de": "Woche:",
        "en": "Week:",
        "fr": "Semaine :",
        "it": "Settimana:",
    },
    "email.weekly_report.week_range": {
        "de": "{start} bis {end}",
        "en": "{start} to {end}",
        "fr": "du {start} au {end}",
        "it": "dal {start} al {end}",
    },
    "email.weekly_report.recommendations": {
        "de": "Empfehlungen",
        "en": "Recommendations",
        "fr": "Recommandations",
        "it": "Raccomandazioni",
    },
    "email.weekly_report.weak_topics": {
        "de": "Themen mit Übungsbedarf",
        "en": "Weak topics",
        "fr": "Points à retravailler",
        "it": "Argomenti da rafforzare",
    },
    "email.weekly_report.teacher_note": {
        "de": "Hinweis der Lehrperson:",
        "en": "Teacher note:",
        "fr": "Note de l'enseignant :",
        "it": "Nota dell'insegnante:",
    },
    "email.weekly_report.portal_link": {
        "de": "Diesen Bericht im Elternportal öffnen",
        "en": "Open this report in the parent portal",
        "fr": "Ouvrir ce rapport dans le portail des parents",
        "it": "Apri questo rapporto nel portale dei genitori",
    },
}
