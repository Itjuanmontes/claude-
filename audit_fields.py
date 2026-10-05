"""Field-coverage audit: python3 audit_fields.py <records.json>

Accepts a list of SAM.gov records, lead-magnet bids, or lead-magnet contacts
(each with a `bids` list). Reports how often each email field is missing.
"""
import json
import sys
from collections import Counter

from solicitation_fields import FIELD_ORDER, extract_fields


def records(data):
    for r in data:
        if isinstance(r, dict) and 'bids' in r:
            yield from r['bids']
        else:
            yield r


def main(path):
    data = json.load(open(path))
    if isinstance(data, dict):
        data = data.get('opportunitiesData') or data.get('results') or [data]
    seen, missing, n = set(), Counter(), 0
    for r in records(data):
        key = r.get('noticeId') or r.get('url') or json.dumps(r, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        n += 1
        missing.update(extract_fields(r)['_missing'])
    print(f"unique records: {n}")
    print(f"{'field':<14}{'missing':>8}{'filled %':>10}")
    for k in FIELD_ORDER:
        print(f"{k:<14}{missing[k]:>8}{100 * (n - missing[k]) / max(n, 1):>9.0f}%")


if __name__ == '__main__':
    main(sys.argv[1])
