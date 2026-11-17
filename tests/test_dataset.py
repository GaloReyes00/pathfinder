"""Sanity checks for the real dataset in data/. Run from the repo root with: python -m pytest -q

These catch data mistakes (a typo in a course id, a rule the validator cannot read,
a required course that is missing) before they break the planner. They are skipped
while data/courses.json is still empty.
"""
import json
from pathlib import Path

import pytest

from pathfinder.validator import load_courses, load_requirements, normalize_id, unmet_prereqs

DATA = Path(__file__).resolve().parent.parent / "data"
COURSES = load_courses()
REQUIREMENTS = load_requirements() or {}
PROFILES_PATH = DATA / "profiles.json"
PROFILES = json.loads(PROFILES_PATH.read_text()) if PROFILES_PATH.exists() and PROFILES_PATH.read_text().strip() else []

pytestmark = pytest.mark.skipif(not COURSES, reason="data/courses.json is empty")


def test_course_ids_are_unique():
    raw = json.loads((DATA / "courses.json").read_text())
    ids = [normalize_id(course["id"]) for course in raw]
    assert len(ids) == len(set(ids)), "duplicate course ids in data/courses.json"


@pytest.mark.parametrize("course_id", sorted(COURSES))
def test_course_has_the_agreed_fields(course_id):
    course = COURSES[course_id]
    for field in ("id", "title", "units", "description", "prereqs"):
        assert field in course, f"{course_id} is missing '{field}'"
    assert isinstance(course["units"], int) and course["units"] > 0, f"{course_id} needs whole-number units"


@pytest.mark.parametrize("course_id", sorted(COURSES))
def test_course_rules_are_readable_and_satisfiable(course_id):
    """With every course in the dataset finished, no prereq or coreq rule may still be unmet."""
    everything = set(COURSES)
    course = COURSES[course_id]
    assert unmet_prereqs(course["prereqs"], everything) == "", f"{course_id} can never be scheduled"
    assert unmet_prereqs(course.get("coreqs"), everything) == "", f"{course_id} has a coreq outside the dataset"


def test_every_course_can_be_reached_from_scratch():
    """Starting with nothing completed, repeatedly take whatever is unlocked. Nothing may be left over."""
    done = set()
    while True:
        unlocked = {
            cid for cid, course in COURSES.items()
            if cid not in done and not unmet_prereqs(course["prereqs"], done)
        }
        if not unlocked:
            break
        done |= unlocked
    assert set(COURSES) - done == set(), "these courses are locked behind a prerequisite cycle or a missing course"


@pytest.mark.skipif(not REQUIREMENTS, reason="data/requirements.json is empty")
def test_required_courses_exist_in_the_dataset():
    missing = [c for c in REQUIREMENTS.get("required", []) if normalize_id(c) not in COURSES]
    assert missing == [], "required courses missing from data/courses.json"


@pytest.mark.skipif(not REQUIREMENTS, reason="data/requirements.json is empty")
def test_enough_elective_units_are_available():
    electives = {normalize_id(c) for c in REQUIREMENTS.get("electives", [])}
    available = sum(COURSES[c]["units"] for c in electives if c in COURSES)
    assert available >= REQUIREMENTS.get("elective_units", 0)


@pytest.mark.parametrize("profile", PROFILES, ids=[p.get("id", "?") for p in PROFILES])
def test_profile_is_well_formed(profile):
    assert isinstance(profile.get("completed"), list)
    assert isinstance(profile.get("max_units"), int) and profile["max_units"] > 0
    assert isinstance(profile.get("semesters"), int) and profile["semesters"] > 0
    # Completed courses may be outside the dataset (for example a transfer equivalent), so only the type is checked.
    assert all(isinstance(c, str) for c in profile["completed"])
