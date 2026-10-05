# Solicitation email fields: port + audit

## Goal
Every notification email from govcontract-engine shows all 8 rows, in the same format Muse (lead-magnet) uses:

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

`test_solicitation_fields.py::test_w912dr26qa057_all_fields` checks this exact output.

## What's in this repo
| File | Purpose |
|---|---|
| `solicitation_fields.py` | `extract_fields(record)` → 8 normalized fields; `render_html()` / `render_text()` for the email body |
| `test_solicitation_fields.py` | 8 tests (run with `python3 test_solicitation_fields.py`, no dependencies) |
| `audit_fields.py` | `python3 audit_fields.py records.json` reports how often each field is missing |

`extract_fields` takes either a **raw SAM.gov Opportunities API v2 record** (`solicitationNumber`, `fullParentPathName`, `postedDate`, `responseDeadLine`, `naicsCode`, `typeOfSetAsideDescription`, `placeOfPerformance`, `pointOfContact[]`) or a **lead-magnet bid dict** (`solicitation`, `poc_*`, `sam{}`, `enriched{}`).

## Wiring into govcontract-engine
At the point where the engine builds the email for an opportunity:

```python
from solicitation_fields import extract_fields, render_html, render_text

fields = extract_fields(opportunity)   # the SAM.gov record as returned by the API
html_block = render_html(fields)       # drop into the HTML body
text_block = render_text(fields)       # drop into the plain-text part
if fields["_missing"]:
    log.warning("email %s missing %s", opportunity.get("solicitationNumber"), fields["_missing"])
```

Rows are **never dropped**. A missing value renders as `Not specified`, so a gap shows up in the email instead of the row silently disappearing.

## Audit: Muse (lead-magnet) source
Data: `lead-magnet-contacts.json`, 140 contacts, 132 unique bids (72 open opportunities, 60 prime-award leads).

### Field coverage on the 72 open opportunities
| Field | Filled | Note |
|---|---|---|
| Agency | 72/72 | |
| Deadline | 72/72 | |
| POC | 72/72 | |
| Solicitation | 20/72 | 52 have `solicitation: null` |
| NAICS | 9/72 | only stored when the SAM detail page was scraped |
| Place | 9/72 | same |
| Set-aside | 8/72 | same |
| Posted | 8/72 | same |

**Muse only produces the full 8-field block for about 9 of 72 opportunities.** The W912DR26QA057 example worked because it was one of the records with a full SAM detail fetch. NAICS, set-aside, place, and posted date all come with the SAM.gov API record. govcontract-engine should read them from that response (this module does), not from a scraped `sam{}` sub-dict.

### Bugs found in Muse (fixed in the port)
| # | Where | Bug | Fix |
|---|---|---|---|
| 1 | `build_contacts.py` `TZ_ABBR` | The timezone label comes from the UTC offset: `-05:00` is always `CT` and `-04:00` is always `ET`. After DST ends (Nov 1, 2026), an Eastern deadline at `-05:00` gets labeled **CT**. Arizona `-07:00` gets labeled `PT`. | DST-aware `zoneinfo` conversion into the place of performance's state zone |
| 2 | `build_contacts.py` | Naive deadlines are assumed to be **UTC**. SAM naive times are Eastern, so the displayed time is off by 4 to 5 hours. | Naive is treated as Eastern |
| 3 | `invitation_docx.py` `Place` | Falls back to the **contractor's** state (`contact['state']`) when SAM has no place, which shows the wrong place of performance. Hits 63/72 opportunities. | Falls back to `Not specified` |
| 4 | `invitation_docx.py` `extract_solicitation` | The loose "any mixed alphanumeric token" fallback takes VA project numbers (e.g. `Z2DA--561-26-104`) as the solicitation number | Fallback removed; only an explicit `Solicitation/RFQ/RFP/IFB No.` match is used |
| 5 | `clean_agency` | Leaves raw SAM casing (`ENERGY, DEPARTMENT OF`) and doesn't shorten the path | Formats as `Dept. of X — Sub / Office`, with USACE district handling |
| 6 | POC phone | Passed through raw (`6308403207`, `7088902524.0`) | Formatted as `(630) 840-3207`, extensions kept as `x202046` |
| 7 | Set-aside | Keeps the FAR citation (`… (FAR 19.14)`), unlike the target format | Citation stripped; also falls back from `typeOfSetAside` codes (SBA, 8A, SDVOSBC…) |
| 8 | `deadline_iso` | Some records store a date-only ISO (`2026-11-04`) next to a timed display string, so deadline math such as `days_left` and `expired` runs on midnight UTC | The module prefers a timed source and only falls back to the display string |
| 9 | POC selection | Takes the first POC only, with no primary/secondary check | Prefers `type == "primary"` |

### Still open (needs govcontract-engine source)
- I haven't read govcontract-engine's email template or SAM fetch code. Once it's on GitHub, check that the fetch keeps `pointOfContact`, `placeOfPerformance`, `typeOfSetAsideDescription`, and `fullParentPathName`. Some SAM search calls return a trimmed record.
- `AGENCY_ALIASES` covers DoD, USACE, and the common civilian departments. Add any other agencies that show up in real sends.
