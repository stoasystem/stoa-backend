# The starmap layout

stoasystem/stoa-backend#60, decided in stoasystem/stoa-frontend#72 (2026-09-28).

A subject is a **starmap**, a topic is a **nebula**, a unit is a **star** in that
nebula, and a skill point is a speck beside its star. The frontend only renders:
it runs no force layout and computes no coordinates. Every position it draws is
read from the table, computed offline by `scripts/layout_starmap.py`.

The sphere is gone. There is no `lat`, no `lng`, no equal-area inverse projection
and no spherical cap packing; #72 retired all of it on 2026-09-28.

## What is written

| Row | Attributes |
| --- | --- |
| `SUBJECT#<id>` | `layout_version`, `starmap_layout` |
| `TOPIC#<id>` | `x`, `y`, `radius`, `layout_version` |
| `UNIT#<id>` | `x`, `y`, `nebula_id`, `layout_version` |
| `SKILL#<id>` | `x`, `y`, `layout_version` |

`x` and `y` are in `[0, 1]`, and a nebula's `radius` is in the same normalised
frame, so a star's distance from its nebula centre can be compared to it
directly. `nebula_id` is the unit's `topic_id`.

`starmap_layout` on the subject row is the layout record: the version, the seed,
the number of digits coordinates were rounded to, why the layout was last
recomputed, the normalising transform, and the **raw** (un-normalised) nebula
centres. It is what makes an incremental re-run possible; nothing else stores the
raw frame.

## How it is computed

1. **Input.** Topics, units and lessons for the subject. A unit with **zero
   active lessons is not laid out**, and a topic left with no unit gets no
   nebula. Topics are sorted by `(order, topic_id)` and units by
   `(order, unit_id)` *before* anything is computed.
2. **Nebula placement.** The nebula graph has one edge per pair of topics that
   prerequisite edges cross, weighted by how many cross (`prerequisite_unit_ids`,
   stoa-backend#56). A heavier link is a shorter target edge; every other pair
   gets the shortest path through the graph, and pairs with no path at all are
   pushed out to `UNRELATED_SPREAD` times the longest distance the graph did
   constrain. Those targets are fitted by **stress majorisation (SMACOF)** from a
   seeded ring. Before #56 lands there are no edges at all; every pair then gets
   the same target and the map is still deterministic and still non-overlapping.
3. **Radii and clearance.** A nebula's radius is
   `NEBULA_RADIUS_PER_STAR * sqrt(stars)`, so star density is the same
   everywhere. A separation pass then pushes every pair apart until their centres
   are at least `NEBULA_CLEARANCE * (r_a + r_b)` apart. The part of
   `NEBULA_CLEARANCE` above 1.0 is the growth headroom.
4. **Stars.** A golden-angle spiral inside the nebula: even, never a grid. The
   n-th star sits at `radius * STAR_FILL * sqrt(n / count)`, so the first unit of
   a topic is at the centre and the last at the rim.
5. **Skill points.** A small golden-angle offset around the star of the unit the
   skill belongs to.
6. **Normalisation.** One uniform scale and shift puts the whole raw layout
   inside `[0, 1]`, with padding and growth headroom around it, and coordinates
   are rounded to `COORD_DIGITS`.

## Determinism

Same input, same output, digit for digit:

- Input is sorted before it is laid out, so the order the table hands rows back
  cannot move a star.
- The one random draw — the jitter that breaks the symmetry of the initial ring —
  comes from `random.Random(SEED)` with `SEED` fixed in the script.
- Per-topic spiral phases come from a BLAKE2b digest of the topic id, never from
  `hash()`, which is salted per interpreter and would differ between two runs of
  the same script.
- SMACOF runs a fixed number of iterations from a fixed start: no step size, no
  cooling schedule, no convergence test.
- Coordinates are rounded before they are compared or written, so a re-run
  produces no writes at all. **Re-running is idempotent.**

## Stability rules

These are what keep an existing map from jumping when content changes.

1. **Nebula centres carry over.** The stored raw centres and the stored
   normalising transform are reused. They are recomputed only when the set of
   topics changes (a topic added or removed), when `--relayout` is passed, or
   when carrying them over would break a rule (below).
2. **A unit change re-spirals one nebula.** Adding or removing a unit changes the
   stars and skill points of that nebula, and its radius. Every other nebula's
   centre, radius and stars come out identical.
3. **A change in cross-topic prerequisite counts does not move anything.** It
   only changes the nebula links the read model draws (stoa-backend#59
   `links[]`).
4. **The frame is not recomputed per run.** The scale and shift are fixed when
   the layout is recomputed in full and stored in `starmap_layout`. Normalising
   to the current bounding box each time would shift the whole map whenever one
   star appeared.
5. **Growth escalates to a full recompute.** If a nebula grows past its clearance
   with a neighbour, or past the stored frame, the incremental result is
   discarded, the layout is recomputed in full, `layout_version` goes up, and the
   reason is written to `starmap_layout.relayout_reason`.

Re-run the script after a curriculum change; the result belongs in the seed and
migration checklist.

## Running it

```bash
python scripts/layout_starmap.py                 # report only, writes nothing
python scripts/layout_starmap.py --subject math
python scripts/layout_starmap.py --relayout      # recompute every nebula centre
python scripts/layout_starmap.py --apply         # write the rows
```

Default is report only. The table and region come from the application settings,
so `DYNAMODB_TABLE_NAME` and `AWS_REGION` select which table is read and written.

Skill rows are stoa-backend#58 and may not exist yet. When there are none, the
layout is computed and written without them; it is not an error.

Tests: `tests/test_starmap_layout.py`.
