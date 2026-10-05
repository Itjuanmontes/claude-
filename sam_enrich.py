"""Backfill missing solicitation fields from the SAM.gov Opportunities API.

    SAM_API_KEY=... python3 sam_enrich.py contacts.json [out.json]

For each open-opportunity bid with a sam.gov URL, fetches the full record by
notice ID and stores it under `bid['sam_record']`. `extract_fields` then reads
NAICS, set-aside, place, posted date, and the primary POC from it.
Get a free key at sam.gov → Account Details → Public API Key.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

API = "https://api.sam.gov/opportunities/v2/search"
_NOTICE_ID = re.compile(r'sam\.gov/(?:workspace/contract/)?opp/([0-9a-f]{32})', re.I)


def notice_id(url):
    m = _NOTICE_ID.search(url or '')
    return m.group(1) if m else None


def fetch_record(nid, api_key, opener=urllib.request.urlopen, today=None):
    # v2 search requires a posted-date window of at most 1 year.
    today = today or date.today()
    q = urllib.parse.urlencode({
        'api_key': api_key, 'noticeid': nid, 'limit': 1,
        'postedFrom': (today - timedelta(days=364)).strftime('%m/%d/%Y'),
        'postedTo': today.strftime('%m/%d/%Y'),
    })
    with opener(f"{API}?{q}", timeout=30) as r:
        data = json.load(r)
    recs = data.get('opportunitiesData') or []
    return recs[0] if recs else None


def enrich(contacts, api_key, opener=urllib.request.urlopen, pause=0.2):
    cache, stats = {}, {'fetched': 0, 'not_found': 0, 'errors': 0, 'skipped': 0}
    for c in contacts:
        for b in c.get('bids', []):
            nid = notice_id(b.get('url'))
            if not nid or b.get('sam_record'):
                stats['skipped'] += 1
                continue
            if nid not in cache:
                try:
                    cache[nid] = fetch_record(nid, api_key, opener)
                    stats['fetched' if cache[nid] else 'not_found'] += 1
                except Exception as ex:  # keep going; report at the end
                    cache[nid] = None
                    stats['errors'] += 1
                    print(f"  {nid}: {ex}", file=sys.stderr)
                time.sleep(pause)
            if cache[nid]:
                b['sam_record'] = cache[nid]
    return stats


if __name__ == '__main__':
    key = os.environ.get('SAM_API_KEY')
    if not key:
        sys.exit("Set SAM_API_KEY (sam.gov → Account Details → Public API Key).")
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else src
    contacts = json.load(open(src))
    print(enrich(contacts, key))
    json.dump(contacts, open(out, 'w'), indent=1)
