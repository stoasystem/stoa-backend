# Translating a knowledge-base batch

`scripts/knowledge_base_import.py batches` cuts the extracted knowledge base into
batch files of about a dozen knowledge points with their exercises, written in
Chinese. A translator - a person or a model - fills one batch at a time and writes
`<batch>.out.json` next to it; `merge` then checks every record and refuses what
breaks a rule below. The batches and their translations stay out of the repository
(the upstream licence is CC BY-NC 4.0).

## Output

```json
{
  "batch": "mathematics-001",
  "points": {
    "kb-m-p001": {
      "unit": "zahlen-u5",
      "de": {"name": "...", "description": "...", "mastery": ["...", "..."]},
      "en": {...}, "fr": {...}, "it": {...}
    }
  },
  "exercises": {
    "kb-m-p001-q1": {
      "de": {"prompt": "...", "answer": "4", "accepted": [], "explanation": "..."},
      "en": {...}, "fr": {...}, "it": {...}
    },
    "kb-m-p001-q4": {
      "de": {"prompt": "...", "choices": ["...", "...", "..."], "explanation": "..."},
      "en": {...}, "fr": {...}, "it": {...}
    },
    "kb-m-p001-q9": {"drop": "why this exercise cannot be carried over"}
  }
}
```

- Every point and every exercise of the batch gets an entry, in all four locales
  `de`, `en`, `fr`, `it`, or - exercises only - a `drop` with its reason.
- `unit` (mathematics and physics only): the id of the star from the batch's
  `units` whose title and scope fit the knowledge point best. English batches
  have no `units`; leave `unit` out.
- `mastery`: as many criteria as the source has, in the same order.
- Choice exercises: `choices` in the source's order, one text per option and no
  letter in front; the right option stays the one at `answerIndex`. Options must
  stay distinct from one another.
- Answer exercises: `answer`, and `accepted` for other ways of writing the same
  answer. An answer that is a plain value (`4`, `-3, -1/2`, `x=2`, `3/4`) is
  copied exactly; an answer with words or units is translated (`12厘米` → `12 cm`).
  Answers in a list keep the comma: `3, -3`.

## Rules

- No Chinese characters anywhere in the output, including punctuation: use
  `,` `(` `)` `:` `?` and the quotation marks of the target language.
- **Leave the textbook behind.** Nothing may name or point at a textbook, an
  edition, a publisher, a curriculum standard, a unit or chapter number, a page,
  or "this map". A convention the source attributes to the textbook ("按教材约定")
  is stated as a convention: "By convention, ...". The knowledge point's name and
  description say what is learnt, never where it sits in a book.
- **Localise to Switzerland.** Money in 元/角/分 becomes francs and centimes with
  the same numbers (1 元 → 1 Fr., 1 角 → 10 Rp. / 10 ct.); Chinese personal names
  become names common in Switzerland; Chinese places, festivals and stories become
  neutral or Swiss ones when the mathematics does not depend on them. Metric units
  stay. Drop an exercise that only works with Chinese traditional units (斤, 亩,
  里), Chinese characters, Chinese idioms or poems, or facts about China.
- **Keep the mathematics exactly.** Numbers, formulas, variables, units and the
  order of options do not change. Keep the source's decimal point in numbers.
  If the source answer is wrong or the prompt is ambiguous, drop the exercise and
  say why rather than repair it.
- **English as a subject.** English words, sentences and options that are the
  material being learnt stay exactly as they are in every locale; only the
  instructions, explanations and Chinese glosses are translated into the locale's
  language (in `en`, the instructions are in English too). A task that asks for the
  English of a Chinese phrase asks for the English of the same phrase in the
  locale's language. Drop a task that depends on Chinese pronunciation or Chinese
  grammar.
- **Register.** Address the student with du / tu / tu and you. German follows
  Swiss spelling: `ss`, never `ß`. Keep prompts as short as the source.
- Names of knowledge points: a short skill title (at most 80 characters) in the
  style "Brüche addieren", "Adding fractions", "Additionner des fractions",
  "Addizionare frazioni"; no grade, no numbering.
