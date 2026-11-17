
import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "courses.json"


# Terms that are closely related to specific job skills.
SKILL_TOPICS = {
    "Python": ["Python programming"],
    "Java": ["Java programming"],
    "C++": ["C++ programming"],
    "C": ["C programming"],
    "JavaScript": ["JavaScript programming"],
    "SQL": ["database systems", "relational database"],
    "AWS": ["cloud computing", "cloud services"],
    "Azure": ["cloud computing", "cloud services"],
    "Google Cloud": ["cloud computing", "cloud services"],
    "Apache Spark": ["big data", "distributed computing"],
    "Apache Airflow": ["workflow automation", "data pipelines"],
    "ETL pipelines": ["data integration", "data processing"],
    "distributed systems": ["distributed computing"],
    "data structures": ["data structures and algorithms"],
    "algorithms": ["algorithm analysis"],
    "machine learning": ["predictive modeling"],
    "deep learning": ["neural networks"],
    "artificial intelligence": ["intelligent systems"],
    "neural networks": ["deep learning"],
    "natural language processing": ["language processing"],
    "databases": ["database systems", "relational database"],
    "database design": ["data modeling"],
    "cybersecurity": ["computer security", "network security"],
    "cryptography": ["information security"],
    "data privacy": ["information security"],
    "computer networks": ["network protocols"],
    "Linux": ["Linux operating system"],
    "operating systems": ["operating system principles"],
    "software engineering": ["software engineering principles"],
    "web development": ["web software development"],
    "mobile development": ["mobile applications"],
    "React": ["frontend development"],
    "Node.js": ["backend development"]
}


def load_courses():
    """Load the SFSU CS course dataset."""

    with open(DATA_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def score_courses(skills, courses=None):
    """Rank courses by direct and related skill matches."""

    if not isinstance(skills, list):
        raise ValueError("Skills must be a list.")

    if courses is None:
        courses = load_courses()

    results = []

    for course in courses:
        course_text = (
            course.get("title", "") + " " +
            course.get("description", "")
        ).lower()

        matched_skills = []
        related_matches = []

        for skill in skills:
            if not isinstance(skill, str) or not skill.strip():
                continue

            skill = skill.strip()
            skill_text = skill.lower()

            if skill_text in course_text:
                matched_skills.append(skill)
                continue

            related_terms = SKILL_TOPICS.get(skill, [])

            for term in related_terms:
                if term.lower() in course_text:
                    related_matches.append(skill)
                    break

        score = (
            len(matched_skills) +
            len(related_matches) * 0.5
        )

        if skills:
            score = score / len(skills)
        else:
            score = 0.0

        results.append({
            "course_id": course.get("id"),
            "title": course.get("title"),
            "units": course.get("units"),
            "score": round(score, 4),
            "matched_skills": matched_skills,
            "related_matches": related_matches
        })

    results.sort(
        key=lambda course: course["score"],
        reverse=True
    )

    return results
