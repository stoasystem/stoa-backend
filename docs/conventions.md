# Conventions

How code in this repository is usually written. Moved from the old `.planning/codebase/CONVENTIONS.md` (#433) after checking each point against the code; the domain vocabulary lives in `CONTEXT.md`, not here.

## Python style and typing

- Ruff is configured in `pyproject.toml` for a 100-character line length and Python 3.12. `ruff check src tests` must pass.
- Imports group standard library, third-party, then `stoa`. Most modules open with a docstring saying what they are for.
- Modern annotations (`str | None`). Pydantic models define most public request and response schemas; a few broad or evolving contracts still use plain `dict` values.
- Repository helpers usually return `dict | None` or `list[dict]`.

## FastAPI and dependencies

- Each route module owns an `APIRouter`; `src/stoa/main.py` is where they are attached.
- Authenticated endpoints use dependencies such as `Depends(get_current_user)` and exact role or capability dependencies, not authentication inside the handler.
- Configuration has two access paths (#359): a service takes `settings` as a parameter, or calls `config.settings()` when it needs a value; routes use `Depends(config.settings)`. Nothing reads configuration at import (except `main.py` building the app). Tests use `config.install(Settings(...))` or pass settings in, never `monkeypatch.setattr` on a settings object; `tests/test_config_access.py` gates this.
- AWS clients come from `stoa.aws.client(Kind.X)` (#358), except DynamoDB, which goes through `stoa.db.table`; tests install doubles with `aws.install` / `db_table.install`.
- The roles are student, parent, teacher and admin (`stoa.models.user.UserRole`). Public registration creates only students and parents; teachers and admins are activated through separate reviewed flows.

## DynamoDB and time

- One table, with `PK`/`SK` values composed by hand. Repositories build keys with `Key`/`Attr` and updates with explicit `UpdateExpression` strings, mapping reserved names through `ExpressionAttributeNames`.
- Query by key or GSI where one exists; some admin aggregates still scan.
- Timestamps are stored as ISO strings in UTC. Tests use injected or frozen clocks.

## Errors and public contracts

- Route validation and authorization failures raise `HTTPException`; provider `ClientError` values are normalized before they reach a client.
- Unknown provider failures become generic dependency failures. Provider codes, payloads, tokens and internal diagnostics never appear in public responses.
- `docs/security/client-error-actions.json` is the checked registry of client actions for HTTP statuses: safe copy, retry policy and correlation-ID handling.
- Non-critical AI or AWS side effects may catch broad exceptions and carry on; tests then assert the side effect and the log, so the branch cannot hide a regression.
- API responses use camelCase for clients; Python internals use snake_case.
- Privacy-sensitive public models use `ConfigDict(extra="forbid", populate_by_name=True)` with explicit camelCase aliases. Attachment responses expose opaque IDs and safe metadata only; practice previews and answer-bearing results are separate allowlisted schemas.
- Active contracts say teacher, never tutor.

## Generated contracts and drift checks

- Route authorization is projected into `docs/security/route-authorization-inventory.json`, client failure behaviour into `docs/security/client-error-actions.json`, and the API into `docs/api/openapi.json`.
- Generators are deterministic. After changing what they read, regenerate and commit, then make sure `scripts/generate_openapi_snapshot.py --check`, `scripts/generate_route_authorization_inventory.py --check` and `scripts/generate_client_error_actions.py --check` pass.
- Generated JSON changes only through its generator, never by hand.

## Repository hygiene

- `.env.example` is tracked; real `.env` files are ignored.
- The repository is LF with `core.autocrlf=false`; Python that writes files passes `newline="\n"`.

## Adding a data type

Every kind of row the code writes has one entry in the data type catalog, `src/stoa/db/data_catalog.py` (#586). When you add a new `entity_type` - or a writer starts putting a new attribute that holds an account id on an existing one - give its entry three things:

- **The account pointers**: every place the row names an account (`Field`, `Ids`, `Summaries`, `KeyId` for an account in the key, `ScopeId`), each with its role: `owner` when deleting that account removes or tombstones the row, `reference` when it only scrubs the name out. A type that points to no account declares `accounts=()`. An attribute that looks like an account id but is deliberately not handled (an administrator's `updated_by`) goes in `not_pointers`, with its reason.
- **The deletion handling**: the `deletion` slot, empty until candidate I fills it (see #586).
- **The owning module**: where its rows are written.

Nothing else decides which accounts a row names: read it through `data_catalog.mentions` / `names` / `owns` / `role_of`, not a field list of your own. Account deletion does (#588): every deletion scan asks the catalog whose a row is and keeps only its own choice of which kinds it handles and how, so a row the catalog does not know is one no deletion takes. So does the owner registry (#589): a write registers its partition under every account the catalog says its rows name, and under nobody else. A row written without an `entity_type` is matched by its key (`UNTYPED`); prefer giving new rows an `entity_type`.

Write such rows through `db_table.fenced` (behind the owner's account fence) or, when there is no fence to hold, `db_table.registered`; never register by hand. An Update that sets an account pointer passes the row as it will stand (`rows=`), or the write is refused before it is sent: the registry cannot see whom an Update makes the row name.

What fails if you don't:

- `tests/test_data_catalog.py`: a written `entity_type` with no entry, an entry nothing writes, an entry naming the wrong module, an account-looking attribute a writer writes that the entry neither declares nor lists in `not_pointers`, a writer whose fields the scan cannot read that is not in `FIELDS_READ_BY_HAND`, and a declared pointer the catalog does not read.
- `tests/test_account_deletion_branch_coverage.py`: the same `entity_type` with no deletion branch and no `KEPT` reason (#534).
- `tests/test_owner_registry_unfenced_writers.py`: a function that writes to the table without calling `db_table.fenced` or `db_table.registered`, unless it is listed with its reason.

The daily owner registry sweep (`stoa.services.owner_registry_sweep`) checks the stored rows against the same catalog: a missing registration or a leftover of a deleted account is a finding, and rows of a kind the catalog does not know are counted on their own line (`rows_unknown_to_catalog`).
