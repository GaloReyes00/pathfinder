"""Plan validator for PathFinder.

validate_plan(plan, profile) checks a semester-by-semester plan against the course
dataset and returns a list of violations. An empty list means the plan is valid.

The same function grades PathFinder's own plans and the LLM-only baseline's plans,
so both systems are measured by identical rules.

Shapes
------
plan     [["CSC 101", "CSC 110"], ["CSC 201"], ...]   one inner list per semester
profile  {"completed": ["CSC 101"], "max_units": 15, "semesters": 4}
course   {"id": "CSC 201", "units": 3, "prereqs": {"all": ["CSC 101", {"any": ["CSC 110", "CSC 120"]}]}}

Every violation is a string that starts with its type, then a colon:
unknown_course, already_completed, repeat, prereq, units, semesters, requirement.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def normalize_id(course_id):
    """Make course ids comparable: ' csc415 ' and 'CSC  415' both become 'CSC 415'."""
    text = re.sub(r"\s+", " ", str(course_id).strip().upper())
    match = re.fullmatch(r"([A-Z]+) ?(\d.*)", text)
    return f"{match.group(1)} {match.group(2)}" if match else text


def _read_json(path, default):
    """Read a JSON file, treating a missing or empty file as `default`."""
    path = Path(path)
    text = path.read_text().strip() if path.exists() else ""
    return json.loads(text) if text else default


def load_courses(path=None):
    """Load the course dataset as {course_id: course}. Defaults to data/courses.json."""
    courses = _read_json(path or DATA_DIR / "courses.json", [])
    return {normalize_id(course["id"]): course for course in courses}


def load_requirements(path=None):
    """Load degree requirements, or None if data/requirements.json is missing or empty.

    Format: {"required": ["CSC 101", ...], "electives": ["CSC 350", ...], "elective_units": 12}
    """
    return _read_json(path or DATA_DIR / "requirements.json", None)


def unmet_prereqs(rule, done):
    """Describe which part of a prerequisite rule is not satisfied by the set `done`.

    Returns "" when the rule is satisfied. A rule is a course id, a list (all required),
    or a dict with "all" and/or "any" lists, which can be nested.
    """
    if not rule:
        return ""
    if isinstance(rule, str):
        course_id = normalize_id(rule)
        return "" if course_id in done else course_id
    if isinstance(rule, list):
        rule = {"all": rule}
    if "all" not in rule and "any" not in rule:
        raise ValueError(f"Unrecognized prerequisite rule: {rule!r}")

    missing = [m for m in (unmet_prereqs(r, done) for r in rule.get("all", [])) if m]

    options = [unmet_prereqs(r, done) for r in rule.get("any", [])]
    if options and all(options):  # every alternative is still missing something
        wrapped = [f"({o})" if " and " in o else o for o in options]
        missing.append(wrapped[0] if len(wrapped) == 1 else "(" + " or ".join(wrapped) + ")")

    return " and ".join(missing)


def validate_plan(plan, profile, courses=None, requirements=None):
    """Return a list of rule violations for `plan`. An empty list means the plan is valid.

    courses       course dataset as a list or {id: course}; defaults to data/courses.json
    requirements  degree requirements dict; defaults to data/requirements.json if it exists
    """
    if courses is None:
        courses = load_courses()
    elif isinstance(courses, dict):
        courses = {normalize_id(course_id): course for course_id, course in courses.items()}
    else:
        courses = {normalize_id(course["id"]): course for course in courses}
    if requirements is None:
        requirements = load_requirements()

    completed = {normalize_id(c) for c in profile.get("completed", [])}
    max_units = profile.get("max_units")
    max_semesters = profile.get("semesters")

    problems = []
    done = set(completed)  # everything finished before the semester being checked
    scheduled_in = {}      # course id -> semester number where the plan first schedules it

    if max_semesters is not None and len(plan) > max_semesters:
        problems.append(f"semesters: Plan uses {len(plan)} semesters but the limit is {max_semesters}.")

    for number, semester in enumerate(plan, start=1):
        course_ids = [normalize_id(c) for c in semester]
        units = 0
        for course_id in course_ids:
            where = f"Semester {number}: {course_id}"
            if course_id not in courses:
                problems.append(f"unknown_course: {where} is not in the course dataset.")
                continue
            units += courses[course_id].get("units", 0)
            if course_id in completed:
                problems.append(f"already_completed: {where} was already completed.")
                continue
            if course_id in scheduled_in:
                problems.append(f"repeat: {where} is already scheduled in semester {scheduled_in[course_id]}.")
                continue
            scheduled_in[course_id] = number
            missing = unmet_prereqs(courses[course_id].get("prereqs"), done)
            if missing:
                problems.append(f"prereq: {where} needs {missing} in an earlier semester.")
        if max_units is not None and units > max_units:
            problems.append(f"units: Semester {number} has {units} units but the limit is {max_units}.")
        # Courses only count as prerequisites for later semesters, never the same one.
        done.update(c for c in course_ids if c in courses)

    if requirements:
        for course_id in requirements.get("required", []):
            if normalize_id(course_id) not in done:
                problems.append(f"requirement: Required course {normalize_id(course_id)} is never scheduled.")
        needed = requirements.get("elective_units", 0)
        if needed:
            electives = {normalize_id(c) for c in requirements.get("electives", [])}
            earned = sum(courses[c].get("units", 0) for c in done & electives if c in courses)
            if earned < needed:
                problems.append(f"requirement: Plan reaches {earned} elective units but {needed} are required.")

    return problems
