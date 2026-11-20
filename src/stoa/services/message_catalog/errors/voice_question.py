"""Why a recording was not transcribed (`stoa.services.voice_transcription.VoiceQuestionErrorCode`).

Read by the student asking by voice: `du`, `tu`, `tu`.
"""

TEXT: dict[str, dict[str, str]] = {
    "error.voice_questions_not_allowed": {
        "de": "Fragen per Sprache sind für dich nicht eingeschaltet. Deine Eltern können sie erlauben.",
        "en": "Voice questions are not switched on for you. Your parents can allow them.",
        "fr": "Les questions vocales ne sont pas activées pour toi. Tes parents peuvent les autoriser.",
        "it": "Le domande vocali non sono attive per te. I tuoi genitori possono consentirle.",
    },
    "error.voice_recording_unsupported": {
        "de": "Diese Aufnahme kann nicht verwendet werden. Nimm deine Frage bitte noch einmal auf.",
        "en": "This recording cannot be used. Please record your question again.",
        "fr": "Cet enregistrement ne peut pas être utilisé. Enregistre ta question encore une fois.",
        "it": "Questa registrazione non può essere usata. Registra di nuovo la tua domanda.",
    },
    "error.voice_recording_too_large": {
        "de": "Die Aufnahme ist zu gross (höchstens {max_megabytes} MB). Nimm eine kürzere Frage auf.",
        "en": "The recording is too large (at most {max_megabytes} MB). Record a shorter question.",
        "fr": "L'enregistrement est trop volumineux ({max_megabytes} Mo au maximum). Enregistre une question plus courte.",
        "it": "La registrazione è troppo grande (al massimo {max_megabytes} MB). Registra una domanda più breve.",
    },
    "error.voice_recording_too_long": {
        "de": "Die Aufnahme ist zu lang (höchstens {max_seconds} Sekunden). Nimm eine kürzere Frage auf.",
        "en": "The recording is too long (at most {max_seconds} seconds). Record a shorter question.",
        "fr": "L'enregistrement est trop long ({max_seconds} secondes au maximum). Enregistre une question plus courte.",
        "it": "La registrazione è troppo lunga (al massimo {max_seconds} secondi). Registra una domanda più breve.",
    },
    "error.voice_recording_unreadable": {
        "de": "Die Aufnahme konnte nicht gelesen werden. Nimm deine Frage bitte noch einmal auf.",
        "en": "The recording could not be read. Please record your question again.",
        "fr": "L'enregistrement n'a pas pu être lu. Enregistre ta question encore une fois.",
        "it": "Non è stato possibile leggere la registrazione. Registra di nuovo la tua domanda.",
    },
    "error.voice_recording_silent": {
        "de": "In der Aufnahme war nichts zu verstehen. Sprich bitte etwas lauter und versuche es noch einmal.",
        "en": "Nothing could be understood in the recording. Please speak a little louder and try again.",
        "fr": "On n'a rien compris dans l'enregistrement. Parle un peu plus fort et réessaie.",
        "it": "Nella registrazione non si capiva niente. Parla un po' più forte e riprova.",
    },
    "error.voice_transcription_daily_limit": {
        "de": "Du hast heute schon {limit} Fragen per Sprache gestellt. Schreib deine Frage oder versuche es morgen wieder.",
        "en": "You have already asked {limit} voice questions today. Type your question or try again tomorrow.",
        "fr": "Tu as déjà posé {limit} questions vocales aujourd'hui. Écris ta question ou réessaie demain.",
        "it": "Oggi hai già fatto {limit} domande vocali. Scrivi la tua domanda o riprova domani.",
    },
    "error.voice_transcription_unavailable": {
        "de": "Deine Aufnahme kann gerade nicht in Text umgewandelt werden. Versuche es gleich noch einmal.",
        "en": "Your recording cannot be turned into text right now. Please try again in a moment.",
        "fr": "Ton enregistrement ne peut pas être transformé en texte pour le moment. Réessaie dans un instant.",
        "it": "Al momento la tua registrazione non può essere trasformata in testo. Riprova tra poco.",
    },
    "error.voice_transcription_refused": {
        "de": "Fragen per Sprache funktionieren gerade nicht. Schreib deine Frage bitte auf.",
        "en": "Voice questions are not working at the moment. Please type your question.",
        "fr": "Les questions vocales ne fonctionnent pas pour le moment. Écris ta question, s'il te plaît.",
        "it": "Le domande vocali al momento non funzionano. Scrivi la tua domanda, per favore.",
    },
}
