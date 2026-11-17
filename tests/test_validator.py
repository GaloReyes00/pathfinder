"""Tests for pathfinder/validator.py. Run from the repo root with: python -m pytest -q

They use tests/sample_courses.json, a small set of made-up TEST courses, so they
do not depend on the real dataset in data/courses.json.
"""
from pathlib import Path

import pytest

from pathfinder.validator import load_courses, load_requirements, normalize_id, unmet_prereqs, validate_plan

COURSES = load_courses(Path(__file__).parent / "sample_courses.json")
NO_REQUIREMENTS = {}  # passing {} keeps a test from picking up data/requirements.json


def check(plan, completed=(), max_units=15, semesters=4, requirements=NO_REQUIREMENTS):
    profile = {"completed": list(completed), "max_units": max_units, "semesters": semesters}
    return validate_plan(plan, profile, courses=COURSES, requirements=requirements)


def types(problems):
    return [p.split(":")[0] for p in problems]


# --- valid plans ---------------------------------------------------------------

def test_valid_plan_has_no_violations():
    plan = [["TEST 101", "TEST 110"], ["TEST 201"], ["TEST 301", "TEST 350"], ["TEST 400"]]
    assert check(plan) == []


def test_empty_plan_is_valid():
    assert check([]) == []
    assert check([[], []]) == []


def test_completed_courses_satisfy_prerequisites():
    assert check([["TEST 201"]], completed=["TEST 101"]) == []


def test_either_alternative_satisfies_an_any_rule():
    assert check([["TEST 301"]], completed=["TEST 201", "TEST 110"]) == []
    assert check([["TEST 301"]], completed=["TEST 201", "TEST 120"]) == []


# --- prerequisite violations ---------------------------------------------------

def test_missing_prerequisite_is_reported():
    problems = check([["TEST 201"]])
    assert types(problems) == ["prereq"]
    assert "TEST 201 needs TEST 101" in problems[0]


def test_prerequisite_in_the_same_semester_does_not_count():
    assert types(check([["TEST 101", "TEST 201"]])) == ["prereq"]


def test_prerequisite_in_a_later_semester_does_not_count():
    assert types(check([["TEST 201"], ["TEST 101"]])) == ["prereq"]


def test_any_rule_fails_when_no_alternative_is_met():
    problems = check([["TEST 301"]], completed=["TEST 201"])
    assert types(problems) == ["prereq"]
    assert "(TEST 110 or TEST 120)" in problems[0]


def test_message_lists_every_missing_part():
    problems = check([["TEST 301"]])
    assert "TEST 201 and (TEST 110 or TEST 120)" in problems[0]


# --- corequisite violations ----------------------------------------------------
# TEST 220 (lecture) and TEST 222 (lab) are each other's coreqs.
# TEST 230 has prereq TEST 101 and coreq TEST 110 (same semester or earlier).

def test_coreqs_taken_together_are_valid():
    assert check([["TEST 101"], ["TEST 220", "TEST 222"]]) == []


def test_lecture_without_its_lab_is_reported():
    problems = check([["TEST 101"], ["TEST 220"]])
    assert types(problems) == ["coreq"]
    assert "TEST 220 needs TEST 222 in the same semester or earlier" in problems[0]


def test_lab_without_its_lecture_is_reported():
    assert types(check([["TEST 222"]])) == ["coreq"]


def test_coreq_already_completed_counts():
    assert check([["TEST 222"]], completed=["TEST 220"]) == []


def test_coreq_may_be_taken_earlier_or_in_the_same_semester():
    assert check([["TEST 101", "TEST 110"], ["TEST 230"]]) == []
    assert check([["TEST 101"], ["TEST 110", "TEST 230"]]) == []


def test_coreq_taken_later_does_not_count():
    assert types(check([["TEST 101"], ["TEST 230"], ["TEST 110"]])) == ["coreq"]


def test_prereq_cannot_be_satisfied_like_a_coreq():
    # TEST 101 is a prereq of TEST 230, so the same semester is not enough.
    assert types(check([["TEST 101", "TEST 110", "TEST 230"]])) == ["prereq"]


# --- other rule violations -----------------------------------------------------

def test_unknown_course_is_reported():
    problems = check([["TEST 999"]])
    assert types(problems) == ["unknown_course"]
    assert "TEST 999" in problems[0]


def test_already_completed_course_is_reported():
    assert types(check([["TEST 101"]], completed=["TEST 101"])) == ["already_completed"]


def test_course_scheduled_twice_is_reported():
    problems = check([["TEST 101"], ["TEST 101"]])
    assert types(problems) == ["repeat"]
    assert "semester 1" in problems[0]


def test_unit_limit_is_enforced_per_semester():
    plan = [["TEST 101", "TEST 110", "TEST 120"]]  # 9 units
    assert check(plan, max_units=9) == []
    problems = check(plan, max_units=8)
    assert types(problems) == ["units"]
    assert "9 units" in problems[0]


def test_too_many_semesters_is_reported():
    assert types(check([["TEST 101"], ["TEST 110"], ["TEST 120"]], semesters=2)) == ["semesters"]


def test_limits_are_skipped_when_profile_omits_them():
    plan = [["TEST 101", "TEST 110", "TEST 120"], [], [], [], []]
    assert validate_plan(plan, {}, courses=COURSES, requirements=NO_REQUIREMENTS) == []


def test_one_bad_plan_reports_every_violation():
    plan = [["TEST 301", "TEST 999"], ["TEST 201", "TEST 101", "TEST 350"]]
    problems = check(plan, completed=["TEST 101"], max_units=7)
    assert sorted(types(problems)) == ["already_completed", "prereq", "prereq", "units", "unknown_course"]


# --- degree requirements -------------------------------------------------------

REQUIREMENTS = {"required": ["TEST 101", "TEST 201"], "electives": ["TEST 350", "TEST 360"], "elective_units": 6}


def test_requirements_met():
    plan = [["TEST 101"], ["TEST 201"], ["TEST 350", "TEST 360"]]
    assert check(plan, requirements=REQUIREMENTS) == []


def test_required_course_never_scheduled():
    plan = [["TEST 101"]]
    problems = check(plan, requirements={"required": ["TEST 101", "TEST 201"]})
    assert types(problems) == ["requirement"]
    assert "TEST 201" in problems[0]


def test_completed_courses_count_toward_requirements():
    assert check([], completed=["TEST 101", "TEST 201"], requirements={"required": ["TEST 101", "TEST 201"]}) == []


def test_not_enough_elective_units():
    plan = [["TEST 101"], ["TEST 201"], ["TEST 350"]]
    problems = check(plan, requirements=REQUIREMENTS)
    assert types(problems) == ["requirement"]
    assert "3 elective units but 6" in problems[0]


# --- helpers -------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["TEST 101", "test101", " Test  101 ", "TEST101"])
def test_course_ids_are_normalized(raw):
    assert normalize_id(raw) == "TEST 101"
    assert check([[raw]]) == []


def test_unmet_prereqs_accepts_every_rule_shape():
    done = {"TEST 101"}
    assert unmet_prereqs(None, done) == ""
    assert unmet_prereqs({"all": []}, done) == ""
    assert unmet_prereqs("TEST 101", done) == ""
    assert unmet_prereqs(["TEST 101", "TEST 110"], done) == "TEST 110"
    assert unmet_prereqs({"any": ["TEST 110", {"all": ["TEST 101", "TEST 120"]}]}, done) == "(TEST 110 or TEST 120)"
    with pytest.raises(ValueError):
        unmet_prereqs({"one_of": ["TEST 101"]}, done)


def test_empty_or_missing_data_files_load_as_empty(tmp_path):
    empty = tmp_path / "courses.json"
    empty.write_text("")
    assert load_courses(empty) == {}
    assert load_courses(tmp_path / "missing.json") == {}
    assert load_requirements(tmp_path / "missing.json") is None
