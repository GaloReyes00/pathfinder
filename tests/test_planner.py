"""Tests for pathfinder/planner.py. Run from the repo root with: python -m pytest -q

Most tests use the made-up TEST courses in tests/sample_courses.json:
  TEST 101 -> TEST 201 -> TEST 301 -> TEST 400   (TEST 301 also needs TEST 110 or TEST 120)
  TEST 350 and TEST 360 are electives that need TEST 201
  TEST 220 (lecture) and TEST 222 (lab) are each other's coreqs; TEST 230 has coreq TEST 110
The last tests run the planner on the real dataset in data/.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("ortools")

from pathfinder.planner import NoValidPlan, build_plan, format_plan  # noqa: E402
from pathfinder.validator import load_courses, load_requirements, validate_plan  # noqa: E402

COURSES = load_courses(Path(__file__).parent / "sample_courses.json")
DEGREE = {
    "required": ["TEST 101", "TEST 201", "TEST 301", "TEST 400"],
    "electives": ["TEST 350", "TEST 360"],
    "elective_units": 3,
}


def plan_for(relevance=None, completed=(), max_units=9, semesters=6, requirements=DEGREE):
    profile = {"completed": list(completed), "max_units": max_units, "semesters": semesters}
    plan = build_plan(profile, relevance, courses=COURSES, requirements=requirements)
    assert validate_plan(plan, profile, courses=COURSES, requirements=requirements) == []
    return plan


def flat(plan):
    return [course for semester in plan for course in semester]


def semester_of(plan, course_id):
    return next(number for number, semester in enumerate(plan, start=1) if course_id in semester)


# --- degree requirements -------------------------------------------------------

def test_plan_schedules_every_required_course():
    plan = plan_for()
    assert set(DEGREE["required"]) <= set(flat(plan))


def test_plan_finishes_as_early_as_the_prerequisite_chain_allows():
    # TEST 101 -> 201 -> 301 -> 400 is four semesters long, even though six are available.
    assert len(plan_for(semesters=6)) == 4


def test_plan_adds_exactly_one_course_to_satisfy_an_any_rule():
    plan = flat(plan_for())
    assert ("TEST 110" in plan) != ("TEST 120" in plan)


def test_plan_takes_exactly_the_elective_units_required():
    plan = flat(plan_for({"TEST 350": 0.9, "TEST 360": 0.9}))
    assert len([c for c in plan if c in DEGREE["electives"]]) == 1


def test_no_courses_that_count_toward_nothing():
    plan = set(flat(plan_for()))
    assert plan & {"TEST 220", "TEST 222", "TEST 230"} == set()


# --- relevance -----------------------------------------------------------------

def test_plan_picks_the_more_relevant_elective():
    assert "TEST 350" in flat(plan_for({"TEST 350": 0.9, "TEST 360": 0.1}))
    assert "TEST 360" in flat(plan_for({"TEST 350": 0.1, "TEST 360": 0.9}))


def test_relevance_accepts_the_score_courses_list_format():
    scores = [
        {"course_id": "TEST 360", "title": "Elective B", "score": 0.8, "matched_skills": ["x"]},
        {"course_id": "TEST 350", "title": "Elective A", "score": 0.2, "matched_skills": []},
    ]
    assert "TEST 360" in flat(plan_for(scores))


def test_without_requirements_plan_chases_relevance_and_adds_prerequisites():
    plan = flat(plan_for({"TEST 301": 1.0}, requirements={}))
    assert {"TEST 101", "TEST 201", "TEST 301"} <= set(plan)
    assert ("TEST 110" in plan) != ("TEST 120" in plan)
    assert len(plan) == 4  # nothing that was not needed


def test_nothing_to_do_gives_an_empty_plan():
    assert plan_for(requirements={}) == []


# --- limits --------------------------------------------------------------------

def test_completed_courses_are_not_scheduled_again():
    plan = flat(plan_for(completed=["TEST 101", "TEST 110"]))
    assert "TEST 101" not in plan and "TEST 110" not in plan and "TEST 120" not in plan


def test_unit_limit_is_respected():
    plan = plan_for(max_units=4, semesters=8)
    for semester in plan:
        assert sum(COURSES[c]["units"] for c in semester) <= 4


def test_impossible_profile_raises_no_valid_plan():
    with pytest.raises(NoValidPlan):
        plan_for(semesters=2)
    with pytest.raises(ValueError):  # NoValidPlan is a ValueError, so callers can catch either
        plan_for(max_units=3, semesters=3)


def test_missing_limits_fall_back_to_defaults():
    plan = build_plan({"completed": []}, courses=COURSES, requirements=DEGREE)
    assert validate_plan(plan, {"completed": []}, courses=COURSES, requirements=DEGREE) == []


# --- corequisites --------------------------------------------------------------

def test_mutual_coreqs_are_scheduled_in_the_same_semester():
    plan = plan_for(requirements={"required": ["TEST 220", "TEST 222"]})
    assert semester_of(plan, "TEST 220") == semester_of(plan, "TEST 222")


def test_one_way_coreq_is_scheduled_the_same_semester_or_earlier():
    plan = plan_for(requirements={"required": ["TEST 230"]})
    assert semester_of(plan, "TEST 110") <= semester_of(plan, "TEST 230")


# --- output --------------------------------------------------------------------

def test_plan_is_the_same_every_run():
    assert plan_for({"TEST 350": 0.5}) == plan_for({"TEST 350": 0.5})


def test_format_plan_lists_each_semester_with_units():
    text = format_plan([["TEST 101", "TEST 110"], ["TEST 201"]], COURSES)
    assert text.splitlines() == [
        "Semester 1 (6 units): TEST 101, TEST 110",
        "Semester 2 (4 units): TEST 201",
    ]


# --- the real dataset ----------------------------------------------------------

DATA = Path(__file__).resolve().parent.parent / "data"
REAL_COURSES = load_courses()
REAL_REQUIREMENTS = load_requirements() or {}
PROFILES_PATH = DATA / "profiles.json"
PROFILES = json.loads(PROFILES_PATH.read_text()) if PROFILES_PATH.exists() and PROFILES_PATH.read_text().strip() else []
needs_data = pytest.mark.skipif(not (REAL_COURSES and REAL_REQUIREMENTS), reason="data/ is not filled in yet")


@needs_data
@pytest.mark.parametrize("profile", PROFILES, ids=[p.get("id", "?") for p in PROFILES])
def test_every_real_profile_gets_a_valid_plan(profile):
    plan = build_plan(profile)
    assert validate_plan(plan, profile) == []
    assert len(plan) <= profile["semesters"]


@needs_data
def test_relevance_changes_which_real_electives_are_chosen():
    profile = {"completed": [], "max_units": 15, "semesters": 8}
    electives = [c for c in REAL_REQUIREMENTS["electives"] if c in {v["id"] for v in REAL_COURSES.values()}]
    favourite, least = electives[0], electives[-1]
    plan = flat(build_plan(profile, {favourite: 1.0, least: -1.0}))
    assert favourite in plan and least not in plan
    plan = flat(build_plan(profile, {favourite: -1.0, least: 1.0}))
    assert least in plan and favourite not in plan


@needs_data
def test_planner_accepts_what_score_courses_really_returns():
    matching = pytest.importorskip("pathfinder.matching")
    if not hasattr(matching, "score_courses"):
        pytest.skip("score_courses is not written yet")
    scores = matching.score_courses(["machine learning", "databases", "computer networks"])
    profile = {"completed": [], "max_units": 15, "semesters": 8}
    assert validate_plan(build_plan(profile, scores), profile) == []
