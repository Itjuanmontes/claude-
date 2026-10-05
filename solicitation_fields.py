"""Solicitation detail block for notification emails.

Ported from the lead-magnet (Muse) project: `build_contacts.py` (deadline
display, state names, TZ labels) and `invitation_docx.py` (solicitation
extraction, agency cleanup, POC line, "Not specified" for missing values).

Every email renders all 8 rows, in this order, even when a value is missing:

    Agency      Dept. of Defense — Army / USACE Baltimore
    Solicitation W912DR26QA057
    Posted      Sep 28, 2026
    Deadline    Oct 9, 2026 · 11:00 AM ET
    NAICS       238160
    Set-aside   Total Small Business Set-Aside
    Place       Fort Meade, Maryland 20755
    POC         Michael Getz
                · michael.j.getz@usace.army.mil
                · (540) 761-4935

Accepts either a raw SAM.gov Opportunities API v2 record or a lead-magnet
bid dict (with optional `sam` / `enriched` sub-dicts).
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MISSING = "Not specified"
FIELD_ORDER = ("Agency", "Solicitation", "Posted", "Deadline", "NAICS",
               "Set-aside", "Place", "POC")

STATE_NAMES = {'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia','PR':'Puerto Rico','GU':'Guam','VI':'U.S. Virgin Islands'}

# Primary IANA zone per state. Used to label deadlines in the place of
# performance's local time (DST-aware), instead of guessing from the UTC offset.
STATE_TZ = {
    **{s: 'America/New_York' for s in 'CT DE DC FL GA IN KY ME MD MA MI NH NJ NY NC OH PA RI SC VT VA WV'.split()},
    **{s: 'America/Chicago' for s in 'AL AR IL IA KS LA MN MS MO NE ND OK SD TN TX WI'.split()},
    **{s: 'America/Denver' for s in 'CO ID MT NM UT WY'.split()},
    'AZ': 'America/Phoenix',
    **{s: 'America/Los_Angeles' for s in 'CA NV OR WA'.split()},
    'AK': 'America/Anchorage', 'HI': 'Pacific/Honolulu',
    'PR': 'America/Puerto_Rico', 'VI': 'America/St_Thomas', 'GU': 'Pacific/Guam',
}
DEFAULT_TZ = 'America/New_York'
TZ_SHORT = {'EST': 'ET', 'EDT': 'ET', 'CST': 'CT', 'CDT': 'CT', 'MST': 'MT',
            'MDT': 'MT', 'PST': 'PT', 'PDT': 'PT', 'AKST': 'AKT', 'AKDT': 'AKT',
            'HST': 'HT', 'AST': 'AT', 'ChST': 'ChT'}

SET_ASIDE_CODES = {
    'SBA': 'Total Small Business Set-Aside',
    'SBP': 'Partial Small Business Set-Aside',
    '8A': '8(a) Set-Aside', '8AN': '8(a) Sole Source',
    'HZC': 'HUBZone Set-Aside', 'HZS': 'HUBZone Sole Source',
    'SDVOSBC': 'Service-Disabled Veteran-Owned Small Business (SDVOSB) Set-Aside',
    'SDVOSBS': 'Service-Disabled Veteran-Owned Small Business (SDVOSB) Sole Source',
    'WOSB': 'Women-Owned Small Business (WOSB) Set-Aside',
    'WOSBSS': 'Women-Owned Small Business (WOSB) Sole Source',
    'EDWOSB': 'Economically Disadvantaged WOSB (EDWOSB) Set-Aside',
    'EDWOSBSS': 'Economically Disadvantaged WOSB (EDWOSB) Sole Source',
    'VSA': 'Veteran-Owned Small Business Set-Aside',
    'VSS': 'Veteran-Owned Small Business Sole Source',
    'IEE': 'Indian Economic Enterprise (IEE) Set-Aside',
    'ISBEE': 'Indian Small Business Economic Enterprise (ISBEE) Set-Aside',
}

# Agency path segments -> short display names.
AGENCY_ALIASES = {
    'DEPT OF DEFENSE': 'Dept. of Defense',
    'DEPT OF THE ARMY': 'Army', 'DEPT OF THE NAVY': 'Navy',
    'DEPT OF THE AIR FORCE': 'Air Force',
    'US ARMY CORPS OF ENGINEERS': 'USACE',
    'DEFENSE LOGISTICS AGENCY': 'DLA',
    'NATIONAL AERONAUTICS AND SPACE ADMINISTRATION': 'NASA',
    'GENERAL SERVICES ADMINISTRATION': 'GSA',
    'PUBLIC BUILDINGS SERVICE': 'PBS',
}
ACRONYMS = {'US', 'USA', 'VA', 'NCO', 'DOE', 'GSA', 'PBS', 'NAVFAC', 'USACE',
            'NASA', 'NOAA', 'NIH', 'FBI', 'DHS', 'FAA', 'DLA', 'NPS', 'BIA',
            'IHS', 'USDA', 'HHS', 'HUD', 'DOJ', 'DOI', 'USFS', 'AFB', 'SOCONS',
            'NAS', 'MCB', 'CDC', 'ARS', 'FS', 'NRCS', 'II', 'III', 'IV'}

_PIID = re.compile(r'\b(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6}\d{2}[A-Z][A-Z0-9]{4}\b')
_FAR_SUFFIX = re.compile(r'\s*\(FAR\s[^)]*\)\s*$', re.I)
_OFFICE_CODE = re.compile(r'^(?=[A-Z0-9]*\d)[A-Z0-9]{4,6}\s+(?=\S)')  # "W2SD ENDIST BALTIMORE"


def _first(*vals):
    for v in vals:
        if isinstance(v, str):
            v = v.strip()
        if v not in (None, '', [], {}):
            return v
    return None


def _word(w: str, last: bool) -> str:
    bare = re.sub(r'[^A-Za-z0-9]', '', w)
    if bare.upper() in ACRONYMS or (re.search(r'\d', bare) and re.search(r'[A-Za-z]', bare)):
        return w.upper()                       # acronyms, codes like 36C245
    if last and bare.upper() in STATE_NAMES:
        return w.upper()                       # "... JACKSONVILLE FL"
    if w.lower() in ('of', 'the', 'and', 'for', 'at', 'on', 'in'):
        return w.lower()
    return w[:1].upper() + w[1:].lower()


def _title(s: str) -> str:
    words = s.split()
    out = ['-'.join(_word(part, i == len(words) - 1) for part in w.split('-'))
           for i, w in enumerate(words)]
    s = ' '.join(out)
    return s[:1].upper() + s[1:]


def _segment(seg: str) -> str:
    seg = seg.strip()
    key = seg.upper()
    if key in AGENCY_ALIASES:
        return AGENCY_ALIASES[key]
    m = re.match(r'^(.*),\s*DEPARTMENT OF$', key)          # "ENERGY, DEPARTMENT OF"
    if m:
        return f"Dept. of {_title(m.group(1))}"
    m = re.match(r'^DEPT\.? OF (?:THE )?(.*)$', key)       # "DEPT OF ENERGY"
    if m:
        return f"Dept. of {_title(m.group(1))}"
    return _title(seg)


def format_agency(raw) -> str:
    """'DEPT OF DEFENSE.DEPT OF THE ARMY.US ARMY CORPS OF ENGINEERS.…ENDIST BALTIMORE'
    -> 'Dept. of Defense — Army / USACE Baltimore'.
    Also handles lead-magnet's 'A / B / C' paths."""
    if not raw:
        return MISSING
    sep = '/' if '/' in raw else '.'
    parts, seen = [], set()
    for p in raw.split(sep):
        p = _OFFICE_CODE.sub('', p.strip()).strip()
        if p and p.upper() not in seen:
            seen.add(p.upper())
            parts.append(p)
    if not parts:
        return MISSING
    dept = _segment(parts[0])
    rest = parts[1:]
    if not rest:
        return dept
    sub = _segment(rest[0])
    if len(rest) == 1:
        return f"{dept} — {sub}"
    office = rest[-1]
    usace = any('CORPS OF ENGINEERS' in p.upper() for p in rest)
    m = re.match(r'^(?:ENDIST|ENGINEER DISTRICT)\s+(.*)$', office, re.I)
    if usace and m:
        office_disp = f"USACE {_title(m.group(1))}"
    else:
        office_disp = _segment(office)
    return f"{dept} — {sub} / {office_disp}"


def format_phone(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if re.fullmatch(r'\d+\.0', s):            # spreadsheet floats: 7088902524.0
        s = s[:-2]
    m = re.match(r'^\s*(?:\+?1[\s.-]*)?\(?(\d{3})\)?[\s.-]*(\d{3})[\s.-]*(\d{4})\s*(.*)$', s)
    if not m:
        return s or None
    ext = m.group(4).strip()
    ext_num = re.sub(r'^(?:x|ext\.?|extension)\s*[-.:]?\s*', '', ext, flags=re.I)
    out = f"({m.group(1)}) {m.group(2)}-{m.group(3)}"
    return f"{out} x{ext_num}" if ext_num else out


_ABBR_OFFSET = {'EST': -5, 'EDT': -4, 'CST': -6, 'CDT': -5, 'MST': -7, 'MDT': -6,
                'PST': -8, 'PDT': -7, 'AKST': -9, 'AKDT': -8, 'HST': -10, 'UTC': 0, 'GMT': 0}


def _parse_dt(raw):
    if not raw:
        return None, False
    s = str(raw).strip()
    m = re.fullmatch(r'([A-Za-z]{3}) (\d{1,2}), (\d{4}) (\d{1,2}:\d{2} [AP]M) ([A-Z]{3,4})', s)
    if m and m.group(5) in _ABBR_OFFSET:
        d = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}", '%b %d %Y %I:%M %p')
        return d.replace(tzinfo=timezone(timedelta(hours=_ABBR_OFFSET[m.group(5)]))), True
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        for fmt in ('%m/%d/%Y', '%Y-%m-%d %H:%M:%S', '%b %d, %Y'):
            try:
                d = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None, False
    has_time = bool(re.search(r'\d{1,2}:\d{2}', s))
    return d, has_time


def format_posted(raw) -> str:
    d, _ = _parse_dt(raw)
    if d is None:
        return str(raw).strip() if raw else MISSING
    return f"{d.strftime('%b')} {d.day}, {d.year}"


_OFFSET_ZONES = ('America/New_York', 'America/Chicago', 'America/Denver',
                 'America/Los_Angeles', 'America/Phoenix', 'America/Anchorage',
                 'Pacific/Honolulu')


def _zone_for_offset(d):
    """No place state: keep the timestamp's own local time by picking the US zone
    whose offset *on that date* matches (so -05:00 is CT in October, ET in
    November). UTC or unknown offsets fall back to ET."""
    off = d.utcoffset() if d.tzinfo else None
    if off:
        for name in _OFFSET_ZONES:
            z = ZoneInfo(name)
            if d.astimezone(z).utcoffset() == off:
                return z
    return ZoneInfo(DEFAULT_TZ)


def format_deadline(raw, state_code=None) -> str:
    """ISO deadline -> 'Oct 9, 2026 · 11:00 AM ET', shown in the place of
    performance's local zone (falls back to ET). Already-formatted strings
    pass through unchanged."""
    if not raw:
        return MISSING
    d, has_time = _parse_dt(raw)
    if d is None:
        return str(raw).strip()
    if not has_time:
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    if state_code and state_code.upper() in STATE_TZ:
        zone = ZoneInfo(STATE_TZ[state_code.upper()])
    else:
        zone = _zone_for_offset(d)
    if d.tzinfo is None:
        # SAM.gov naive timestamps are Eastern; never assume UTC.
        d = d.replace(tzinfo=ZoneInfo(DEFAULT_TZ))
    local = d.astimezone(zone)
    abbr = local.tzname() or ''
    label = TZ_SHORT.get(abbr, abbr)
    hour = local.strftime('%I').lstrip('0')
    return f"{local.strftime('%b')} {local.day}, {local.year} · {hour}:{local.strftime('%M %p')} {label}".strip()


def format_set_aside(desc, code=None) -> str:
    v = _first(desc)
    if v and str(v).strip().upper() not in ('NONE', 'N/A', 'NO SET ASIDE USED.'):
        return _FAR_SUFFIX.sub('', str(v)).strip()
    if code:
        return SET_ASIDE_CODES.get(str(code).upper(), str(code))
    if v:
        return 'None (full and open)'
    return MISSING


def format_place(city=None, state=None, zip_code=None, raw=None) -> str:
    if raw and not (city or state):
        m = re.fullmatch(r'\s*(.+?),\s*([A-Z]{2})\s*(\d{5}(?:-?\d{4})?)?\s*', str(raw))
        if not m:
            return str(raw).strip()
        city, state, zip_code = m.group(1), m.group(2), (m.group(3) or '').replace('-', '')
    city = _title(city) if city and city.isupper() else city
    st = (state or '').strip()
    st_disp = STATE_NAMES.get(st.upper(), st) if st else ''
    z = str(zip_code).split('.')[0].strip() if zip_code else ''
    z = z[:5] if re.fullmatch(r'\d{9}', z) else z
    left = ', '.join(x for x in (city, st_disp) if x)
    out = f"{left} {z}".strip()
    return out or MISSING


def _primary_poc(contacts):
    contacts = [c for c in (contacts or []) if isinstance(c, dict)]
    if not contacts:
        return {}
    for c in contacts:
        if (c.get('type') or '').lower() == 'primary':
            return c
    return contacts[0]


def extract_solicitation(rec) -> str:
    """Muse's extractor minus its loose 'any mixed alnum token' fallback,
    which grabbed project numbers (e.g. 'Z2DA--561-26-104') as solicitations."""
    v = _first(rec.get('solicitationNumber'), rec.get('solicitation'))
    if v:
        return str(v)
    sam = rec.get('sam') or {}
    desc = rec.get('description')
    if not isinstance(desc, str) or desc.startswith('http'):   # SAM v2 description is a URL
        desc = ''
    text = f"{rec.get('title') or ''} {desc} {sam.get('description') or ''}"
    m = re.search(r'(?i)\b(?:solicitation|rfq|rfp|ifb|bid)\s*(?:no\.?|number|#)?\s*:?\s+([A-Z0-9][A-Z0-9\-]{6,25}\d)\b', text)
    if m:
        return m.group(1)
    # Uniform PIID (FAR 4.1603): 6-char agency code + 2-digit FY + type letter
    # + 4-char serial, e.g. W912DR26QA057, W911S223S8000, 36C24226R0128.
    m = _PIID.search(text)
    return m.group(0) if m else MISSING


def extract_fields(rec: dict) -> dict:
    """Return {'Agency': str, ..., 'POC': {'name','email','phone'}} plus
    '_missing': [field names that fell back to MISSING]."""
    if isinstance(rec.get('sam_record'), dict):      # backfilled by sam_enrich.py
        rec = {**rec, **rec['sam_record']}
    sam = rec.get('sam') or {}
    enr = rec.get('enriched') or {}
    pop = rec.get('placeOfPerformance') or {}
    office = rec.get('officeAddress') or {}

    state_code = _first((pop.get('state') or {}).get('code'), enr.get('pop_state'))
    if not state_code and sam.get('place'):
        m = re.search(r',\s*([A-Z]{2})\b', sam['place'])
        state_code = m.group(1) if m else None

    agency_raw = _first(rec.get('fullParentPathName'), sam.get('agency'),
                        enr.get('awarding_agency'), enr.get('awarding_office'),
                        rec.get('agency'))
    # Award leads' date_signed is NOT a posted date; leave Posted empty for them.
    posted_raw = _first(rec.get('postedDate'), sam.get('posted'))
    deadline_raw = _first(rec.get('responseDeadLine'), rec.get('deadline_iso')
                          if rec.get('deadline_iso') and 'T' in str(rec.get('deadline_iso')) else None,
                          rec.get('deadline_display'), sam.get('deadline'))
    naics = _first(rec.get('naicsCode'), (rec.get('naicsCodes') or [None])[0],
                   sam.get('naics'), enr.get('naics'))
    set_aside = format_set_aside(
        _first(rec.get('typeOfSetAsideDescription'), sam.get('set_aside')),
        rec.get('typeOfSetAside'))

    if pop:
        place = format_place((pop.get('city') or {}).get('name'),
                             (pop.get('state') or {}).get('code'), pop.get('zip'))
    elif sam.get('place'):
        place = format_place(raw=sam['place'])
    elif enr.get('pop_state') or enr.get('pop_city'):
        place = format_place(enr.get('pop_city'), enr.get('pop_state'))
    else:
        # Never fall back to the *contractor's* state (Muse bug) — that is
        # not the place of performance.
        place = MISSING

    poc = _primary_poc(rec.get('pointOfContact'))
    poc = {
        'name': _first(poc.get('fullName'), rec.get('poc_name')),
        'email': _first(poc.get('email'), rec.get('poc_email')),
        'phone': format_phone(_first(poc.get('phone'), rec.get('poc_phone'))),
    }

    fields = {
        'Agency': format_agency(agency_raw),
        'Solicitation': extract_solicitation(rec),
        'Posted': format_posted(posted_raw),
        'Deadline': format_deadline(deadline_raw, state_code),
        'NAICS': str(naics).split('.')[0] if naics else MISSING,
        'Set-aside': set_aside,
        'Place': place,
        'POC': poc,
    }
    fields['_missing'] = [k for k in FIELD_ORDER
                          if (fields[k] == MISSING if k != 'POC' else not any(poc.values()))]
    return fields


def render_text(fields: dict) -> str:
    w = max(len(k) for k in FIELD_ORDER) + 2
    lines = []
    for k in FIELD_ORDER:
        if k == 'POC':
            p = fields['POC']
            lines.append(f"{k:<{w}}{p['name'] or MISSING}")
            for extra in (p['email'], p['phone']):
                if extra:
                    lines.append(f"{'':<{w}}· {extra}")
        else:
            lines.append(f"{k:<{w}}{fields[k]}")
    return '\n'.join(lines)


def render_html(fields: dict) -> str:
    """Email-safe table (inline styles only)."""
    e = html.escape
    td_l = 'style="padding:6px 12px 6px 0;color:#475467;font-weight:600;vertical-align:top;white-space:nowrap"'
    td_r = 'style="padding:6px 0;color:#1C1916;vertical-align:top"'
    rows = []
    for k in FIELD_ORDER:
        if k == 'POC':
            p = fields['POC']
            parts = [e(p['name'] or MISSING)]
            if p['email']:
                parts.append(f'· <a href="mailto:{e(p["email"])}">{e(p["email"])}</a>')
            if p['phone']:
                tel = re.sub(r'[^\d+]', '', p['phone'].split(' x')[0])
                parts.append(f'· <a href="tel:{e(tel)}">{e(p["phone"])}</a>')
            val = '<br>'.join(parts)
        else:
            val = e(fields[k])
        rows.append(f'<tr><td {td_l}>{e(k)}</td><td {td_r}>{val}</td></tr>')
    return ('<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px">'
            + ''.join(rows) + '</table>')
