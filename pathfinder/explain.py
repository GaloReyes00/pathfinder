
import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "courses.json"


def load_courses():
    """Load the SFSU CS course dataset."""

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def explain_plan(plan, profile=None, courses=None, skill_scores=None):
    """Explain why each course appears in a recommended plan."""

    if courses is None:
        courses = load_courses()

    if skill_scores is None:
        skill_scores = []

    course_lookup = {
        course["id"]: course
        for course in courses
    }

    score_lookup = {
        item["course_id"]: item
        for item in skill_scores
    }

    if isinstance(plan, list):
        course_ids = plan

    elif isinstance(plan, dict):
        course_ids = []

        for semester in plan.get("semesters", []):
            if isinstance(semester, dict):
                course_ids.extend(semester.get("courses", []))
            elif isinstance(semester, list):
                course_ids.extend(semester)

    else:
        raise ValueError("Plan must be a list or dictionary.")

    explanations = []

    for course_id in course_ids:
        course = course_lookup.get(course_id)

        if course is None:
            continue

        match = score_lookup.get(course_id, {})

        matched_skills = match.get("matched_skills", [])
        related_matches = match.get("related_matches", [])

        explanation = (
            f"{course['id']} - {course['title']} "
            f"({course['units']} units). "
        )

        if matched_skills:
            explanation += (
                "Directly matches job skills: "
                + ", ".join(matched_skills) + ". "
            )

        if related_matches:
            explanation += (
                "May support related job skills through "
                "related course topics: "
                + ", ".join(related_matches) + "."
            )

        if not matched_skills and not related_matches:
            explanation += (
                "No direct or related job-skill matches "
                "were identified."
            )

        explanations.append({
            "course_id": course_id,
            "title": course["title"],
            "explanation": explanation
        })

    return explanations
