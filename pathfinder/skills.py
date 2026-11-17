
import re


SKILL_VOCABULARY = [
    "Python",
    "Java",
    "C++",
    "C",
    "JavaScript",
    "HTML",
    "CSS",
    "SQL",
    "MATLAB",
    "AWS",
    "Azure",
    "Google Cloud",
    "Apache Spark",
    "Apache Airflow",
    "ETL pipelines",
    "distributed systems",
    "data structures",
    "algorithms",
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "neural networks",
    "natural language processing",
    "databases",
    "database design",
    "cybersecurity",
    "cryptography",
    "data privacy",
    "computer networks",
    "TCP/IP",
    "Linux",
    "operating systems",
    "software engineering",
    "object-oriented programming",
    "web development",
    "mobile development",
    "React",
    "Node.js",
    "Git",
    "version control",
    "network protocols",
    "user interface design"
]


def extract_skills(job_posting):
    """Extract recognized technical skills from a job posting."""

    if not isinstance(job_posting, str) or not job_posting.strip():
        raise ValueError("Job posting cannot be empty.")

    text = job_posting.lower()
    skills = []

    for skill in SKILL_VOCABULARY:
        pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"

        if re.search(pattern, text):
            skills.append(skill)

    return skills
