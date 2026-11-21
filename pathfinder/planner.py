"""Plan builder for PathFinder, using the Google OR-Tools CP-SAT constraint solver.

build_plan(profile, relevance) returns a semester-by-semester plan:

    [["MATH 226", "CSC 101"], ["MATH 227", "CSC 215"], ...]

Hard rules (the solver can never break these; they are the same rules validator.py checks):
  - a course is scheduled at most once, and never if it is already completed
  - prerequisites are finished in an earlier semester
  - corequisites are taken in the same semester or earlier
  - each semester stays within profile["max_units"]
  - the plan fits in profile["semesters"]
  - every required course is scheduled, and the elective-unit requirement is met

What it optimizes, in priority order:
  1. total relevance of the chosen courses (this is what decides WHICH electives are picked)
  2. finishing in as few semesters as possible
  3. taking courses as early as possible

Every plan is run through validate_plan() before it is returned.
"""
from __future__ import annotations

from ortools.sat.python import cp_model

from pathfinder.validator import load_courses, load_requirements, normalize_id, validate_plan

DEFAULT_SEMESTERS = 8
DEFAULT_MAX_UNITS = 15
RELEVANCE_SCALE = 1000    # CP-SAT needs whole numbers, so a relevance of 0.537 becomes 537
EXTRA_COURSE_COST = 100   # a course that counts toward nothing "costs" 0.1 relevance, so it is
                          # only added when it unlocks something worth more than that


class NoValidPlan(ValueError):
    """No plan can satisfy every rule within the profile's semester and unit limits."""


def _index_courses(courses):
    """Return {normalized id: course} from None (load the dataset), a dict, or a list."""
    if courses is None:
        return load_courses()
    if isinstance(courses, dict):
        return {normalize_id(course_id): course for course_id, course in courses.items()}
    return {normalize_id(course["id"]): course for course in courses}


def _relevance_map(relevance):
    """Accept {course_id: score} or the list that score_courses() returns
    ([{"course_id": "CSC 665", "score": 0.4, ...}, ...]) and return {normalized id: score}."""
    if not relevance:
        return {}
    if isinstance(relevance, dict):
        pairs = relevance.items()
    else:
        pairs = ((item.get("course_id"), item.get("score", 0)) for item in relevance)
    return {normalize_id(course_id): float(score or 0) for course_id, score in pairs if course_id}


def _holds(model, rule, semester, done):
    """Turn a prerequisite/corequisite rule into a 0/1 value that can only be 1 when the rule is met.

    `done(course_id, semester)` gives a 0/1 value saying whether that course is finished in time.
    Returns the int 0 or 1 when the answer is already known, otherwise a solver expression.
    """
    if not rule:
        return 1
    if isinstance(rule, str):
        return done(normalize_id(rule), semester)
    if isinstance(rule, list):
        rule = {"all": rule}
    if "all" not in rule and "any" not in rule:
        raise ValueError(f"Unrecognized prerequisite rule: {rule!r}")

    parts = [_holds(model, r, semester, done) for r in rule.get("all", [])]

    options = [_holds(model, r, semester, done) for r in rule.get("any", [])]
    if options:
        if any(isinstance(o, int) and o == 1 for o in options):
            parts.append(1)
        else:
            open_options = [o for o in options if not isinstance(o, int)]
            if not open_options:
                parts.append(0)
            elif len(open_options) == 1:
                parts.append(open_options[0])
            else:
                one_of = model.new_bool_var("")
                model.add(one_of <= sum(open_options))
                parts.append(one_of)

    if any(isinstance(p, int) and p == 0 for p in parts):
        return 0
    open_parts = [p for p in parts if not isinstance(p, int)]
    if not open_parts:
        return 1
    if len(open_parts) == 1:
        return open_parts[0]
    every = model.new_bool_var("")
    for part in open_parts:
        model.add(every <= part)
    return every


def build_plan(profile, relevance=None, courses=None, requirements=None, time_limit=10.0):
    """Build the most relevant valid plan for a student.

    profile       {"completed": [...], "max_units": 15, "semesters": 8}
    relevance     {course_id: score} or score_courses() output; missing courses count as 0
    courses       course dataset (list or dict); defaults to data/courses.json
    requirements  degree requirements dict; defaults to data/requirements.json.
                  Pass {} to ignore degree requirements and only chase relevance.

    Returns a list of semesters, each a list of course ids. Raises NoValidPlan (a ValueError)
    when the requirements cannot be met within the profile's limits.
    """
    courses = _index_courses(courses)
    if requirements is None:
        requirements = load_requirements() or {}
    scores = _relevance_map(relevance)

    completed = {normalize_id(c) for c in profile.get("completed", [])}
    semesters = profile.get("semesters") or DEFAULT_SEMESTERS
    max_units = profile.get("max_units") or DEFAULT_MAX_UNITS
    terms = range(1, semesters + 1)
    candidates = [course_id for course_id in courses if course_id not in completed]
    units = {course_id: courses[course_id].get("units", 0) for course_id in courses}

    required = [normalize_id(c) for c in requirements.get("required", []) if normalize_id(c) not in completed]
    unknown_required = [c for c in required if c not in courses]
    if unknown_required:
        raise NoValidPlan(f"Required courses missing from the dataset: {', '.join(unknown_required)}")
    electives = {normalize_id(c) for c in requirements.get("electives", [])} & set(courses)
    elective_units_left = max(
        0, requirements.get("elective_units", 0) - sum(units[c] for c in electives & completed)
    )

    model = cp_model.CpModel()
    take = {c: {s: model.new_bool_var(f"{c}@{s}") for s in terms} for c in candidates}
    taken = {c: sum(take[c].values()) for c in candidates}  # 1 if the course is in the plan at all

    for course_id in candidates:
        model.add(taken[course_id] <= 1)

    def finished_before(course_id, semester):
        if course_id in completed:
            return 1
        if course_id not in take:
            return 0  # not in the dataset and not completed, so it can never be satisfied
        return sum(take[course_id][t] for t in terms if t < semester) if semester > 1 else 0

    def finished_by(course_id, semester):
        if course_id in completed:
            return 1
        if course_id not in take:
            return 0
        return sum(take[course_id][t] for t in terms if t <= semester)

    for course_id in candidates:
        course = courses[course_id]
        for s in terms:
            for rule, done in ((course.get("prereqs"), finished_before), (course.get("coreqs"), finished_by)):
                allowed = _holds(model, rule, s, done)
                if isinstance(allowed, int):
                    if allowed == 0:
                        model.add(take[course_id][s] == 0)
                else:
                    model.add(take[course_id][s] <= allowed)

    for s in terms:
        model.add(sum(units[c] * take[c][s] for c in candidates) <= max_units)

    for course_id in required:
        model.add(taken[course_id] == 1)

    elective_candidates = [c for c in candidates if c in electives]
    elective_units = sum(units[c] * taken[c] for c in elective_candidates)
    if elective_units_left > 0:
        biggest = max((units[c] for c in elective_candidates), default=0)
        model.add(elective_units >= elective_units_left)
        model.add(elective_units <= elective_units_left + max(biggest - 1, 0))  # no extra electives

    # Which courses "count". With degree requirements, that is the required courses plus electives
    # (only while elective units are still needed). Anything else counts toward nothing and is only
    # scheduled when it unlocks a course that does count. Without requirements, every course counts.
    if requirements:
        counts = set(required) | (electives if elective_units_left > 0 else set())
    else:
        counts = set(candidates)

    last = model.new_int_var(0, semesters, "last_semester_used")
    for course_id in candidates:
        for s in terms:
            model.add(last >= s * take[course_id][s])

    # Weights that make the three goals strictly ordered: relevance, then fewer semesters, then earlier.
    earliness_max = semesters * len(candidates)
    semester_weight = earliness_max + 1
    relevance_weight = semester_weight * semesters + earliness_max + 1
    objective = []
    for course_id in candidates:
        if course_id in counts:
            value = round(RELEVANCE_SCALE * scores.get(course_id, 0.0))
        else:
            value = -EXTRA_COURSE_COST
        objective.append(relevance_weight * value * taken[course_id])
        objective.extend(-s * take[course_id][s] for s in terms)
    objective.append(-semester_weight * last)
    model.maximize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = 1  # one worker keeps the result the same on every run
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise NoValidPlan(
            f"No valid plan fits in {semesters} semesters with at most {max_units} units per semester. "
            "Try more semesters or a higher unit limit."
        )

    plan = [[courses[c]["id"] for c in candidates if solver.value(take[c][s])] for s in terms]
    while plan and not plan[-1]:
        plan.pop()

    problems = validate_plan(plan, profile, courses=courses, requirements=requirements)
    if problems:
        raise RuntimeError("Planner produced a plan the validator rejects: " + "; ".join(problems))
    return plan


def format_plan(plan, courses=None):
    """Readable text for a plan, one line per semester, for the notebook and the app."""
    courses = _index_courses(courses)
    lines = []
    for number, semester in enumerate(plan, start=1):
        total = sum(courses[normalize_id(c)].get("units", 0) for c in semester if normalize_id(c) in courses)
        lines.append(f"Semester {number} ({total} units): " + ", ".join(semester))
    return "\n".join(lines)
