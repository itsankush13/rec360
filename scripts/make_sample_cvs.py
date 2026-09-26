"""
Generate a folder of sample CVs for exercising Phase C intake.

Produces good files and, deliberately, every bad case the upload screen has to
classify — a duplicate, a password-protected PDF, a corrupt PDF, a text-free
"scanned" PDF, an unsupported extension, and a CV with no contact details.
Testing only the happy path tells you almost nothing about bulk intake.

    python scripts/make_sample_cvs.py                    # writes ./sample_cvs
    python scripts/make_sample_cvs.py --out C:\\CVs      # somewhere else
    python scripts/make_sample_cvs.py --clean            # wipe first

Every name, email and phone number here is invented.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def cv_body(name, email, phone, city, years, skills, degree, employer):
    return "\n".join([
        name,
        email,
        phone,
        f"{city}, India",
        "",
        "SUMMARY",
        f"Backend engineer with {years} years building production services.",
        "",
        "EXPERIENCE",
        f"Senior Engineer, {employer} (2020-present).",
        "Owned service reliability and led a team of four engineers.",
        "Engineer, Globex Systems (2017-2020).",
        "Built and maintained REST APIs serving 2M requests per day.",
        "",
        "SKILLS",
        skills,
        "",
        "EDUCATION",
        degree,
        "",
        "CERTIFICATIONS",
        "AWS Certified Solutions Architect - Associate",
    ])


PEOPLE = [
    ("Priya Menon", "priya.menon@example.com", "+91 98765 43210", "Bengaluru", 8,
     "Python, AWS, PostgreSQL, Docker, Kubernetes, FastAPI", "B.Tech Computer Science, NIT Trichy", "Acme Payments"),
    ("Arun Verma", "arun.verma@example.com", "+91 91234 56780", "Pune", 6,
     "Python, Django, MySQL, Redis, Celery", "B.E. Information Technology, COEP Pune", "Initech Labs"),
    ("Neha Gupta", "neha.gupta@example.com", "+91 90011 22334", "Hyderabad", 11,
     "Java, Spring Boot, AWS, Kafka, PostgreSQL", "M.Tech Computer Science, IIT Hyderabad", "Umbrella Retail"),
    ("Rahul Iyer", "rahul.iyer@example.com", "+91 98111 22333", "Chennai", 3,
     "Python, Flask, SQLite, Git", "B.Sc Computer Science, Loyola College", "Soylent Digital"),
]


def make_pdf(text, path, user_password=None, blank=False):
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    if not blank:
        top = 60
        for line in text.split("\n"):
            page.insert_text((60, top), line, fontsize=10)
            top += 16
    if user_password:
        data = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw=user_password
        )
        path.write_bytes(data)
    else:
        document.save(str(path))
    document.close()


def make_docx(text, path):
    import docx

    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    document.save(str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="./sample_cvs")
    parser.add_argument("--clean", action="store_true", help="delete the folder first")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    created: list[tuple[str, str]] = []

    # --- Good files -------------------------------------------------------
    priya = cv_body(*PEOPLE[0])
    make_pdf(priya, out / "priya_menon.pdf")
    created.append(("priya_menon.pdf", "valid PDF -> COMPLETED"))

    make_docx(cv_body(*PEOPLE[1]), out / "arun_verma.docx")
    created.append(("arun_verma.docx", "valid DOCX -> COMPLETED"))

    make_pdf(cv_body(*PEOPLE[2]), out / "neha_gupta.pdf")
    created.append(("neha_gupta.pdf", "valid PDF -> COMPLETED"))

    make_pdf(cv_body(*PEOPLE[3]), out / "rahul_iyer.pdf")
    created.append(("rahul_iyer.pdf", "valid PDF -> COMPLETED"))

    # --- Exact duplicate: byte-identical copy -----------------------------
    shutil.copyfile(out / "priya_menon.pdf", out / "priya_menon_COPY.pdf")
    created.append(("priya_menon_COPY.pdf", "identical bytes -> DUPLICATE / EXACT_FILE"))

    # --- Same person, different file: phone in another format -------------
    same_person_reformatted = cv_body(
        "Priya M Menon", "priya.alternate@example.com", "098765-43210",
        "Bengaluru", 8, "Python, AWS, PostgreSQL, Terraform",
        "B.Tech Computer Science, NIT Trichy", "Acme Payments",
    )
    make_docx(same_person_reformatted, out / "priya_menon_v2.docx")
    created.append(("priya_menon_v2.docx", "same phone, new format -> DUPLICATE / SAME_CANDIDATE_PHONE"))

    # --- Password-protected ----------------------------------------------
    make_pdf(priya, out / "locked_cv.pdf", user_password="secret")
    created.append(("locked_cv.pdf", "encrypted -> FAILED / PASSWORD_PROTECTED"))

    # --- Corrupt ----------------------------------------------------------
    (out / "corrupt_cv.pdf").write_bytes(b"%PDF-1.4 this is not actually a valid PDF file")
    created.append(("corrupt_cv.pdf", "malformed -> FAILED / CORRUPT_FILE"))

    (out / "corrupt_cv.docx").write_bytes(b"not a zip archive at all")
    created.append(("corrupt_cv.docx", "malformed -> FAILED / CORRUPT_FILE"))

    # --- Text-free, i.e. a scan ------------------------------------------
    make_pdf("", out / "scanned_cv.pdf", blank=True)
    created.append(("scanned_cv.pdf", "no text layer -> FAILED / NO_TEXT_EXTRACTED"))

    # --- Unsupported extension -------------------------------------------
    (out / "notes.txt").write_text("Candidate looked promising on the call.", encoding="utf-8")
    created.append(("notes.txt", "wrong format -> FAILED / UNSUPPORTED_FORMAT"))

    # --- No contact details ----------------------------------------------
    anonymous = "\n".join([
        "CURRICULUM VITAE", "",
        "EXPERIENCE",
        "Backend engineer responsible for building and running Python services.",
        "Worked across payments, identity and reporting domains.",
        "Migrated a monolith to containerised microservices on AWS.", "",
        "SKILLS", "Python, AWS, PostgreSQL, Docker",
    ])
    make_pdf(anonymous, out / "anonymous_cv.pdf")
    created.append(("anonymous_cv.pdf", "no name/email/phone -> FAILED / INCOMPLETE_CONTENT"))

    # --- Name only, no email or phone ------------------------------------
    name_only = "\n".join([
        "Vikram Rao", "Kolkata", "",
        "EXPERIENCE",
        "Senior backend engineer building distributed Python services.",
        "Led the migration of billing infrastructure to Kubernetes.", "",
        "SKILLS", "Python, Kubernetes, PostgreSQL, Kafka",
    ])
    make_pdf(name_only, out / "name_only_cv.pdf")
    created.append(("name_only_cv.pdf", "partial identity -> COMPLETED but requires_review"))

    print(f"Wrote {len(created)} sample files to {out}\n")
    width = max(len(name) for name, _ in created)
    for name, expectation in created:
        print(f"  {name.ljust(width)}   {expectation}")
    print(
        "\nExpected totals: 5 COMPLETED (one flagged for review), "
        "2 DUPLICATE, 6 FAILED, and 5 candidates.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
