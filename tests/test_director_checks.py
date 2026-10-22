"""Director clean-up after extraction: footnotes in the director table, the DIN certificate,
DIN conflicts, the FY2024 board rule, hand-confirmed merges, and the field-level regression
guard. Also the AOC-1 repeat-block filter. (Related-party amounts: test_rpt_amounts.py.)"""

from __future__ import annotations

import json

from src.extract.extractor import (
    Fact,
    _apply_merge_overrides,
    _drop_repeat_block,
    _fill_dins_from_certificate,
    _finish_directors,
    field_changes,
    keep_previous_if_fewer,
    load_merge_overrides,
)
from src.extract.tables import (
    parse_change,
    parse_date,
    parse_din_certificate,
    parse_directors_table,
    parse_footnotes,
)

# TCS's footnotes, as printed on p.99 (the "*" reused later for another table).
TCS_FOOTNOTES = "\n".join([
    "*appointed as CEO & MD w.e.f. June 1, 2023",
    " ",
    "**ceased to be CEO & MD w.e.f. June 1, 2023",
    " ",
    "^^appointed as Independent Director w.e.f. ",
    "October 12, 2023",
    " ",
    "^^^ceased to be Director w.e.f. January 10, 2024 upon ",
    "completion of his term as Independent Director.",
    " ",
    "*includes shares held jointly with his relative",
])

CERTIFICATE = "\n".join([
    "Certificate of non-disqualification of directors",
    "Sr. No.", "Name of Director", "DIN", "Date of Appointment in Company",
    "1.", "N Chandrasekaran", "00121863", "September 6, 2007",
    "2.", "K Krithivasan", "10106739", "June 1, 2023",
    "3.", "Helene Auriol Potier", "10166891", "May 26, 2023",
    "4.", "Al-Noor Ramji", "08326836", "October 12, 2023",
])


# ---------------------------------------------------------------- tables.py


def test_footnotes_first_definition_wins():
    notes = parse_footnotes(TCS_FOOTNOTES)
    assert notes["*"] == "appointed as CEO & MD w.e.f. June 1, 2023"
    assert notes["^^"] == "appointed as Independent Director w.e.f. October 12, 2023"
    assert notes["^^^"].startswith("ceased to be Director w.e.f. January 10, 2024")


def test_parse_change_and_dates():
    assert parse_change("ceased to be Director w.e.f. January 10, 2024 upon completion") == ("ceased", "January 10, 2024")
    assert parse_change("appointed as Independent Director w.e.f. October 12, 2023") == ("appointed", "October 12, 2023")
    assert parse_change("re-appointed as Independent Director for a second term w.e.f. December 18, 2023")[0] == "current"
    assert str(parse_date("May 15, 2024")) == "2024-05-15"
    assert str(parse_date("15/05/2024")) == "2024-05-15"
    assert parse_date("not a date") is None


def test_director_table_footnotes_set_status_and_dates():
    table = [
        ["Al-Noor Ramji^^ DIN 00230865", "Independent, Non-Executive"],
        ["Don Callahan^^^ DIN 08326836", "Independent, Non-Executive"],
        ["K Krithivasan* (CEO & MD) DIN 10106739", "Non-Independent, Executive"],
        ["Rajesh Gopinathan** (Erstwhile CEO & MD) DIN 06365813", "Non-Independent, Executive"],
        ["Keki Mistry DIN 00008886", "Independent, Non-Executive"],
    ]
    rows = {r["person_name"]: r for r in parse_directors_table(table, "", TCS_FOOTNOTES)}
    assert (rows["Al-Noor Ramji"]["status"], rows["Al-Noor Ramji"]["appointed_on"]) == ("appointed", "October 12, 2023")
    assert (rows["Don Callahan"]["status"], rows["Don Callahan"]["ceased_on"]) == ("ceased", "January 10, 2024")
    assert rows["K Krithivasan"]["appointed_on"] == "June 1, 2023"
    assert (rows["Rajesh Gopinathan"]["status"], rows["Rajesh Gopinathan"]["ceased_on"]) == ("ceased", "June 1, 2023")
    assert (rows["Keki Mistry"]["status"], rows["Keki Mistry"]["footnote"]) == ("current", None)


def test_certificate_name_before_or_after_the_din():
    assert parse_din_certificate(CERTIFICATE)[2] == {"name": "Helene Auriol Potier", "din": "10166891", "appointed_on": "May 26, 2023"}
    din_first = "\n".join(["disqualification", "1", "00121863", "Mr. Chandrasekaran Natarajan", "03/07/2017",
                           "2", "00161853", "Mr. Siraj Azmat Chaudhry", "03/07/2017",
                           "3", "00043265", "Ms. Shikha Sanjaya Sharma", "07/05/2019"])
    assert parse_din_certificate(din_first)[0] == {"name": "Mr. Chandrasekaran Natarajan", "din": "00121863", "appointed_on": "03/07/2017"}
    assert parse_din_certificate("A page about something else\n00121863\nN Chandrasekaran") == []


# ---------------------------------------------------------------- extractor helpers


def _director(name, din=None, page=98, method="llm", **extra):
    data = {"person_name": name, "din": din, "role": "", "is_independent": True, "is_executive": False,
            "status": "current", **extra}
    return Fact("director", method, "Example Ltd", "EX", "corporate_governance", page, "FY2023-24", data, name)


def _page(number, text):
    return {"page": number, "text": text, "tables": [], "rotated": False}


BOARD_PAGE = _page(98, "Number of Board Meetings attended: N Chandrasekaran 5, Helene Auriol Potier 4, "
                       "Al-Noor Ramji 2, Don Callahan 3, Bharat Puri")
CERT_PAGE = _page(117, CERTIFICATE)


def test_missing_din_is_filled_from_the_certificate_and_linked_directorships_follow():
    other = Fact("other_directorship", "llm", "Example Ltd", "EX", "corporate_governance", 98, "FY2023-24",
                 {"person_name": "Helene Auriol Potier", "din": None, "company_name": "X Ltd"}, "X Ltd")
    facts, notes = _fill_dins_from_certificate([_director("Helene Auriol Potier"), other], [BOARD_PAGE, CERT_PAGE])
    assert facts[0].data["din"] == "10166891" and facts[0].data["din_source"] == "certificate p.117"
    assert facts[1].data["din"] == "10166891"
    assert len(notes) == 1


def test_din_conflict_with_the_certificate_is_marked_on_both_directors():
    facts = [_director("Al-Noor Ramji", "00230865"), _director("Don Callahan", "08326836", status="ceased")]
    kept, notes, _ = _finish_directors(facts, [BOARD_PAGE, CERT_PAGE])
    ramji, callahan = kept
    assert ramji.data["din"] == "00230865"  # both DINs kept on record
    assert ramji.data["din_conflict"] == {"certificate_din": "08326836", "certificate_page": 117}
    assert callahan.data["din_conflict"] == {"certificate_name_for_this_din": "Al-Noor Ramji", "certificate_page": 117}
    assert sum("DIN conflict" in n for n in notes) == 2


def test_name_only_in_resolution_history_is_not_an_fy2024_director():
    history = _page(248, "2020-21 Re-appointment of Mr Guenter Butschek (DIN: 07427375) as the Chief Executive Officer")
    facts = [_director("N Chandrasekaran", "00121863"), _director("Guenter Butschek", "07427375", page=248)]
    kept, notes, dropped = _finish_directors(facts, [BOARD_PAGE, history, CERT_PAGE])
    assert [f.data["person_name"] for f in kept] == ["N Chandrasekaran"]
    assert dropped[0].data["person_name"] == "Guenter Butschek"
    assert any("Guenter Butschek" in n for n in notes)


def test_appointment_after_year_end_gets_its_date_and_flag_and_is_kept():
    text = ("The Board at its meeting held on May 10, 2024 appointed Mr Bharat Puri (DIN:02173566) as an "
            "Additional Independent Director, for a tenure of 5 years commencing from May 15, 2024.")
    facts = [_director("Bharat Puri", "02173566", status="appointed", page=237)]
    kept, _, _ = _finish_directors(facts, [_page(237, text)])
    [puri] = kept
    assert (puri.data["appointed_on"], puri.data["after_fy_end"]) == ("May 15, 2024", True)


def test_merge_override_folds_the_named_copy_into_the_din_holder(tmp_path):
    path = tmp_path / "merges.csv"
    path.write_text("nse_symbol,fact_type,from_name,to_din,note\n"
                    "EX,director,Om Prakash Bhatt,00548091,same person\n", encoding="utf-8")
    overrides = load_merge_overrides(path)
    facts = [_director("Mr O P Bhatt", "00548091"), _director("Mr Om Prakash Bhatt")]
    kept, log = _apply_merge_overrides(facts, overrides, "EX")
    assert [f.data["person_name"] for f in kept] == ["Mr O P Bhatt"]
    assert log[0].startswith("override: 'Mr Om Prakash Bhatt'")
    assert _apply_merge_overrides(facts, overrides, "OTHER")[0] == facts


def test_repeat_block_entries_are_dropped():
    page = _page(479, "88 Real Subsidiary Ltd 100.00 Details of Direct Subsidiaries, on consolidated "
                      "basis including their respective subsidiaries included above Tata Technologies Limited 55.39")
    def sub(name):
        return Fact("subsidiary", "llm", "Example Ltd", "EX", "subsidiaries_aoc1", 479, "FY2023-24",
                    {"subsidiary_name": name}, name)
    kept, dropped = _drop_repeat_block([sub("Real Subsidiary Ltd"), sub("Tata Technologies Limited")], [page])
    assert [f.data["subsidiary_name"] for f in kept] == ["Real Subsidiary Ltd"]
    assert dropped[0].reason.startswith("in a summary block")


# ---------------------------------------------------------------- field-level guard


def _auditor(frn):
    return Fact("auditor", "llm", "Example Ltd", "EX", "auditor_report", 245, "FY2023-24",
                {"firm_name": "B S R & Co. LLP", "firm_registration_no": frn, "audit_type": "statutory"}, "x")


def _rpt(amount, party="Tata Sons Private Limited"):
    return Fact("related_party", "llm", "Example Ltd", "EX", "related_party", 299, "FY2023-24",
                {"party_name": party, "nature": "Dividend paid", "amount_inr_crore": amount}, "x")


def test_field_guard_flags_lost_and_changed_key_fields():
    previous = [_auditor("101248W/W-100022"), _rpt(18177.0), _director("Don Callahan", "08326836")]
    new = [_auditor(None), _rpt(18000.0), _director("Don Callahan", "08326836", status="ceased")]
    flags = field_changes(previous, new)
    assert "auditor b s r & co. llp / statutory: firm_registration_no was '101248W/W-100022', now empty" in flags
    assert "related_party tata sons private limited / dividend paid: amount_inr_crore was 18177.0, now 18000.0" in flags
    assert "director don callahan: status was 'current', now 'ceased'" in flags
    assert len(flags) == 3


def test_field_guard_flags_a_lost_amount_as_printed():
    before = _rpt(18177.0)
    before = Fact(**{**before.__dict__, "data": {**before.data, "amount_as_printed": "18,177"}})
    flags = field_changes([before], [_rpt(18177.0)])
    assert flags == ["related_party tata sons private limited / dividend paid: amount_as_printed was '18,177', now empty"]


def test_field_guard_skips_ambiguous_identities_and_first_fills():
    previous = [_rpt(1.0), _rpt(2.0), _auditor(None)]  # same party+nature twice: can't pair them
    new = [_rpt(3.0), _auditor("101248W/W-100022")]  # empty -> filled is not a regression
    assert field_changes(previous, new) == []


def test_explained_removals_are_not_regressions():
    previous = [_director("N Chandrasekaran", "00121863"), _director("Guenter Butschek", "07427375")]
    new = [_director("N Chandrasekaran", "00121863")]
    kept, flags = keep_previous_if_fewer(previous, new, explained={("director", "corporate_governance"): 1})
    assert [f.data["person_name"] for f in kept] == ["N Chandrasekaran"] and flags == []
    kept, flags = keep_previous_if_fewer(previous, new)
    assert len(kept) == 2 and len(flags) == 1


def test_footnote_marker_glued_to_a_name_still_counts_as_on_the_board_page():
    page = _page(86, "Attendance of directors during fiscal 2024 Uri Levine(1) NA NA 1 1 100 Bobby Parikh 6 6 100")
    facts = [_director("Uri Levine", status="ceased", page=85)]
    kept, _, dropped = _finish_directors(facts, [page])
    assert [f.data["person_name"] for f in kept] == ["Uri Levine"] and dropped == []


def test_appointment_date_comes_from_the_certificate_not_a_neighbouring_footnote():
    attendance = _page(96, "Meetings attended: Uri Levine(1) NA 1 1 100 Helene Auriol Potier(2) NA 3 3 100 "
                           "(1) Ceased to be a member of the Committee due to retirement effective April 19, 2023 "
                           "(2) Appointed as a member of the Committee")
    facts = [_director("Helene Auriol Potier", "10166891", status="appointed", page=96),
             _director("Uri Levine", status="ceased", page=96)]
    kept, notes, _ = _finish_directors(facts, [attendance, CERT_PAGE])
    helene, uri = kept
    assert helene.data["appointed_on"] == "May 26, 2023"  # certificate, not April 19
    assert uri.data["ceased_on"] == "April 19, 2023"
