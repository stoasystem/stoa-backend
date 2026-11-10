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

This is the full computation: the first layout of a subject, and `--relayout`.
Once stars are placed, the default run keeps them and places only new ones
(see "Stability rules").

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

These are what keep an existing map from jumping when content changes. Students
learn where their stars are, so a star that is on the map stays where it is
unless someone asks, by name, for the whole map to be recomputed
(stoa-backend#376).

### Default: keep the placed stars

Without `--relayout` the script runs in **keep-placed** mode (`--keep-placed`
names it explicitly; it is the default for both the report and `--apply`):

1. **A placed star does not move.** A unit row with `x`, `y` and a `nebula_id`
   that is still its topic keeps all three, and its `layout_version`, digit for
   digit. Its row is not written at all.
2. **A placed nebula does not move.** A topic row with `x`, `y` and `radius` keeps
   its centre. Its radius only grows, and only when it gains stars.
3. **A new star goes into the first free slot of its nebula's spiral.** The
   spiral is the one a full layout draws (rule 4 of "How it is computed"), and
   because the radius grows with the square root of the count, the n-th slot
   sits `STAR_FILL * NEBULA_RADIUS_PER_STAR * sqrt(n)` raw units from the centre
   whatever the count: a slot does not move when the nebula grows. Slots are
   tried innermost first; one that is closer than `STAR_MIN_GAP` (0.5 raw units,
   the spacing a full spiral keeps) to any star already in the nebula is skipped.
   So new stars land after the stars that are there, whatever their `order`. A
   star whose lessons went dark keeps its row and its slot, so it comes back to
   the same place. The nebula's radius becomes the larger of its stored radius,
   `NEBULA_RADIUS_PER_STAR * sqrt(stars)` and what its outermost star needs.
   A new star's skill points get the offsets a full layout would give them; a
   skill point already placed keeps its position.
4. **A new nebula finds a centre without moving any other.** A topic with no
   position gets the point nearest the nebulae it shares prerequisite edges with
   (the middle of the map when it has none), searched on a
   `CENTRE_GRID_STEPS` grid over the frame, where its whole disc fits in `[0, 1]`
   and it keeps `NEBULA_CLEARANCE` from every placed nebula, including dark ones.
   Its raw centre is added to `starmap_layout.nebula_centres`.
5. **The frame and `layout_version` stay.** New positions are in the stored frame
   (`starmap_layout.transform`); the version is not raised.
6. **What does not fit is not forced.** If a nebula would grow to within the
   clearance of a neighbour, a new nebula has no free space, or a point would
   leave the frame, the script names the nebula and the stars that do not fit,
   says `--relayout` is needed, **writes nothing** and exits 1. It never falls
   back to a full recompute on its own.
7. **Rows that carry positions with no layout record are refused.** If unit or
   topic rows have positions but the subject row has no `starmap_layout` for the
   current seed, new stars cannot be put in the same frame; the script asks for
   `--relayout` and writes nothing.

When nothing of the subject is placed yet (the first layout), keep-placed has
nothing to keep and computes the whole map, as `--relayout` would.

Re-running is idempotent in this mode too: a second run finds every star placed
and writes nothing.

### `--relayout`: recompute the whole map

`--relayout` recomputes every nebula centre, the frame and every star from
scratch, exactly as the script did before #376: nebula placement, radii, spiral
and normalisation as in "How it is computed", with units in `(order, unit_id)`
order. **Every star can move.** It raises `layout_version` and writes
`relayout_reason`. Use it on purpose, when keep-placed reports that the new
stars do not fit, or when the map is to be redrawn.

Re-run the script after a curriculum change that adds stars; the result belongs
in the seed and migration checklist. Re-running `scripts/seed_practice.py` alone
does not move anything: the seed updates only the fields it owns and never writes
the position fields above (stoa-backend#352).

## Running it

```bash
python scripts/layout_starmap.py                        # report only, writes nothing
python scripts/layout_starmap.py --apply                # keep placed stars, place new ones
python scripts/layout_starmap.py --relayout             # report a full recompute
python scripts/layout_starmap.py --relayout --apply     # recompute and move every star
```

Default is report only, and the report shows what `--apply` would write; it exits
1 when the new stars do not fit. `--subject` defaults to `math`, which is the
subject the seed writes as `mathematics`: subjects are compared by
`curriculum_service.subject_key`, which maps the alias. The table and region come
from the application settings, so `DYNAMODB_TABLE_NAME` and `AWS_REGION` select
which table is read and written.

Skill rows are stoa-backend#58 and may not exist yet. When there are none, the
layout is computed and written without them; it is not an error.

Tests: `tests/test_starmap_layout.py`.
