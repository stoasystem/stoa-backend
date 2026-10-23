# Importing the knowledge base

The knowledge base adapted from [cn-math-taxonomy](https://github.com/xiaoyang111222/cn-math-taxonomy)
brings 1821 knowledge points (mathematics from the first year of primary school to
upper secondary, English, physics), their prerequisite edges and a question bank.
It arrives as draft lessons in German with English, French and Italian translations,
one lesson per knowledge point, each knowledge point a skill under one star.

**Licence.** The upstream is CC BY-NC 4.0: no commercial use without the author's
permission. Nothing is published before that permission is in writing. The source
text and its translations stay out of the repository; only the skill vocabulary
(`src/stoa/services/knowledge_base_skills.json`, knowledge point names) is committed.

## What is left behind

The Chinese textbook records: chapter and unit numbers, semesters, curriculum
standard ids, edition mappings, id aliases and the upstream's review logs. Text that
attributes a convention to a textbook is rewritten as a convention, and the merge
step refuses any translation that still points at a textbook. Exercises with a
figure (practice shows no figures yet) and self-assessments are skipped and listed.

## Where it goes

`src/stoa/services/knowledge_base_catalog.py` holds the stars: new stars in the
seven mathematics nebulae for what the ZAP stars do not cover (functions, vectors,
probability, ...), and the English and physics nebulae. The translator files each
mathematics and physics knowledge point under one of the offered stars; English
points go by strand and school stage.

## Steps

All data files live outside the repository, e.g. in `.scratch/knowledge-base/`.

1. **Extract** from a checkout of the upstream:
   `uv run python scripts/knowledge_base_import.py extract UPSTREAM/data --out source.json`
2. **Batches:** `... batches source.json --out-dir batches/`
3. **Translate** every batch by the rules in `docs/knowledge-base-translation.md`,
   writing `batches/<batch>.out.json`.
4. **Merge:** `... merge source.json batches/ --out translated.json` - exits non-zero and
   lists every record that breaks a rule; fix those batches and merge again.
5. **Manifest:** `... manifest translated.json --out-dir manifests/ --source-version <commit>`
   writes `manifest-NNN.json` (40 draft lessons each), `report.json`, and the skill
   vocabulary into `src/stoa/services/knowledge_base_skills.json`.
6. **Commit and deploy the vocabulary** - the dry run checks every exercise's skill
   against the deployed vocabulary.
7. **Seed the stars:** `uv run python scripts/seed_practice.py --knowledge-base` writes the
   new stars and nebulae in preview: hidden from students, there for the drafts to name.
8. **Dry run and apply** each manifest through `POST /admin/curriculum/migrations/dry-run`
   and `.../apply`. Every lesson becomes a draft; nothing is published.
9. **Review** the drafts in the curriculum workflow. Once the licence permission is in
   writing, publish the reviewed lessons.
10. **Prerequisites:** `report.json` lists `prerequisitesForLater`, the upstream's
    prerequisite edges between lessons of one star or nebula. A lesson prerequisite
    must name an existing lesson, so they are set on drafts after the lessons they
    name are published.
11. **Go live:** once the lessons are published, `seed_practice.py --knowledge-base-live`
    writes the stars and nebulae active, and the English and physics subjects with them.
