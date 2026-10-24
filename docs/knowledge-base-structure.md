# Structuring a knowledge-base batch

In the star map a nebula is a field of knowledge, a **star is one knowledge
point**, and the **small stars around it are question types**. There are no
lessons for the student: tapping a small star practises that type of task on that
knowledge point.

The translation files each upstream knowledge point under a coarse star (a
`group`). `scripts/knowledge_base_import.py structure-batches` hands those groups
out in batches; a structurer - a person or a model - fills one batch and writes
`<batch>.out.json` next to it, and `structure` checks every batch.

## Output

```json
{
  "batch": "structure-mathematics-001",
  "stars": [
    {
      "group": "zahlen-u5",
      "slug": "addition-bis-20",
      "titles": {"de": "Addition bis 20", "en": "Addition up to 20",
                 "fr": "Addition jusqu'à 20", "it": "Addizione fino a 20"},
      "description": "Mit und ohne Zehnerübergang bis 20 addieren.",
      "points": ["kb-m-p014", "kb-m-p015", "kb-m-p019", "kb-m-p020"]
    }
  ],
  "exercises": {"kb-m-p019-q1": "kopfrechnen", "kb-m-p019-q3": "sachaufgaben"}
}
```

## Stars

- Every point of every group goes into exactly one star of **its own group**.
- A star is one knowledge point a teacher would name: "Addition bis 20",
  "Einmaleins", "Division mit Rest" - not a grade, not a chapter, not a mixture.
- At most `maxPointsPerStar` points per star. A group at or under the limit may
  stay one star; split it anyway when it holds two clearly different knowledge
  points. Avoid stars of a single point unless it stands alone.
- Keep the progression: points of one star should be close in grade and build on
  each other.
- `slug`: lower-case ASCII words joined by hyphens (`addition-bis-20`), at most
  48 characters, no umlauts (`ae`, `oe`, `ue`, `ss`).
- `titles`: a short name in all four languages, at most 80 characters, Swiss
  spelling in German (`ss`, never `ß`), no grade and no numbering.
- `description`: one German sentence saying what the knowledge point covers.

## Question types

- Every exercise of the batch gets one type from the batch's `questionTypes`: the
  kind of task it is, judged from its prompt and options - not from the knowledge
  point's name. A word problem about adding is `sachaufgaben`, a bare sum is
  `kopfrechnen` when it is done in the head and `rechnen` when it needs written or
  several steps; "which statement is right" about a definition is `begriffe`.
- In English: a gap to fill with the right form is `grammatik`; choosing which
  sentence is correct is `saetze`; what to say in a situation or reply to an
  utterance is `situationen`; a question about a given text is `lesen`.

## Merging stars

The first pass makes stars small - most hold two to four upstream points. The merge
pass (`merge-batches`, one batch per nebula) joins them: a structurer writes
`merges/<batch>.out.json`, and `structure --merges merges/` applies every batch.

```json
{
  "batch": "merge-zahlen",
  "nebula": "zahlen",
  "stars": [
    {
      "slug": "addition-und-subtraktion-bis-20",
      "titles": {"de": "Addition und Subtraktion bis 20", "en": "Addition and subtraction up to 20",
                 "fr": "Addition et soustraction jusqu'à 20", "it": "Addizione e sottrazione fino a 20"},
      "description": "Mit und ohne Zehnerübergang bis 20 addieren und subtrahieren.",
      "from": ["zahlen-addition-bis-20", "zahlen-subtraktion-bis-20"]
    }
  ]
}
```

- Every star of the batch goes into exactly one merged star (`from`); stars are
  joined whole, never split.
- A merged star holds `minPoints` to `maxPoints` upstream points (the batch says how
  many each input star has). Fewer than `minPoints` only when nothing related is left
  to join; the check refuses a star under `minPoints - 1`, unless the whole nebula is
  smaller.
- Join what belongs together for a teacher: the same operation across number
  ranges, one topic across grades, a skill and its application. Two stars that cover
  the same thing (e.g. "Rechengesetze" and "Rechenregeln") always become one.
- Name, slug and description follow the rules for stars above; the merged star says
  what it now covers.
