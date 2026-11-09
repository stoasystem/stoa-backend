# Importing the knowledge base

The knowledge base adapted from [cn-math-taxonomy](https://github.com/xiaoyang111222/cn-math-taxonomy)
brings 1821 knowledge points (mathematics from the first year of primary school to
upper secondary, English, physics), their prerequisite edges and a question bank,
in German with English, French and Italian translations.

In the star map a nebula is a field of knowledge, a **star is one knowledge point**
and the **small stars around it are question types**. There are no lessons for the
student: a small star's exercises are its practice. Technically they sit in hidden
practice sets that carry the small star's id (cut into parts of at most ten
exercises), so the practice reads, the quiz and the mastery work unchanged.

**Licence.** The upstream is CC BY-NC 4.0: no commercial use without the author's
permission. On 2026-11-09 the author's permission to use it was given to the
operator and passed on here in words, not in writing, together with the note that
the upstream itself was generated elsewhere; publishing goes ahead on that basis
and this paragraph is the record of it. Neither the permission nor the upstream's
own provenance settles any third party's rights in the material. The source text
and its translations still stay out of the repository; only the star file and the
skill vocabulary (names of knowledge points and question types) are committed.

## What is left behind

The Chinese textbook records: chapter and unit numbers, semesters, curriculum
standard ids, edition mappings, id aliases and the upstream's review logs. Text that
attributes a convention to a textbook is rewritten as a convention, and the merge
step refuses any translation that still points at a textbook. Exercises with a
figure (practice shows no figures yet) and self-assessments are skipped and listed.

## Where it goes

`src/stoa/services/knowledge_base_catalog.py` holds the nebulae, the coarse stars
the translation files each upstream point under, and the question types of each
subject. The structuring step splits every coarse star into knowledge-point stars
of at most twelve upstream points and tags every exercise with its question type;
the result is `knowledge_base_stars.json` and `knowledge_base_skills.json`.
Mathematics keeps its seven nebulae: the ZAP stars stay as they are, and the
knowledge base gets stars of its own beside them.

### What a student is ready for, and what lights a star

- **Layers.** Inside a star its upstream knowledge points are layered by the
  upstream edges between them: layer 1 needs nothing else in the star, layer 2
  needs layer 1, and so on (at most four). A small star's practice is cut by
  layer, so the star is worked through from its foundations up; a small star with
  more than one layer shows "Stufe 1", "Stufe 2" ... A layer with fewer than three
  exercises joins the next one (the last joins the one before), shown as
  "Stufe 1–2", so a practice set is more than a question or two; a stage of more
  than ten exercises is cut into parts of even size.
- **Readiness, not age.** Every practice set states the knowledge points that come
  before it (`requiresPoints`), in its own star or another. A knowledge point is
  mastered when every core exercise of it has been answered right once. The star
  map names, for each small star, the stars holding what its next practice needs
  and the student has not mastered yet (`missingPrerequisites`). Nothing is
  locked by it: the practice stays open, the hint says where to go first.
- **Core and extension.** Question types that deepen a knowledge point are
  extension: formulas and reasoning in mathematics, experiments and charts in
  physics, reading and pronunciation in English. A star lights from its core
  practice sets; extension sets are practice beside it and their small stars say
  `extension`. The ZAP stars have no extension sets, so they light as before.

### Reading the star map at this size

- Every list read of the practice partition follows all its pages; a lesson list of
  two thousand rows is over the 1 MB a query returns.
- A published or seeded practice set carries its exercise index on its lesson row
  (each exercise's id, small stars and knowledge point), so the catalog and the
  star map judge from lesson rows instead of reading every set's exercises. A row
  written before that still works, read through its challenges; running
  `seed_practice.py` once after the deploy writes the index onto the ZAP lessons.
- `GET /practice/knowledge-map?view=skeleton` sends every star without its small
  stars, and `GET /practice/knowledge-map/stars?around=<unit>` the few around one in
  full - the star, the stars it needs, the stars that need it and its neighbours,
  with small stars, practice sets and missing prerequisites. The client opens on
  the skeleton and loads the neighbourhood it shows (stoa-frontend#503).

A language subject is laid out the same way for every language: ten nebulae for
situations of life (me and others, daily life, school and work, food and shopping,
free time, out and about, nature, health, society, communicating) and four for
grammar (letters and sounds, parts of speech, verbs and tenses, building
sentences). Another language - German, French, Italian - gets the same nebulae by
one entry in `LANGUAGE_SUBJECTS` once it has content.

## Steps

All data files live outside the repository, e.g. in `.scratch/knowledge-base/`.

1. **Extract** from a checkout of the upstream:
   `uv run python scripts/knowledge_base_import.py extract UPSTREAM/data --out source.json`
2. **Batches:** `... batches source.json --out-dir batches/`
3. **Translate** every batch by the rules in `docs/knowledge-base-translation.md`,
   writing `batches/<batch>.out.json`.
4. **Merge:** `... merge source.json batches/ --out translated.json` - exits non-zero and
   lists every record that breaks a rule; fix those batches and merge again.
5. **Structure batches:** `... structure-batches translated.json --out-dir structure/`
6. **Structure** every batch by the rules in `docs/knowledge-base-structure.md`, writing
   `structure/<batch>.out.json`.
7. **Structure:** `... structure translated.json structure/ --out structure.json` - checks
   every star and every question type, and derives the stars' prerequisites.
8. **Manifest:** `... manifest translated.json structure.json --out-dir manifests/
   --source-version <commit>` writes `manifest-NNN.json` (40 draft practice sets each),
   `report.json`, and the two committed files.
9. **Commit and deploy the two files** - the dry run checks every exercise's skill
   against the deployed vocabulary.
10. **Seed the stars:** `uv run python scripts/seed_practice.py --knowledge-base` writes the
    stars and nebulae in preview: hidden from students, there for the drafts to name.
    Run it with `--dry-run` first: that prints the seed hash and writes nothing.
11. **Dry run and apply** each manifest through `POST /admin/curriculum/migrations/dry-run`
    and `.../apply`. Every practice set becomes a draft; nothing is published.
12. **Review** the drafts in the curriculum workflow. The licence permission is in
    (see **Licence** above), so the reviewed practice sets can be published with
    `scripts/publish_curriculum_drafts.py`, which makes the submit-review, approve and
    publish calls for every draft of the manifests, under your own admin session (its
    access token in `STOA_ADMIN_TOKEN`):

    ```
    uv run python scripts/publish_curriculum_drafts.py dry-run --base-url https://api.stoaedu.ch --manifest manifests/ --report plan.json
    uv run python scripts/publish_curriculum_drafts.py apply --base-url https://api.stoaedu.ch --manifest manifests/ --confirm confirm_...
    ```

    The session needs the author, reviewer and publisher capabilities; each call is
    checked as if made by hand. The dry run changes nothing: it lists every practice set
    with the steps it still needs, or why it stays (already published, a reviewer asked
    for changes, blocking validation issues), and prints a confirmation code for that
    list. `apply` takes the code, plans again and refuses if the list changed. `--only` and
    `--exclude` take a file of publicLessonIds, one per line, to publish part of the
    import; `--migration ID` names a migration instead of its manifest. The first refused
    or failed call stops the run and says where (an access token that expired, a stale
    published version); run the dry run again and apply its new code to go on - published
    sets are skipped, and a set left in review or approved continues from there.
13. **Go live:** `seed_practice.py --knowledge-base-live` writes the stars and nebulae
    active, and the English and physics subjects with them.
14. **Prerequisites:** both seed options write the stars' prerequisites, drawn from the
    upstream edges between knowledge points with every cycle left out; the unit rows
    are the only place the runtime reads them (stoa-backend#317). A prerequisite no
    longer locks a star (stoa-backend#125).

### Running the seed again

`seed_practice.py` updates its rows field by field instead of replacing them: it
SETs the fields it owns (`SEED_OWNED_FIELDS`), REMOVEs the owned fields a row no
longer has a value for, and leaves every other field alone. The star map positions
`scripts/layout_starmap.py` writes onto the same subject, topic and unit rows are
among those, so a re-run keeps the map where it was and needs no new layout; only
stars the run adds need `layout_starmap.py --apply`. The seed is the only writer of
the curriculum structure and its prerequisites - there is no admin route that edits
them - so a change goes into the repository and is seeded.

When every row is written, the seed records `seed_hash` (sha256 over every field it
owns, rows sorted by key), `seeded_at`, the `git_commit` it ran from and `git_dirty`
(uncommitted changes), with the knowledge base flags it ran with, in the row
`PK=PRACTICE, SK=CURRICULUM_SEED`. `--dry-run` prints the hash it would record, and
`--print-hash` prints only that hash, needing no AWS access: run it with the same
flags to check whether the table still holds what the repository seeds.
