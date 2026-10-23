"""Phase 7 scorer on made-up answers (written before any real answer was read)."""

import json

from src.eval.score import (AliasIndex, AnswerItems, find_dates, find_values, part_in, score_answer, score_list,
                            score_none, score_number)

ALIASES = AliasIndex()
ALIASES.spellings = {"n chandrasekaran": ["N. Chandrasekaran", "Natarajan Chandrasekaran"],
                     "natarajan chandrasekaran": ["N. Chandrasekaran", "Natarajan Chandrasekaran"],
                     "tata consultancy servlces": ["Tata Consultancy Services Limited", "TCS"]}


def test_names_fold_case_punctuation_titles_legal_forms_and_spacing():
    assert part_in("n:P B Balaji", "Mr. P. B. Balaji, Group CFO", ALIASES)
    assert part_in("n:T V Narendran", "T.V. Narendran", ALIASES)
    assert part_in("n:A.G.S. Manikantha", "A. G. S. Manikantha", ALIASES)
    assert part_in("n:B S R & Co. LLP", "BSR & Co LLP", ALIASES)
    assert part_in("n:Makarand M. Joshi & Co.", "M/s Makarand M Joshi and Company", ALIASES)
    assert part_in("n:Tata Motors Limited", "Tata Motors", ALIASES)
    assert part_in("n:Neelachal Ispat Nigam Limited", "Neelachal lspat Nigam Ltd", ALIASES)
    assert part_in("n:Sunil D'Souza", "Sunil D’Souza (MD & CEO)", ALIASES)


def test_names_through_aliases_and_close_spellings_only():
    assert part_in("n:N Chandrasekaran", "Natarajan Chandrasekaran", ALIASES)
    assert part_in("n:Tata Consultancy Services Limited", "TCS", ALIASES)
    assert part_in("n:TCS Technology Solution GmbH", "TCS Technology Solutions GmbH", ALIASES)
    assert part_in("n:L Krishnakumar | Lakshmanan Krishna Kumar", "Lakshmanan Krishna Kumar", ALIASES)
    assert not part_in("n:L Krishnakumar", "Ajit Krishnakumar", ALIASES)
    assert not part_in("n:Tata Steel Limited", "Tata Motors Limited", ALIASES)
    assert not part_in("n:O P Bhatt", "R P Bhatt", ALIASES)


def test_values_any_format():
    assert part_in("v:₹2,40,893 crore", "2,40,893", ALIASES)
    assert part_in("v:₹2,40,893 crore", "240,893 crore", ALIASES)
    assert part_in("v:₹2,40,893 crore", "Rs 2.40893 lakh crore", ALIASES)
    assert part_in("v:55.39%", "55.39 percent", ALIASES)
    assert part_in("v:129", "one hundred twenty-nine", ALIASES)
    assert part_in("v:23", "twenty-three subsidiaries", ALIASES)
    assert not part_in("v:₹1,089 crore", "about ₹1,100 crore", ALIASES)
    assert not part_in("v:55.39%", "55.4%", ALIASES)


def test_dates_any_format_and_not_counted_as_values():
    assert part_in("d:June 1, 2023", "joined on 01/06/2023", ALIASES)
    assert part_in("d:June 1, 2023", "1st June 2023", ALIASES)
    assert not part_in("d:June 1, 2023", "June 9, 2023", ALIASES)
    assert find_dates("from September 19, 2023")[0] == {(2023, 9, 19)}
    assert find_values("appointed May 15, 2024 in FY2024") == []


def test_value_counts_only_with_its_entity():
    key = [["n:Tata Motors Limited", "v:₹298.51 crore"], ["n:Tata Consumer Products Limited", "v:₹228.62 crore"]]
    right = score_list(key, ["Tata Motors: ₹298.51 crore", "Tata Consumer Products: ₹228.62 crore"], ALIASES)
    assert right.correct and right.score == 1.0
    swapped = score_list(key, ["Tata Motors: ₹228.62 crore", "Tata Consumer Products: ₹298.51 crore"], ALIASES)
    assert swapped.score == 0.0


def test_list_precision_recall_f1():
    key = [["n:Deepak Kapoor"], ["n:Farida Khambata"]]
    s = score_list(key, ["Deepak Kapoor", "Noel Naval Tata"], ALIASES)
    assert (s.precision, s.recall) == (0.5, 0.5) and s.extra_items == ["Noel Naval Tata"]
    assert score_list(key, [], ALIASES).score == 0.0


def test_numbers_need_the_gold_value_and_no_other():
    assert score_number("23", ["23 subsidiaries"]).correct
    assert not score_number("23", ["22"]).correct
    assert not score_number("23", ["23", "25"]).correct
    assert not score_number("23", []).correct


def test_none_needs_no_items():
    assert score_none([], True).correct
    assert not score_none(["Tata Motors"], False).correct
    assert score_answer({"type": "none"}, AnswerItems(items=[], says_none=True), ALIASES).correct


def test_scoring_key_parses():
    from pathlib import Path

    for line in Path("src/eval/scoring_key.jsonl").read_text(encoding="utf-8").splitlines():
        key = json.loads(line)
        if key["type"] == "number":
            assert len(find_values(key["value"])) == 1, key
        for item in key.get("items", []):
            for part in item:
                assert part == "none" or part[:2] in ("n:", "v:", "d:", "w:"), part
                if part.startswith("v:"):
                    assert len(find_values(part[2:])) == 1, part
                if part.startswith("d:"):
                    assert len(find_dates(part[2:])[0]) == 1, part
