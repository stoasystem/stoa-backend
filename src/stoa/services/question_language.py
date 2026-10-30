"""Which of the four languages a student wrote a question in (#172).

An Ask answer comes back in the language the question was asked in, not the
language the app happens to be displayed in. Only what the student typed is
read: a quoted passage, the text of an attachment or the exercise beside the
question can be in any language and say nothing about the student's own.

Recognition is a word list, not a model call: each language contributes common
words the other three do not share, and a question is in the language with the
most of them. Words two of the languages share ("du", "des", "da", "will", "i",
"la", "il", "non", "tu", "per", "was", "come") are left out on purpose, since
they would tip a short question the wrong way. A question with no listed word, or a tie, is not recognised, and
the caller falls back: a bare formula, "ok" or "?" says nothing about language.
The same text always gives the same answer, so a retried command keeps the
language of its first attempt.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_WORDS: dict[str, frozenset[str]] = {
    "de": frozenset(
        """
        der die das dem den und ist sind nicht ich er wir ihr wie warum
        wieso weshalb welche welcher welches wo wann ein eine einen einem einer
        mit von zu auf für bei sich auch kann kannst können muss musst soll
        bitte mir mich dir dich dass oder aber nur noch schon hier dann wenn
        weil geht habe hast haben wird werden nein ja doch aufgabe gleichung
        löse lösen rechne rechnen erkläre erklär erklären verstehe verstehen
        heisst heißt bedeutet brüche bruch ergebnis danke hallo
        """.split()
    ),
    "en": frozenset(
        """
        the and is are what why how which where when who whose this that these
        those does do did can could would should please explain solve help my
        you your with of for from it i'm don't doesn't not to have has there
        here if because but or equation problem question answer understand
        mean means get find calculate then just thanks hello hi
        """.split()
    ),
    "fr": frozenset(
        """
        les une et est sont je nous vous comment pourquoi quoi quel
        quelle quels quelles où quand que cette ces avec pour dans sur pas mon
        ton mes tes peux peut pouvez faire fais explique expliquer expliquez
        résoudre résous aide aider aidez comprends comprendre équation exercice
        problème réponse c'est j'ai qu'est-ce ça au aux mais ou donc alors
        merci bonjour veux veut
        """.split()
    ),
    "it": frozenset(
        """
        lo gli della dello delle degli del di sono io lui lei noi voi
        perché perche cosa quale quali dove quando che chi questo questa questi
        quello quella con mio mia tuo tua puoi può posso fare fammi spiega
        spiegami risolvere risolvi aiuto aiutami capisco capire equazione
        esercizio problema risposta ciao grazie anche oppure allora quindi ho
        hai uno una nel nella sul sulla cos'è
        """.split()
    ),
}

# Letters, the accents the four languages use, and the apostrophe inside
# "c'est" or "don't"; digits and operators split words and count for nothing.
_WORD = re.compile(r"[a-zà-öø-ÿ]+(?:['’][a-zà-öø-ÿ]+)?")


def detect(text: str | None) -> str | None:
    """The language `text` is written in, or None when the words do not say."""
    scores = dict.fromkeys(_WORDS, 0)
    for word in _WORD.findall(str(text or "").lower()):
        word = word.replace("’", "'")
        for language, words in _WORDS.items():
            if word in words:
                scores[language] += 1
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top == 0 or top == second:
        return None
    return best


def answer_language(
    question: str | None,
    history: Iterable[Mapping[str, object]],
    *,
    fallback: str,
) -> str:
    """The language to answer `question` in.

    The question itself first. When it says nothing, the student's own earlier
    messages in the conversation, newest first, so a German conversation that
    goes on with "ok" or a formula stays German. When none of them says
    anything either, `fallback`: the language the app is displayed in.
    """
    found = detect(question)
    if found is not None:
        return found
    for message in reversed(list(history)):
        if message.get("role") != "student":
            continue
        found = detect(str(message.get("content") or ""))
        if found is not None:
            return found
    return fallback
