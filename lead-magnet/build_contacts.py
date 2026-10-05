import openpyxl, json, re, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from solicitation_fields import format_deadline  # DST-aware "Oct 9, 2026 · 11:00 AM ET"

STATE_NAMES = {'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia','HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland','MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia'}
TYPE_LABEL = {'recent_prime_award_subcontract_lead':'Recent Prime Award · Subcontract Lead','open_opportunity':'Open Opportunity'}
TYPE_LINK = {'recent_prime_award_subcontract_lead':'Open award record →','open_opportunity':'View opportunity →'}

def norm_title(t):
    return re.sub(r'\s+', ' ', (t or '').strip().lower())


def parse_deadline(deadline):
    """Parse once. Naive timestamps are SAM.gov Eastern time, not UTC."""
    if not deadline:
        return None
    try:
        d = deadline if isinstance(deadline, datetime) else datetime.fromisoformat(str(deadline).replace('Z', '+00:00'))
    except ValueError:
        return None
    if not isinstance(deadline, datetime) and not re.search(r'\d:\d{2}', str(deadline)):
        d = d.replace(hour=23, minute=59)   # date-only: open until end of that day
    if d.tzinfo is None:
        d = d.replace(tzinfo=ZoneInfo('America/New_York'))
    return d


def has_time(deadline):
    return isinstance(deadline, datetime) or bool(re.search(r'\d:\d{2}', str(deadline or '')))


def main(xlsx_path, out_path='lead-magnet-contacts.json'):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb['Hoja 1']
    rows = list(ws.iter_rows(values_only=True))
    contacts, total_dupes = build(rows[1:], datetime.now(timezone.utc))
    open(out_path, 'w').write(json.dumps(contacts, indent=1))
    from collections import Counter
    print('contacts:', len(contacts))
    print('unique bid counts:', dict(Counter(c['bid_count'] for c in contacts)))
    print('total duplicate bid slots removed:', total_dupes)
    if contacts and contacts[0]['bids']:
        print('sample deadline:', contacts[0]['bids'][0]['deadline_display'])


def build(data, now):
    contacts = []
    total_dupes = 0
    for r in data:
        bids, seen, dupes = [], set(), 0
        for n in range(1, 5):
            title, deadline, url, btype = r[19+n], r[23+n], r[27+n], r[31+n]
            if not title and not url:
                continue
            d = parse_deadline(deadline)
            d_iso = d.isoformat() if d else None
            key = (norm_title(title), d_iso)
            if key in seen:
                dupes += 1
                continue
            seen.add(key)
            d_display, days_left, expired = None, None, False
            if d:
                d_display = format_deadline(d_iso if has_time(deadline) else d.date().isoformat())
                days_left = (d - now).days
                expired = d < now
            elif deadline:
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
    return contacts, total_dupes


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/home/hatch/workspace/user/files/Filtered_Leads.xlsx')
