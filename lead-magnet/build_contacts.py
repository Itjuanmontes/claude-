import openpyxl, json, re
from datetime import datetime, timezone

STATE_NAMES = {'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia'}
TZ_ABBR = {'-04:00':'ET','-05:00':'CT','-06:00':'MT','-07:00':'PT','-08:00':'AKT','-10:00':'HST'}
TYPE_LABEL = {'recent_prime_award_subcontract_lead':'Recent Prime Award · Subcontract Lead','open_opportunity':'Open Opportunity'}
TYPE_LINK = {'recent_prime_award_subcontract_lead':'Open award record →','open_opportunity':'View opportunity →'}

def norm_title(t):
    return re.sub(r'\s+', ' ', (t or '').strip().lower())

wb = openpyxl.load_workbook('/home/hatch/workspace/user/files/Filtered_Leads.xlsx', read_only=True)
ws = wb['Hoja 1']
rows = list(ws.iter_rows(values_only=True))
data = rows[1:]
now = datetime.now(timezone.utc)
contacts = []
total_dupes = 0
for r in data:
    bids, seen, dupes = [], set(), 0
    for n in range(1, 5):
        title, deadline, url, btype = r[19+n], r[23+n], r[27+n], r[31+n]
        if not title and not url:
            continue
        # parse deadline first (needed for dedupe key)
        d_iso = None
        if deadline:
            try:
                d = datetime.fromisoformat(str(deadline))
                if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
                d_iso = d.isoformat()
            except Exception:
                pass
        key = (norm_title(title), d_iso)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        d_display, days_left, expired = None, None, False
        if deadline:
            try:
                d = datetime.fromisoformat(str(deadline))
                if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
                m = re.search(r'([+-]\d{2}):(\d{2})$', d.isoformat())
                tz = TZ_ABBR.get(m.group(1)+':'+m.group(2), '') if m else ''
                d_display = d.strftime('%-m/%-d/%Y')  # placeholder replaced below
                d_display = f"{d.strftime('%b')} {d.day}, {d.year} · {d.strftime('%-I:%M %p')} {tz}".strip()
                days_left = (d - now).days
                expired = d < now
            except Exception:
                d_display = str(deadline)
        bids.append({
            'slot': n, 'title': title, 'deadline_iso': d_iso, 'deadline_display': d_display,
            'days_left': days_left, 'expired': expired, 'url': url,
            'type': btype, 'type_label': TYPE_LABEL.get(btype, btype),
            'link_text': TYPE_LINK.get(btype, 'View →'),
        })
    total_dupes += dupes
    state_abbr = r[6]
    contacts.append({
        'spid': r[0], 'business_name': r[1], 'first_name': r[2], 'last_name': r[3],
        'email': r[4], 'city': r[5], 'state': state_abbr,
        'state_name': STATE_NAMES.get(state_abbr, state_abbr),
        'zip': r[7], 'category': r[8], 'services_offered': r[9],
        'annual_sales': r[10], 'employees': r[11], 'disposition': r[12],
        'original_approval_date': str(r[13]) if r[13] else None,
        'page_link': r[14], 'business_phone': r[15], 'cell_phone': r[16],
        'text_message': r[17], 'commercial_match_count': r[18], 'match_status': r[19],
        'bids': bids, 'bid_count': len(bids), 'duplicate_bids_removed': dupes,
    })

open('lead-magnet-contacts.json', 'w').write(json.dumps(contacts, indent=1))
from collections import Counter
print('contacts:', len(contacts))
print('unique bid counts:', dict(Counter(c['bid_count'] for c in contacts)))
print('total duplicate bid slots removed:', total_dupes)
print('sample deadline:', contacts[0]['bids'][0]['deadline_display'])
