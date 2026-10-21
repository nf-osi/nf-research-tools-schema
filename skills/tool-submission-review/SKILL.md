---
name: tool-submission-review
description: >
  Ad hoc workflow for turning a Formspark tool-submission export (or any
  one-off/manually-reported tool) into a submissions/ PR, without waiting
  for the scheduled monthly-submission-check.yml issue. Covers running
  process_formspark_export.py, reviewing/fixing the generated JSON,
  linking a tool's developer to a Synapse investigator profile (and to
  other tools by that investigator), and opening the PR. Use when asked
  to process a Formspark export JSON, review files already sitting in
  submissions/{type}/, or link a developer/investigator across tools.
---

# Tool submission review (ad hoc)

This repo has two scheduled pipelines that both land new tools as JSON
files in `submissions/{type}/` for review, then upload on merge via
`upsert-tools.yml`:

| Workflow | Source of tools |
|---|---|
| `publication-mining.yml` | LLM-mined mentions in NF publications |
| `monthly-submission-check.yml` | Formspark form (`KwZ46H4T`) submissions + Synapse annotation review, opens a **"Monthly Tool Submission Check"** issue on the 1st of each month |

This skill is for doing the `monthly-submission-check.yml` Formspark
steps **by hand in a live session** — e.g. a "Monthly Tool Submission
Check" issue is already open and you have (or are given) an export file,
or someone reports a tool outside the monthly cycle. It reuses the same
script and the same review conventions the scheduled issue documents, so
work here still closes out that issue's checklist normally.

## Steps

### 1–3. Get the export

Formspark dashboard → form `KwZ46H4T` → select new entries since the
last issue closed → **Export → JSON**. If the user already dropped an
export file in the repo (e.g. directly under `submissions/`), that's
this step already done — treat that file as *input only*, never commit
it (see Privacy below).

### 4. Convert

```bash
python tool_coverage/scripts/process_formspark_export.py path/to/export.json --dry-run
```

Always dry-run first and read the per-submission console output before
writing — it tells you the detected tool type/name and prints fields
that need manual handling (description/synonyms, vendor info, an
`otherInformation` catch-all note). Then drop `--dry-run` to actually
write into `submissions/{type}/`.

**Script behavior worth knowing** (some of this needed fixing 2026-09-09
against a real export — check `git log -- tool_coverage/scripts/process_formspark_export.py`
if something here seems out of date):

- Raw Formspark export items are `{id, formId, data: {...}, createdAt, spam}`
  — the script unwraps `data` automatically so `basicInfo.*`/`userInfo`
  lookups work; `spam: true` entries are skipped automatically.
- `contactEmail` / `developerContactEmail` are stripped from the output
  JSON (submitter's private contact info, never committed) — but
  `developerName` / `developerAffiliation` are **kept**. Those two are
  the tool's public developer credit, not the submitter's identity, and
  feed investigator linking (see below) — don't strip them.
- An **observation**-type submission (the general "report an
  observation about an existing tool" form,
  `NF-Tools-Schemas/observations/SubmitObservationSchema.json`) can
  contain multiple `observationsSection.observations[]` entries. The
  script writes one file per observation into
  `submissions/{resourceType-mapped-subdir}/observations/`, matching
  the layout mined observations already use (see `submissions/README.md`).
  Submitter `first_name`/`last_name` are kept on the record (used as
  `observationSubmitterName` by `compile_accepted_submissions.py`,
  falling back to "Anonymous") — email/institution are not.
- The issue template's "Tool forms currently active on nf.synapse.org"
  note can lag reality — computational-tool and observation submissions
  have come through the same form even when that note only lists cell
  line/animal model/antibody/genetic reagent. Don't treat that note as a
  hard filter on what `_detect_tool_type` should accept.

### 5–6. Review and edit

For each new file in `submissions/{type}/` (and `submissions/{type}/observations/`):

- Clean up obvious copy/paste artifacts from the form (trailing periods
  on DOIs, a stray citation number appended to a `referencePublication`
  like `"doi.org/10.xxxx/yyy 30."`) — check the DOI resolves before
  trusting it as-is.
- Check for duplicates: grep the tool name against
  `tool_coverage/outputs/VALIDATED_*.csv` and existing
  `submissions/{type}/*.json` before keeping a file. A submission that
  matches an *existing* tool but adds new context (e.g. someone
  reporting an observation about a tool that's already mid-review in
  `submissions/`) is not a duplicate — it's additive, keep both.
- If a field is unknown, leave it blank per `submissions/README.md` —
  don't guess a developer's full name from a submitter's email address
  (never copy the address itself into the JSON or a PR either — see
  Privacy below). If a `developmentPublicationDOI` is given but
  `developerName` isn't, don't leave it blank by default — pull up that
  publication and use its point of contact (typically the last-listed
  author) as the investigator; see Investigator linking below.
- Delete the file entirely for anything that shouldn't be added.

### Investigator linking

`developerName` is how a tool's investigator gets into the registry
(`syn26486833` via `upsert_publication_links.py`'s `upsert_investigators()`).
Useful facts:

- **Multiple developers are supported**: a semicolon-separated
  `developerName` ("Alice; Bob") is split into separate Investigator
  rows, each linked to the resource through the dev-links table
  (`syn26486807`). Don't leave a placeholder like `"Many"` — either name
  the actual co-developers if you know them, or name the one you can
  identify (the submission's contact/PI) and leave a `_curatorNote`
  (an underscore-prefixed field, ignored by the compiler, same pattern
  as `_source`/`_confidence`) explaining the rest are unconfirmed.
- **No `developerName` but a `developmentPublicationDOI` is given**:
  use that publication's point of contact — typically the last-listed
  author — as the investigator rather than leaving the field blank.
- To check whether a name already has a Synapse profile (rather than
  guessing), run:
  ```bash
  python tool_coverage/scripts/check_investigator_synapse_ids.py
  ```
  It scans all `submissions/**/*.json` for `developerName`, searches
  Synapse People Search, and writes
  `tool_coverage/outputs/investigator_synapse_id_report.csv`. No auth
  required. Run this for anyone landed via the publication point-of-contact
  rule above too, if they aren't already in the investigator table.
  If you already have a Synapse profile URL/username from the submitter
  directly, just record it in `_curatorNote` — no need to search.
- To link an investigator to **other** tools already in (or pending
  into) the registry: grep their name, lab, and known projects/repos
  across `submissions/**/*.json` and `tool_coverage/outputs/VALIDATED_*.csv`.
  If nothing turns up, say so explicitly in the PR — don't assume a
  match exists just because the person is prolific.
- Once you have their name/username, also check studies/datasets
  associated with it — an investigator's Synapse footprint isn't limited
  to the registry's own tables. The NF-OSI project tracking EntityView
  `syn52677631` (see `nf-progress:synapse-projects`) has a `studyLeads`
  column that's a free-text name list, not a Synapse id, so match by
  name rather than `createdBy`/ownerId:
  ```sql
  SELECT id, name, studyLeads FROM syn52677631 WHERE studyLeads LIKE '%<Last Name>%'
  ```
  A hit is a real candidate to cross-reference/link, not an automatic
  one — confirm the study's tool/data types actually connect to this
  resource before adding a link.

### Privacy

Never commit a raw Formspark export file — it's a list of Formspark
items containing submitter emails/names in `userInfo`/`contactEmail`.
Once `process_formspark_export.py` has written the per-tool JSON files,
delete the raw export (it's only ever local working input, same
principle as the "submitter contact info … never committed" note on the
monthly issue).

### 7–10. PR and close-out

```bash
git checkout -b tool-submissions-<date-or-topic>
git add submissions/... [tool_coverage/scripts/process_formspark_export.py if you fixed something]
git commit -m "..."
git push -u origin HEAD
gh pr create --label tool-submissions --title "..." --body "..."
```

- `git diff` before pushing should show only the expected new/edited
  `submissions/` files (plus any script fix) — nothing else.
- **Merging is outward-facing and hard to reverse**: `upsert-tools.yml`
  compiles and pushes straight to the live Synapse tables on merge to
  `main`. Stop at opening the PR and get the user's explicit go-ahead
  before merging it yourself.
- After merge, close the monthly "Tool Submission Check" issue (or
  check off its Formspark checklist items) if this session's work
  covers what it asked for.

Before doing ad hoc Synapse investigation or edits, check `scripts/`
and `tool_coverage/scripts/` and recent git log first — this repo
already has reusable tooling for most data-fix/lookup needs (this
skill's `check_investigator_synapse_ids.py` included). Never modify a
materialized view's `definingSQL` from code — always ask a human to do
that in the Synapse web UI.
