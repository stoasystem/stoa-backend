"""The copy of every email STOA sends (#278, #374).

Each is rendered in the language its recipient stored, never in the language
of the request that sent it: an invitation is sent from an administrator's or a
reviewer's request, a weekly report from a job, so the request names the wrong
person (#124).

The frame every email shares - greeting, "just reply", sign-off, footer - is
under `email.common`. The tone is warm and plain: say why the email came, what
to do next, and what to do when a link or code has run out.

Teachers and parents are addressed formally, like every other message this
backend writes to them, and so is an invited account of any role. A digest
goes to students too, so its own lines name nobody. Swiss German writes "ss".
"""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    # ── the frame every email shares ────────────────────────────────────
    "email.common.greeting": {
        "de": "Guten Tag {name}",
        "en": "Hello {name},",
        "fr": "Bonjour {name},",
        "it": "Buongiorno {name},",
    },
    "email.common.greeting_anonymous": {
        "de": "Guten Tag",
        "en": "Hello,",
        "fr": "Bonjour,",
        "it": "Buongiorno,",
    },
    "email.common.questions": {
        "de": "Haben Sie Fragen? Antworten Sie einfach auf diese E-Mail – wir helfen gern.",
        "en": "Any questions? Just reply to this email – we are happy to help.",
        "fr": "Une question ? Répondez simplement à cet e-mail, nous vous aiderons volontiers.",
        "it": "Ha domande? Risponda semplicemente a questa e-mail: saremo lieti di aiutarLa.",
    },
    "email.common.signoff": {
        "de": "Herzliche Grüsse\nIhr STOA-Team",
        "en": "Kind regards\nYour STOA team",
        "fr": "Cordialement\nL'équipe STOA",
        "it": "Cordiali saluti\nIl team STOA",
    },
    "email.common.tagline": {
        "de": "Lernbegleitung für Schülerinnen und Schüler",
        "en": "Learning support for school students",
        "fr": "Accompagnement scolaire pour les élèves",
        "it": "Accompagnamento allo studio per allievi",
    },
    "email.common.link_fallback": {
        "de": "Falls der Knopf nicht funktioniert, kopieren Sie diesen Link in Ihren Browser:",
        "en": "If the button does not work, copy this link into your browser:",
        "fr": "Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :",
        "it": "Se il pulsante non funziona, copi questo link nel browser:",
    },
    # ── the activation email of an invited account, any role ─────────────
    "email.account_invitation.subject": {
        "de": "Willkommen bei STOA – bitte aktivieren Sie Ihr Konto",
        "en": "Welcome to STOA – please activate your account",
        "fr": "Bienvenue chez STOA – activez votre compte",
        "it": "Benvenuti in STOA – attivi il Suo account",
    },
    "email.account_invitation.title": {
        "de": "Willkommen bei STOA",
        "en": "Welcome to STOA",
        "fr": "Bienvenue chez STOA",
        "it": "Benvenuti in STOA",
    },
    "email.account_invitation.intro": {
        "de": "Schön, dass Sie dabei sind! Für Sie wurde ein STOA-Konto eingerichtet.",
        "en": "We are glad to have you with us! A STOA account has been set up for you.",
        "fr": "Nous sommes ravis de vous accueillir ! Un compte STOA a été créé pour vous.",
        "it": "Siamo lieti di averLa con noi! È stato creato un account STOA per Lei.",
    },
    # What the account is for, by role; an unknown role says nothing here.
    "email.account_invitation.role.student": {
        "de": "Mit STOA üben Sie auf Ihrer persönlichen Sternkarte, stellen Fragen zu Ihren Aufgaben und bekommen Hilfe, wenn Sie nicht weiterkommen.",
        "en": "With STOA you practise on your own star map, ask questions about your work and get help whenever you are stuck.",
        "fr": "Avec STOA, vous vous exercez sur votre propre carte des étoiles, posez vos questions sur vos exercices et recevez de l'aide quand vous bloquez.",
        "it": "Con STOA si esercita sulla Sua mappa delle stelle, fa domande sui Suoi compiti e riceve aiuto quando si blocca.",
    },
    "email.account_invitation.role.parent": {
        "de": "Damit begleiten Sie das Lernen Ihres Kindes, lesen die Wochenberichte und bleiben mit den Lehrpersonen in Kontakt.",
        "en": "With it you can follow your child's learning, read the weekly reports and stay in touch with the teachers.",
        "fr": "Vous pourrez ainsi suivre l'apprentissage de votre enfant, lire les rapports hebdomadaires et rester en contact avec les enseignants.",
        "it": "Potrà così seguire l'apprendimento di Suo/a figlio/a, leggere i rapporti settimanali e restare in contatto con gli insegnanti.",
    },
    "email.account_invitation.role.teacher": {
        "de": "Damit helfen Sie Schülerinnen und Schülern bei ihren Fragen und begleiten sie beim Lernen.",
        "en": "With it you help students with their questions and support their learning.",
        "fr": "Vous pourrez ainsi aider les élèves à répondre à leurs questions et les accompagner dans leur apprentissage.",
        "it": "Potrà così aiutare gli allievi con le loro domande e accompagnarli nello studio.",
    },
    "email.account_invitation.role.admin": {
        "de": "Damit verwalten Sie Konten, Inhalte und den Betrieb von STOA.",
        "en": "With it you manage accounts, content and the day-to-day running of STOA.",
        "fr": "Vous pourrez ainsi gérer les comptes, les contenus et le fonctionnement de STOA.",
        "it": "Potrà così gestire gli account, i contenuti e il funzionamento di STOA.",
    },
    "email.account_invitation.next_step": {
        "de": "Es fehlt nur noch ein Schritt: Legen Sie Ihr Passwort fest, dann ist Ihr Konto bereit.",
        "en": "Just one step left: choose your password and your account is ready.",
        "fr": "Il ne reste qu'une étape : choisissez votre mot de passe et votre compte sera prêt.",
        "it": "Manca solo un passo: scelga la Sua password e l'account sarà pronto.",
    },
    "email.account_invitation.action": {
        "de": "Konto aktivieren",
        "en": "Activate account",
        "fr": "Activer mon compte",
        "it": "Attivare l'account",
    },
    # Shared by both activation emails.
    "email.account_invitation.expiry": {
        "de": "Der Link funktioniert einmal und ist bis {expires} gültig. Ist er abgelaufen, schreiben Sie uns einfach – wir schicken Ihnen gern einen neuen.",
        "en": "The link works once and is valid until {expires}. If it has expired, just write to us and we will gladly send you a new one.",
        "fr": "Le lien fonctionne une seule fois et reste valable jusqu'au {expires}. S'il a expiré, écrivez-nous simplement : nous vous en enverrons volontiers un nouveau.",
        "it": "Il link funziona una sola volta ed è valido fino al {expires}. Se è scaduto, ci scriva: Le invieremo volentieri un nuovo link.",
    },
    "email.account_invitation.footer": {
        "de": "Sie erhalten diese E-Mail, weil für Ihre Adresse ein STOA-Konto eröffnet wurde. Haben Sie das nicht erwartet, können Sie sie einfach ignorieren.",
        "en": "You are receiving this email because a STOA account was opened for your address. If you were not expecting it, you can simply ignore it.",
        "fr": "Vous recevez cet e-mail parce qu'un compte STOA a été ouvert pour votre adresse. Si vous ne l'attendiez pas, vous pouvez simplement l'ignorer.",
        "it": "Riceve questa e-mail perché per il Suo indirizzo è stato aperto un account STOA. Se non se lo aspettava, può semplicemente ignorarla.",
    },
    # ── the teacher activation email ─────────────────────────────────────
    "email.teacher_activation.subject": {
        "de": "Willkommen im STOA-Team – Ihre Freischaltung als Lehrperson",
        "en": "Welcome to the STOA team – your activation as a teacher",
        "fr": "Bienvenue dans l'équipe STOA – votre activation en tant qu'enseignant",
        "it": "Benvenuti nel team STOA – la Sua attivazione come insegnante",
    },
    "email.teacher_activation.title": {
        "de": "Willkommen im STOA-Team",
        "en": "Welcome to the STOA team",
        "fr": "Bienvenue dans l'équipe STOA",
        "it": "Benvenuti nel team STOA",
    },
    "email.teacher_activation.intro": {
        "de": "Vielen Dank für Ihre Bewerbung! Wir haben sie geprüft und freuen uns, Ihnen mitzuteilen, dass Sie bei STOA als Lehrperson mitwirken können.",
        "en": "Thank you for your application! We have reviewed it and are delighted to let you know that you can now teach with STOA.",
        "fr": "Merci pour votre candidature ! Nous l'avons examinée et avons le plaisir de vous annoncer que vous pouvez désormais enseigner avec STOA.",
        "it": "Grazie per la Sua candidatura! L'abbiamo esaminata e siamo lieti di comunicarLe che ora può insegnare con STOA.",
    },
    "email.teacher_activation.next_step": {
        "de": "Richten Sie jetzt Ihr Konto ein – danach können Sie die ersten Hilfeanfragen von Schülerinnen und Schülern übernehmen.",
        "en": "Set up your account now – then you can start taking on help requests from students.",
        "fr": "Configurez maintenant votre compte : vous pourrez ensuite prendre en charge les premières demandes d'aide des élèves.",
        "it": "Configuri ora il Suo account: potrà poi accettare le prime richieste di aiuto degli allievi.",
    },
    "email.teacher_activation.action": {
        "de": "Konto einrichten",
        "en": "Set up account",
        "fr": "Configurer mon compte",
        "it": "Configurare l'account",
    },
    "email.teacher_activation.footer": {
        "de": "Sie erhalten diese E-Mail, weil Sie sich bei STOA als Lehrperson beworben haben.",
        "en": "You are receiving this email because you applied to teach with STOA.",
        "fr": "Vous recevez cet e-mail parce que vous avez posé votre candidature comme enseignant chez STOA.",
        "it": "Riceve questa e-mail perché si è candidato/a come insegnante presso STOA.",
    },
    # ── the teacher's dispatch reminder (#141) ───────────────────────────
    #
    # The rest of its copy is under `teacher_help.dispatched`, shared with the
    # in-app notification; this line names only the subject.
    "email.dispatch_reminder.subject_line": {
        "de": "Fach: {subject}",
        "en": "Subject: {subject}",
        "fr": "Matière : {subject}",
        "it": "Materia: {subject}",
    },
    # ── the password change code ─────────────────────────────────────────
    "email.password_code.subject": {
        "de": "Ihr Bestätigungscode für das neue STOA-Passwort",
        "en": "Your verification code for your new STOA password",
        "fr": "Votre code de vérification pour votre nouveau mot de passe STOA",
        "it": "Il Suo codice di verifica per la nuova password STOA",
    },
    "email.password_code.title": {
        "de": "Ihr Bestätigungscode",
        "en": "Your verification code",
        "fr": "Votre code de vérification",
        "it": "Il Suo codice di verifica",
    },
    "email.password_code.intro": {
        "de": "Sie möchten Ihr STOA-Passwort ändern. Geben Sie dazu diesen Code ein:",
        "en": "You asked to change your STOA password. Enter this code to continue:",
        "fr": "Vous souhaitez modifier votre mot de passe STOA. Saisissez ce code pour continuer :",
        "it": "Ha chiesto di modificare la password STOA. Inserisca questo codice per continuare:",
    },
    "email.password_code.expiry": {
        "de": "Der Code ist {minutes} Minuten lang gültig und funktioniert nur einmal. Ist er abgelaufen, fordern Sie in STOA einfach einen neuen an.",
        "en": "The code is valid for {minutes} minutes and works once. If it has expired, simply request a new one in STOA.",
        "fr": "Le code est valable {minutes} minutes et ne fonctionne qu'une fois. S'il a expiré, demandez-en simplement un nouveau dans STOA.",
        "it": "Il codice è valido per {minutes} minuti e funziona una sola volta. Se è scaduto, ne richieda semplicemente uno nuovo in STOA.",
    },
    "email.password_code.not_you": {
        "de": "Waren Sie das nicht? Dann ändern Sie nichts und melden Sie sich bitte bei uns – Ihr Passwort bleibt, wie es ist.",
        "en": "Wasn't you? Then change nothing and please let us know – your password stays as it is.",
        "fr": "Ce n'était pas vous ? Ne modifiez rien et prévenez-nous : votre mot de passe reste inchangé.",
        "it": "Non è stato Lei? Non modifichi nulla e ci avvisi: la Sua password resta invariata.",
    },
    "email.password_code.footer": {
        "de": "Sie erhalten diese E-Mail, weil in Ihrem STOA-Konto eine Passwortänderung angefordert wurde.",
        "en": "You are receiving this email because a password change was requested in your STOA account.",
        "fr": "Vous recevez cet e-mail parce qu'une modification du mot de passe a été demandée dans votre compte STOA.",
        "it": "Riceve questa e-mail perché nel Suo account STOA è stata richiesta una modifica della password.",
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
    # Each item below the intro is the notification's own title and summary.
    "email.notification_digest.subject": {
        "de": "STOA – Ihre neuen Mitteilungen",
        "en": "STOA – Your new notifications",
        "fr": "STOA – Vos nouvelles notifications",
        "it": "STOA – Le Sue nuove notifiche",
    },
    "email.notification_digest.title": {
        "de": "Das ist neu bei STOA",
        "en": "Here is what's new on STOA",
        "fr": "Voici les nouveautés sur STOA",
        "it": "Ecco le novità su STOA",
    },
    "email.notification_digest.intro": {
        "de": "Seit Ihrer letzten Zusammenfassung ist Folgendes passiert:",
        "en": "Here is what has happened since your last digest:",
        "fr": "Voici ce qui s'est passé depuis votre dernier résumé :",
        "it": "Ecco cosa è successo dal Suo ultimo riepilogo:",
    },
    "email.notification_digest.action": {
        "de": "STOA öffnen",
        "en": "Open STOA",
        "fr": "Ouvrir STOA",
        "it": "Apri STOA",
    },
    # ── the weekly report email to a parent ──────────────────────────────
    #
    # The fixed frame around the report; what the report says about the week
    # is generated content and is not here.
    "email.weekly_report.subject": {
        "de": "STOA – Wochenbericht für {student}",
        "en": "STOA – Weekly report for {student}",
        "fr": "STOA – Rapport hebdomadaire de {student}",
        "it": "STOA – Rapporto settimanale di {student}",
    },
    "email.weekly_report.title": {
        "de": "Wochenbericht für {student}",
        "en": "Weekly report for {student}",
        "fr": "Rapport hebdomadaire de {student}",
        "it": "Rapporto settimanale di {student}",
    },
    "email.weekly_report.intro": {
        "de": "Hier ist der Rückblick auf die vergangene Lernwoche.",
        "en": "Here is a look back at the past week of learning.",
        "fr": "Voici le bilan de la semaine d'apprentissage écoulée.",
        "it": "Ecco il riepilogo dell'ultima settimana di studio.",
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
        "en": "Topics to practise",
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
        "de": "Bericht in STOA öffnen",
        "en": "Open the report in STOA",
        "fr": "Ouvrir le rapport dans STOA",
        "it": "Apri il rapporto in STOA",
    },
}
