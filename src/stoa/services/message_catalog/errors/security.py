"""Sign-in and authorization refusals (`stoa.security.errors.SecurityErrorCode`).

Read by students, parents and teachers alike. Addressed as the web client
addresses its own sign-in copy: `du` in German, `vous` in French, `tu` in
Italian.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.authentication_required": {
        "de": "Bitte melde dich an, um fortzufahren.",
        "en": "Please sign in to continue.",
        "fr": "Veuillez vous connecter pour continuer.",
        "it": "Accedi per continuare.",
    },
    "error.invalid_token": {
        "de": "Deine Sitzung ist nicht gültig. Bitte melde dich erneut an.",
        "en": "Your session is not valid. Please sign in again.",
        "fr": "Votre session n'est pas valide. Veuillez vous reconnecter.",
        "it": "La tua sessione non è valida. Accedi di nuovo.",
    },
    "error.token_expired": {
        "de": "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.",
        "en": "Your session has expired. Please sign in again.",
        "fr": "Votre session a expiré. Veuillez vous reconnecter.",
        "it": "La tua sessione è scaduta. Accedi di nuovo.",
    },
    "error.identity_conflict": {
        "de": (
            "Wende dich an den Support und gib die angezeigte Referenz an, "
            "damit wir dein Konto wiederherstellen können."
        ),
        "en": "Contact support and share the reference shown so we can restore your account.",
        "fr": (
            "Contactez le support en indiquant la référence affichée "
            "afin que nous puissions rétablir votre compte."
        ),
        "it": (
            "Contatta il supporto indicando il riferimento mostrato, "
            "così potremo ripristinare il tuo account."
        ),
    },
    "error.parent_binding_required": {
        "de": "Schliesse zuerst die Verbindung mit deinen Eltern ab.",
        "en": "Complete the parent connection before continuing.",
        "fr": "Terminez d'abord la liaison avec le compte parent.",
        "it": "Completa prima il collegamento con il genitore.",
    },
    "error.teacher_review_pending": {
        "de": "Deine Bewerbung als Lehrperson wird noch geprüft.",
        "en": "Your teacher application is still under review.",
        "fr": "Votre candidature d'enseignant est encore en cours d'examen.",
        "it": "La tua candidatura come insegnante è ancora in fase di verifica.",
    },
    "error.action_not_allowed": {
        "de": "Diese Aktion ist für dich nicht möglich.",
        "en": "You cannot perform this action.",
        "fr": "Vous ne pouvez pas effectuer cette action.",
        "it": "Non puoi eseguire questa azione.",
    },
    "error.resource_not_found": {
        "de": "Das Gesuchte wurde nicht gefunden.",
        "en": "The requested resource was not found.",
        "fr": "L'élément demandé est introuvable.",
        "it": "L'elemento richiesto non è stato trovato.",
    },
    "error.identity_provider_unavailable": {
        "de": (
            "Versuche es in ein paar Minuten noch einmal. Wenn das Problem bleibt, "
            "wende dich an den Support und gib die angezeigte Referenz an."
        ),
        "en": (
            "Try again in a few minutes. If the problem continues, "
            "contact support and share the reference shown."
        ),
        "fr": (
            "Réessayez dans quelques minutes. Si le problème persiste, "
            "contactez le support en indiquant la référence affichée."
        ),
        "it": (
            "Riprova tra qualche minuto. Se il problema persiste, "
            "contatta il supporto indicando il riferimento mostrato."
        ),
    },
    "error.authorization_temporarily_unavailable": {
        "de": "Diese Aktion ist gerade nicht verfügbar. Versuche es später noch einmal.",
        "en": "This action is temporarily unavailable. Try again later.",
        "fr": "Cette action est temporairement indisponible. Réessayez plus tard.",
        "it": "Questa azione al momento non è disponibile. Riprova più tardi.",
    },
    "error.invalid_credentials": {
        "de": "Prüfe deine E-Mail-Adresse und dein Passwort und melde dich dann erneut an.",
        "en": "Check your email and password, then try signing in again.",
        "fr": "Vérifiez votre adresse e-mail et votre mot de passe, puis reconnectez-vous.",
        "it": "Controlla l'indirizzo e-mail e la password, poi prova di nuovo ad accedere.",
    },
    "error.email_verification_required": {
        "de": "Bestätige deine E-Mail-Adresse und melde dich dann erneut an.",
        "en": "Verify your email, then sign in again.",
        "fr": "Confirmez votre adresse e-mail, puis reconnectez-vous.",
        "it": "Conferma il tuo indirizzo e-mail, poi accedi di nuovo.",
    },
    "error.account_disabled": {
        "de": (
            "Wende dich an den Support und gib die angezeigte Referenz an, "
            "um wieder Zugang zu deinem Konto zu erhalten."
        ),
        "en": "Contact support and share the reference shown to restore access to your account.",
        "fr": (
            "Contactez le support en indiquant la référence affichée "
            "pour retrouver l'accès à votre compte."
        ),
        "it": (
            "Contatta il supporto indicando il riferimento mostrato "
            "per riottenere l'accesso al tuo account."
        ),
    },
    "error.account_invitation_unclaimed": {
        "de": (
            "Dieses Konto wurde noch nicht aktiviert. "
            "Öffne den Link aus deiner Einladungs-E-Mail, um es zu aktivieren."
        ),
        "en": (
            "This account has not been activated yet. "
            "Open the link in your invitation email to activate it."
        ),
        "fr": (
            "Ce compte n'a pas encore été activé. "
            "Ouvrez le lien de votre e-mail d'invitation pour l'activer."
        ),
        "it": (
            "Questo account non è ancora stato attivato. "
            "Apri il link nell'e-mail di invito per attivarlo."
        ),
    },
    "error.account_review_pending": {
        "de": "Dein Konto wird noch geprüft. Du kannst dich anmelden, sobald es freigegeben ist.",
        "en": "Your account is still being reviewed. You can sign in once it has been approved.",
        "fr": (
            "Votre compte est encore en cours de vérification. "
            "Vous pourrez vous connecter dès qu'il sera approuvé."
        ),
        "it": (
            "Il tuo account è ancora in fase di verifica. "
            "Potrai accedere non appena sarà approvato."
        ),
    },
    "error.account_archived": {
        "de": (
            "Dieses Konto wurde archiviert. Wende dich an den Support "
            "und gib die angezeigte Referenz an, wenn du es wieder brauchst."
        ),
        "en": (
            "This account has been archived. Contact support and share "
            "the reference shown if you need it again."
        ),
        "fr": (
            "Ce compte a été archivé. Contactez le support en indiquant "
            "la référence affichée si vous en avez de nouveau besoin."
        ),
        "it": (
            "Questo account è stato archiviato. Contatta il supporto indicando "
            "il riferimento mostrato se ti serve di nuovo."
        ),
    },
    "error.account_provisioning_failed": {
        "de": (
            "Beim Einrichten dieses Kontos ist etwas schiefgegangen. "
            "Wende dich an den Support und gib die angezeigte Referenz an."
        ),
        "en": (
            "Something went wrong while this account was being set up. "
            "Contact support and share the reference shown."
        ),
        "fr": (
            "Un problème est survenu lors de la création de ce compte. "
            "Contactez le support en indiquant la référence affichée."
        ),
        "it": (
            "Si è verificato un problema durante la creazione di questo account. "
            "Contatta il supporto indicando il riferimento mostrato."
        ),
    },
    "error.email_already_registered": {
        "de": (
            "Für diese E-Mail-Adresse gibt es bereits ein Konto. "
            "Melde dich an oder setze dein Passwort zurück."
        ),
        "en": "This email already has an account. Sign in instead, or reset your password.",
        "fr": (
            "Un compte existe déjà pour cette adresse e-mail. "
            "Connectez-vous ou réinitialisez votre mot de passe."
        ),
        "it": (
            "Per questo indirizzo e-mail esiste già un account. "
            "Accedi oppure reimposta la password."
        ),
    },
    "error.password_requirements_not_met": {
        "de": (
            "Wähle ein stärkeres Passwort, das die genannten Anforderungen erfüllt, "
            "und versuche es dann noch einmal."
        ),
        "en": "Choose a stronger password that meets the listed requirements, then try again.",
        "fr": (
            "Choisissez un mot de passe plus robuste qui remplit les exigences indiquées, "
            "puis réessayez."
        ),
        "it": (
            "Scegli una password più sicura che rispetti i requisiti indicati, "
            "poi riprova."
        ),
    },
    "error.verification_code_invalid": {
        "de": "Prüfe den Bestätigungscode und versuche es noch einmal.",
        "en": "Check the verification code and try again.",
        "fr": "Vérifiez le code de confirmation et réessayez.",
        "it": "Controlla il codice di verifica e riprova.",
    },
    "error.verification_code_expired": {
        "de": "Fordere einen neuen Bestätigungscode an und versuche es dann noch einmal.",
        "en": "Request a new verification code, then try again.",
        "fr": "Demandez un nouveau code de confirmation, puis réessayez.",
        "it": "Richiedi un nuovo codice di verifica, poi riprova.",
    },
    "error.password_reset_request_invalid": {
        "de": (
            "Fordere einen neuen Code zum Zurücksetzen des Passworts an "
            "und versuche es dann noch einmal."
        ),
        "en": "Request a new password reset code, then try again.",
        "fr": "Demandez un nouveau code de réinitialisation du mot de passe, puis réessayez.",
        "it": "Richiedi un nuovo codice per reimpostare la password, poi riprova.",
    },
    "error.auth_request_rate_limited": {
        "de": "Warte ein paar Minuten, bevor du es noch einmal versuchst.",
        "en": "Wait a few minutes before trying this action again.",
        "fr": "Patientez quelques minutes avant de réessayer.",
        "it": "Aspetta qualche minuto prima di riprovare.",
    },
}
