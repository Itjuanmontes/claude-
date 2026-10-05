# Solicitation email fields: port, fixes, audit

## Goal
Every notification email or invitation shows all 8 rows in Muse's format:

```
Agency        Dept. of Defense — Army / USACE Baltimore
Solicitation  W912DR26QA057
Posted        Sep 28, 2026
Deadline      Oct 9, 2026 · 11:00 AM ET
NAICS         238160
Set-aside     Total Small Business Set-Aside
Place         Fort Meade, Maryland 20755
POC           Michael Getz
              · michael.j.getz@usace.army.mil
              · (540) 761-4935
```
Checked byte-for-byte by `test_w912dr26qa057_all_fields`.

## Files
| File | Purpose |
|---|---|
| `solicitation_fields.py` | `extract_fields(record)` → the 8 fields; `render_html()` / `render_text()` email blocks |
| `sam_enrich.py` | Backfills missing fields from the SAM.gov API by notice ID (`SAM_API_KEY` env var) |
| `audit_fields.py` | `python3 audit_fields.py records.json` reports the missing-field rate per field |
| `lead-magnet/build_contacts.py` | Muse contact builder, with deadline parsing fixed |
| `lead-magnet/invitation_docx.py` | Muse invitation .docx; Job details now use `extract_fields` |
| `test_solicitation_fields.py` | 11 tests, no dependencies: `python3 test_solicitation_fields.py` |

`extract_fields` accepts a raw **SAM.gov Opportunities API v2** record, a **lead-magnet bid**, or a bid backfilled with `sam_record` (the SAM data takes priority).

## Run order (Muse)
```bash
python3 lead-magnet/build_contacts.py Filtered_Leads.xlsx            # → lead-magnet-contacts.json
SAM_API_KEY=xxxx python3 sam_enrich.py lead-magnet-contacts.json      # backfill NAICS/set-aside/place/posted
python3 audit_fields.py lead-magnet-contacts.json                     # check coverage
python3 lead-magnet/invitation_docx.py lead-magnet-contacts.json out/ # generate invitations
```

## Wiring into govcontract-engine
```python
from solicitation_fields import extract_fields, render_html, render_text
fields = extract_fields(opportunity)          # SAM.gov record
html_block, text_block = render_html(fields), render_text(fields)
if fields["_missing"]:
    log.warning("%s missing %s", opportunity.get("solicitationNumber"), fields["_missing"])
```
Rows are never dropped. A missing value renders as `Not specified`.

---

## Audit results (real data: 140 contacts, 266 live invitations, 72 unique open opportunities)

### Old vs. fixed invitation Job details, on all 266 live invitations
| Field | Changed | Example (old → fixed) | Verdict |
|---|---|---|---|
| Place | 244 | `IL` → `Not specified` | **Bug fixed.** 234 showed the *contractor's* state as place of performance |
| Owner / Agency | 266 | `ENERGY, DEPARTMENT OF — FERMILAB - DOE CONTRACTOR` → `Dept. of Energy — Fermilab - DOE Contractor` | Formatting |
| Posted / NAICS / Set-aside | 266 | row missing → row present | **Rows added** (they were never in the docx) |
| Official POC | 40 | `6308403207` → `(630) 840-3207` | Formatting |
| Solicitation | 3 | `B107.500-2010` (an ASME standard), `MD1822AG` (a building code), `N68335-26-RFPREQ-BLG0000-` (truncated) → `Not specified` | **False positives removed** |
| Bids due | 2 | `Nov 30, 2027 · 11:59 PM CT` → `11:59 PM ET` (source said EST) | **DST bug fixed** |
| | | `Oct 12 · 1:00 PM CT` → `2:00 PM ET` (Ayer, MA) | Same instant, now in the place's local time |

The old regex fallback did catch one real number: `W911S223S8000`. The fixed code keeps it with a standard federal solicitation-number (PIID) pattern, so nothing real is lost.

### Coverage on the 72 open opportunities, before SAM backfill
| Field | Filled |
|---|---|
| Agency, Deadline, POC | 72/72 |
| Solicitation | 21/72 |
| Place | 9/72 |
| NAICS | 9/72 |
| Posted, Set-aside | 8/72 |

**Root cause:** Muse only scraped full SAM details for about 9 opportunities. `sam_enrich.py` fixes this by pulling the full record for every sam.gov URL; all 72 have one. It still needs to be run with your key. In tests it's checked against a mocked API only (`test_sam_enrich_backfills_missing_fields`).

### Bugs fixed
| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `build_contacts.py` | The timezone label came from the offset (`-05:00` = CT always), so ET deadlines after Nov 1 read **CT** | DST-aware `zoneinfo` |
| 2 | `build_contacts.py` | Naive deadlines were treated as **UTC**: time and `expired` were off by 4–5 h | Treated as Eastern (SAM.gov convention) |
| 3 | `build_contacts.py` | Date-only deadlines expired at 00:00 UTC, the evening before the due date | Open until 11:59 PM ET that day |
| 4 | `build_contacts.py` | Deadline parsed twice; module-level code ran on import with a hard-coded path | One parser; `main(xlsx)` / `build(rows, now)` |
| 5 | `invitation_docx.py` | Place fell back to the **contractor's** state | Falls back to `Not specified` |
| 6 | `invitation_docx.py` | Posted, NAICS, Set-aside rows missing | Rows added |
| 7 | `invitation_docx.py` | Loose solicitation regex matched standards and building codes | Explicit label match or PIID only |
| 8 | both | Raw phones and agency casing; FAR citation kept on set-aside; first POC used, not primary | Normalized; `type == primary` preferred |

### Bugs found in my own first-pass module (also fixed)
- An empty POC entry (`pointOfContact: [None]`) crashed `extract_fields`.
- SAM-style strings (`Oct 06, 2026 5:00 PM CDT`) passed through unformatted.
- Muse places kept the state abbreviation (`East Orange, NJ`) instead of the full name.
- An award's `date_signed` was shown as **Posted**.
- Agency casing was mangled (`245-NETWORK`, `Jacksonville Fl`).
- Deadlines without a place state were all converted to ET. They now keep local time: the zone is picked by matching the offset on that date.

### Still open
- **govcontract-engine source isn't available here.** Wire it in with the snippet above, and make sure its SAM fetch keeps `pointOfContact`, `placeOfPerformance`, `typeOfSetAsideDescription`, and `fullParentPathName`.
- `sam_enrich.py` searches notices posted in the last 364 days, the API's maximum window. Older notices come back as `not_found`.
- Not end-to-end tested: `build_contacts.py` against the real `Filtered_Leads.xlsx` (not in the upload). It's unit-checked with synthetic rows instead.
