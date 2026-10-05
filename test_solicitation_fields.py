"""Run: python3 test_solicitation_fields.py  (or pytest)."""
from solicitation_fields import (MISSING, extract_fields, format_agency,
                                 format_deadline, format_phone, render_html,
                                 render_text)

# SAM.gov Opportunities API v2 shape for W912DR26QA057.
SAM_W912DR26QA057 = {
    "title": "Fort Meade Roofing Repairs",
    "solicitationNumber": "W912DR26QA057",
    "fullParentPathName": "DEPT OF DEFENSE.DEPT OF THE ARMY.US ARMY CORPS OF ENGINEERS."
                          "ENGINEER DIVISION NORTH ATLANTIC.ENDIST BALTIMORE.W2SD ENDIST BALTIMORE",
    "postedDate": "2026-09-28",
    "responseDeadLine": "2026-10-09T11:00:00-04:00",
    "naicsCode": "238160",
    "typeOfSetAsideDescription": "Total Small Business Set-Aside (FAR 19.5)",
    "typeOfSetAside": "SBA",
    "placeOfPerformance": {"city": {"code": "29525", "name": "Fort Meade"},
                           "state": {"code": "MD", "name": "Maryland"},
                           "zip": "20755", "country": {"code": "USA"}},
    "pointOfContact": [
        {"type": "secondary", "fullName": "Backup Person", "email": "b@usace.army.mil", "phone": "4105550000"},
        {"type": "primary", "fullName": "Michael Getz",
         "email": "michael.j.getz@usace.army.mil", "phone": "5407614935"},
    ],
}

EXPECTED_TEXT = """\
Agency        Dept. of Defense — Army / USACE Baltimore
Solicitation  W912DR26QA057
Posted        Sep 28, 2026
Deadline      Oct 9, 2026 · 11:00 AM ET
NAICS         238160
Set-aside     Total Small Business Set-Aside
Place         Fort Meade, Maryland 20755
POC           Michael Getz
              · michael.j.getz@usace.army.mil
              · (540) 761-4935"""


def test_w912dr26qa057_all_fields():
    f = extract_fields(SAM_W912DR26QA057)
    assert f["_missing"] == []
    assert render_text(f) == EXPECTED_TEXT


def test_html_has_every_row_and_links():
    h = render_html(extract_fields(SAM_W912DR26QA057))
    for label in ("Agency", "Solicitation", "Posted", "Deadline", "NAICS",
                  "Set-aside", "Place", "POC"):
        assert f">{label}</td>" in h
    assert 'href="mailto:michael.j.getz@usace.army.mil"' in h
    assert 'href="tel:5407614935"' in h


def test_missing_fields_still_render_rows():
    f = extract_fields({"title": "Bare record"})
    txt = render_text(f)
    assert txt.count(MISSING) == 8
    assert len(f["_missing"]) == 8


def test_lead_magnet_bid_shape():
    bid = {
        "title": "Z2DA--561-26-104 Repair Operating Room (OR) & Bathroom Leaks",
        "solicitation": "36C24226R0128",
        "deadline_iso": "2026-11-04", "deadline_display": "Nov 4, 2026 · 1:00 PM ET",
        "poc_name": "Delf Saco Mizhquiri", "poc_email": "x@va.gov",
        "poc_phone": "(914) 737-4400 x-202046",
        "sam": {"agency": "VETERANS AFFAIRS, DEPARTMENT OF",
                "place": "East Orange, NJ 07018", "naics": "236220",
                "set_aside": "Service-Disabled Veteran-Owned Small Business (SDVOSB) Set-Aside (FAR 19.14)",
                "posted": "Oct 2, 2026"},
    }
    f = extract_fields(bid)
    assert f["Agency"] == "Dept. of Veterans Affairs"
    assert f["Deadline"] == "Nov 4, 2026 · 1:00 PM ET"
    assert f["Set-aside"] == "Service-Disabled Veteran-Owned Small Business (SDVOSB) Set-Aside"
    assert f["POC"]["phone"] == "(914) 737-4400 x202046"
    assert f["_missing"] == []


def test_deadline_tz_is_dst_aware_and_local():
    # Muse labelled -05:00 as CT; after DST ends that is ET.
    assert format_deadline("2026-11-04T13:00:00-05:00", "NJ") == "Nov 4, 2026 · 1:00 PM ET"
    # Shown in place-of-performance local time.
    assert format_deadline("2026-10-06T17:00:00-05:00", "IL") == "Oct 6, 2026 · 5:00 PM CT"
    assert format_deadline("2026-10-06T17:00:00-07:00", "AZ") == "Oct 6, 2026 · 5:00 PM MT"
    # Naive timestamps are Eastern, not UTC.
    assert format_deadline("2026-10-09T11:00:00", "MD") == "Oct 9, 2026 · 11:00 AM ET"


def test_agency_variants():
    assert format_agency("ENERGY, DEPARTMENT OF / ENERGY, DEPARTMENT OF / FERMILAB - DOE CONTRACTOR") \
        == "Dept. of Energy — Fermilab - DOE Contractor"
    assert format_agency(None) == MISSING


def test_phone_variants():
    assert format_phone("6308403207") == "(630) 840-3207"
    assert format_phone(7088902524.0) == "(708) 890-2524"
    assert format_phone("+1 540.761.4935") == "(540) 761-4935"


def test_solicitation_no_false_positive_from_project_number():
    f = extract_fields({"title": "Z2DA--537-24-106 Create Contractor Lie-Down Zone"})
    assert f["Solicitation"] == MISSING


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print("PASS", name)
            except AssertionError as ex:
                fails += 1; print("FAIL", name, ex)
    sys.exit(1 if fails else 0)
