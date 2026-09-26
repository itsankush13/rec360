"""
Idempotent demo-seed script — docs/plan/DEMO-READINESS-2026-09-14.md P0-5.

Seeds, through the real API/service layer (never page-only HTML, never a
direct row insert into a lifecycle table), the QChem demo dataset:

- A 4-entry JD library (`jd_templates`): HSE Officer, Maintenance Engineer,
  Process Operator, Process Engineer.
- Campaign A (Maintenance Engineer): 3 real CVs screened, top candidate
  shortlisted, sent to the hiring manager, reviewed (PROCEED), interview
  scheduled — deliberately left there, awaiting feedback. "Partway through
  manager review/interview."
- Campaign B (Process Engineer): 3 real CVs screened, top
  candidate carried all the way through interview feedback, HR approval,
  cost-centre budget sign-off (against a synthetic QAR BU envelope) and an
  offer recorded as sent — awaiting the candidate's response. "HR/budget
  approval or offer stage."

Campaign C (Process Operator, the live walkthrough) and Campaign D (HSE
Officer, backup) are deliberately NOT created here — see the readiness doc
for why.

Every row this script creates is named `QChem Demo — …` so it is
recognisable in `start-campaign.html`'s filter box and never mistaken for
the 45 pre-existing dev/test campaigns already in this database, which are
left completely untouched.

Idempotent: reruns detect an existing campaign by its exact `name` and skip
re-creating it (no duplication). `--dry-run` prints the plan and makes zero
mutating calls.

Usage (from the repo root, with the venv active):
    .\\venv\\Scripts\\python.exe scripts\\seed_demo.py --dry-run
    .\\venv\\Scripts\\python.exe scripts\\seed_demo.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QUEUE_BACKEND", "inline")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docx  # noqa: E402

# The JD and CV fixture folders are NOT part of the git repo - they hold
# source documents that are shared out of band. By default they sit one
# level above the repo root, in the shared Resume-Screening workspace. On a
# machine where the clone lives somewhere else, point JD_REPOSITORY_DIR and
# CV_REPOSITORY_DIR at wherever the two folders were unpacked.
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
JD_DIR = Path(os.environ.get("JD_REPOSITORY_DIR") or WORKSPACE_ROOT / "JD-Repository")
CV_DIR = Path(os.environ.get("CV_REPOSITORY_DIR") or WORKSPACE_ROOT / "CV-Repository")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME = "application/pdf"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _ext_mime(path: Path) -> str:
    return {".docx": DOCX_MIME, ".pdf": PDF_MIME, ".pptx": PPTX_MIME}[path.suffix.lower()]


def synthetic_candidate_email(full_name: str) -> str:
    """A demo-safe address for a candidate — never the address on their CV.
    Same @qchem-demo.example domain as the seeded users."""
    parts = re.findall(r"[A-Za-z]+", full_name)
    return ".".join(p.lower() for p in parts) + "@qchem-demo.example"


def read_docx_text(path: Path) -> str:
    d = docx.Document(str(path))
    return "\n".join(p.text for p in d.paragraphs if p.text.strip())


# ---------------------------------------------------------------------------
# The four JDs and their matched, content-verified candidate CVs.
# See docs/plan/DEMO-READINESS-2026-09-14.md for the rationale.
# ---------------------------------------------------------------------------

JDS = {
    "HSE Officer": {
        "file": JD_DIR / "JD_HSE_Officer.docx",
        "tags": "QChem,HSE,Safety,backup-unused",
        "cvs": [
            "Resume_HSEOfficer_GraceOwusu_HeaderInfo_SkillsSpread.docx",
            "Resume_HSEOfficer_MichaelFitzgerald_ChaoticFormat.docx",
            "Resume_HSEOfficer_TariqAlNaimi_ParagraphExperience.docx",
        ],
    },
    "Maintenance Engineer": {
        "file": JD_DIR / "JD_Maintenance_Engineer.docx",
        "tags": "QChem,Maintenance,Reliability,campaign-A",
        "cvs": [
            "Resume_MaintenanceEngineer_AbdulrahmanAlSada_TinyFont.docx",
            "Resume_MaintenanceEngineer_CarlosMendes_Tables.docx",
            "Resume_MaintenanceEngineer_PriyaMenon_DateVariations.docx",
        ],
    },
    "Process Operator": {
        "file": JD_DIR / "JD_Process_Operator.docx",
        "tags": "QChem,Operations,live-walkthrough",
        "cvs": [
            "Resume_ProcessOperator_HanaAlEmadi.pptx",
            "Resume_ProcessOperator_JamesOBrien_PoorFormat_HeaderInfo.docx",
            "Resume_ProcessOperator_SureshNair_ScannedPDF.pdf",
        ],
    },
    "Process Engineer": {
        "file": JD_DIR / "JD_Process_Engineer (1).docx",
        "tags": "QChem,Process,Petrochemical,campaign-B",
        "cvs": [
            "Resume_ProcessEngineer_DanielCruz_Unstructured.docx",
            "Resume_ProcessEngineer_FahadAlKuwari_MultiPageTables.docx",
            "Resume_ProcessEngineer_YoussefAlAttiyah_Polished.docx",
        ],
    },
}

CAMPAIGN_A_NAME = "QChem Demo — Campaign A — Maintenance Engineer"
CAMPAIGN_B_NAME = "QChem Demo — Campaign B — Process Engineer"

PEOPLE = {
    "recruiter": {"full_name": "Layla Haddad", "email": "layla.haddad@qchem-demo.example", "role": "RECRUITER"},
    "manager_a": {"full_name": "Yusuf Al-Marri", "email": "yusuf.almarri@qchem-demo.example", "role": "HIRING_MANAGER"},
    "manager_b": {"full_name": "Noora Al-Thani", "email": "noora.althani@qchem-demo.example", "role": "HIRING_MANAGER"},
    "admin": {"full_name": "Imran Qureshi", "email": "imran.qureshi@qchem-demo.example", "role": "ADMIN"},
}

COST_CENTRE = {
    "code": "CC-QCHEM-PE",
    "name": "Process Engineering",
    "business_unit": "Technical Services",
    "currency": "QAR",
    "fiscal_year": "FY2026",
    "role_grade": "Engineer II",
    "approved_headcount": 2,
    "salary_band_min": 180000,
    "salary_band_max": 220000,
}


class Seeder:
    def __init__(self, client, dry_run: bool):
        self.client = client
        self.dry_run = dry_run
        self.people: dict[str, dict] = {}

    def log(self, message: str) -> None:
        print(("[dry-run] " if self.dry_run else "") + message)

    # -- generic helpers ----------------------------------------------------

    def post(self, path: str, json: dict | None = None, **kwargs):
        if self.dry_run:
            self.log(f"POST {path} {json if json is not None else ''}")
            return None
        response = self.client.post(path, json=json, **kwargs)
        assert response.status_code < 300, f"{path} -> {response.status_code}: {response.text}"
        return response.json()

    def get(self, path: str):
        response = self.client.get(path)
        assert response.status_code < 300, f"{path} -> {response.status_code}: {response.text}"
        return response.json()

    def lifecycle_status_or_none(self, campaign_id: str, candidate_id: str) -> str | None:
        """A candidate not yet entered into the hiring process 404s here —
        that is the "not progressed yet" signal this seed script's
        idempotency check needs, not a real error."""
        response = self.client.get(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}")
        if response.status_code == 404:
            return None
        assert response.status_code < 300, f"lifecycle -> {response.status_code}: {response.text}"
        return response.json().get("status")

    # -- JD library -----------------------------------------------------

    def seed_jd_library(self) -> dict[str, str]:
        existing = {t["role_title"]: t["id"] for t in self.get("/api/jd-library")}
        template_ids = {}
        for role_title, spec in JDS.items():
            if role_title in existing:
                self.log(f"JD template already on file: {role_title}")
                template_ids[role_title] = existing[role_title]
                continue
            body = read_docx_text(spec["file"])
            self.log(f"Creating JD template: {role_title} ({len(body)} chars)")
            created = self.post("/api/jd-library", json={
                "role_title": role_title,
                "summary": body.split("\n")[3][:200] if len(body.split("\n")) > 3 else "",
                "body": body,
                "tags": spec["tags"],
                "source_file": spec["file"].name,
                "created_by": "seed_demo.py",
            })
            template_ids[role_title] = created["id"] if created else None
        return template_ids

    # -- people -----------------------------------------------------------

    def seed_people(self) -> None:
        existing = {u["email"]: u for u in self.get("/api/users")}
        for key, spec in PEOPLE.items():
            if spec["email"] in existing:
                self.people[key] = existing[spec["email"]]
                continue
            self.log(f"Creating user: {spec['full_name']} ({spec['role']})")
            created = self.post("/api/users", json=spec)
            self.people[key] = created or {"id": f"dry-run-{key}", **spec}

    def seed_cost_centre(self) -> None:
        existing = {c["code"]: c for c in self.get("/api/cost-centres")}
        if COST_CENTRE["code"] in existing:
            self.log(f"Cost centre already on file: {COST_CENTRE['code']}")
            return
        self.log(f"Creating cost centre: {COST_CENTRE['code']} ({COST_CENTRE['business_unit']})")
        self.post("/api/cost-centres", json={**COST_CENTRE, "budget_holder_id": self.people["admin"]["id"]})

    # -- campaign build (shared by A and B) --------------------------------

    def find_campaign(self, name: str) -> dict | None:
        for c in self.get("/api/campaigns"):
            if c["name"] == name:
                return c
        return None

    def build_campaign(self, *, name: str, role_title: str, hiring_manager: dict) -> tuple[str, list[dict]]:
        """Create+screen a campaign if it doesn't already exist. Returns
        (campaign_id, evaluations sorted best-first)."""
        existing = self.find_campaign(name)
        if existing is not None:
            self.log(f"Campaign already seeded: {name} ({existing['id']})")
            evaluations = [] if self.dry_run else self.get(f"/api/campaigns/{existing['id']}/evaluations")
            return existing["id"], evaluations

        jd_text = read_docx_text(JDS[role_title]["file"])
        self.log(f"Creating campaign: {name}")
        created = self.post("/api/campaigns", json={
            "name": name,
            "job_title": role_title,
            "job_description": jd_text,
            "vacancies": JDS[role_title].get("vacancies", 1),
            "location": "Mesaieed Industrial City, Qatar",
            "business_unit": "QChem Demo",
            "recruiter": self.people["recruiter"]["full_name"],
            "hiring_manager": hiring_manager["full_name"],
            "target_completion_date": (date.today() + timedelta(days=45)).isoformat(),
        })
        if self.dry_run:
            return "dry-run-campaign", []
        campaign_id = created["id"]

        self.log(f"Extracting requirements for {campaign_id}")
        self.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
        self.post(f"/api/campaigns/{campaign_id}/rubric/versions", json={"seed_from_requirements": True})
        self.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
        self.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                  json={"approved_by": self.people["recruiter"]["full_name"]})

        files = []
        for filename in JDS[role_title]["cvs"]:
            path = CV_DIR / filename
            files.append(("files", (filename, path.read_bytes(), _ext_mime(path))))
        self.log(f"Uploading {len(files)} CVs for {role_title}")
        response = self.client.post(f"/api/campaigns/{campaign_id}/batches", files=files)
        assert response.status_code == 201, response.text

        self.log("Running evaluation (real LLM call — this takes a while)")
        self.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={
            "scoring_mode": "LLM_ASSISTED",
            "demo_delay_seconds": 0.5,
            "notes": "Demo screening: deterministic evidence plus bounded LLM review.",
        })

        evaluations = self.get(f"/api/campaigns/{campaign_id}/evaluations")
        for e in evaluations:
            self.log(f"  scored: {e['candidate_name']} — {e['overall_score']}")
        return campaign_id, evaluations

    # -- lifecycle progression ----------------------------------------------

    def shortlist_and_enter(self, campaign_id: str, candidate_id: str, candidate_name: str) -> None:
        self.log(f"Shortlisting {candidate_name}")
        self.post(f"/api/campaigns/{campaign_id}/candidates/{candidate_id}/disposition",
                  json={"disposition": "SHORTLIST", "actor": self.people["recruiter"]["full_name"]})
        self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/enter?actor_id={self.people['recruiter']['id']}")

    def progress_campaign_a(self, campaign_id: str, evaluations: list[dict]) -> None:
        if not evaluations:
            return
        top = evaluations[0]
        candidate_id, candidate_name = top["candidate_id"], top["candidate_name"]
        # Idempotency: if this candidate already has a lifecycle position past
        # SHORTLISTED, do not repeat the transitions (a rerun would 422/duplicate).
        status = self.lifecycle_status_or_none(campaign_id, candidate_id)
        if status is not None:
            self.log(f"Campaign A candidate already progressed: {candidate_name} ({status})")
            return
        self.shortlist_and_enter(campaign_id, candidate_id, candidate_name)
        manager = self.people["manager_a"]
        self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
                  json={"actor_id": self.people["recruiter"]["id"], "manager_id": manager["id"]})
        self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
                  json={"reviewer_id": manager["id"], "outcome": "PROCEED"})
        self.post(f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/schedule", json={
            "actor_id": manager["id"],
            "when": (date.today() + timedelta(days=6)).isoformat() + "T10:00:00",
            "duration_minutes": 45, "mode": "VIDEO", "round": 1, "panel": [manager["id"]],
        })
        self.log(f"Campaign A left at: interview scheduled, awaiting feedback ({candidate_name})")

    def seed_campaign_a_backup(self, campaign_id: str, evaluations: list[dict]) -> None:
        """Stagger the other two scored candidates so handoff.html has a
        real queue, not just the one candidate parked past manager review.
        Priya Menon stops at WITH_HIRING_MANAGER; Carlos Mendes is recorded
        as not proceeding and never enters the lifecycle."""
        by_name = {e["candidate_name"]: e for e in evaluations}
        manager = self.people["manager_a"]

        priya = by_name.get("Priya Menon")
        if priya is not None:
            status = self.lifecycle_status_or_none(campaign_id, priya["candidate_id"])
            if status is not None:
                self.log(f"Priya Menon already progressed ({status})")
            else:
                self.log("Shortlisting Priya Menon, holding with the hiring manager")
                self.shortlist_and_enter(campaign_id, priya["candidate_id"], "Priya Menon")
                self.post(f"/api/campaigns/{campaign_id}/lifecycle/{priya['candidate_id']}/send-to-manager",
                          json={"actor_id": self.people["recruiter"]["id"], "manager_id": manager["id"]})

        carlos = by_name.get("Carlos Mendes")
        if carlos is not None:
            actions = self.get(f"/api/campaigns/{campaign_id}/candidates/{carlos['candidate_id']}/actions")
            if any(a.get("disposition") for a in actions):
                self.log("Carlos Mendes already dispositioned")
            else:
                self.log("Recording Carlos Mendes as not proceeding")
                self.post(f"/api/campaigns/{campaign_id}/candidates/{carlos['candidate_id']}/disposition",
                          json={"disposition": "REJECT", "actor": self.people["recruiter"]["full_name"]})

    def progress_campaign_b(self, campaign_id: str, evaluations: list[dict]) -> None:
        if not evaluations:
            return
        top = evaluations[0]
        candidate_id, candidate_name = top["candidate_id"], top["candidate_name"]
        status = self.lifecycle_status_or_none(campaign_id, candidate_id)
        if status is not None:
            self.log(f"Campaign B candidate already progressed: {candidate_name} ({status})")
            return
        self.shortlist_and_enter(campaign_id, candidate_id, candidate_name)
        manager = self.people["manager_b"]
        admin = self.people["admin"]
        self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
                  json={"actor_id": self.people["recruiter"]["id"], "manager_id": manager["id"]})
        self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
                  json={"reviewer_id": manager["id"], "outcome": "PROCEED"})
        self.post(f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/schedule", json={
            "actor_id": manager["id"],
            "when": (date.today() - timedelta(days=2)).isoformat() + "T10:00:00",
            "duration_minutes": 45, "mode": "VIDEO", "round": 1, "panel": [manager["id"]],
        })
        self.post(f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/feedback", json={
            "actor_id": manager["id"], "recommendation": "PROCEED",
            "strengths": "Strong HAZOP/MOC and Aspen HYSYS simulation record; clear communicator in the panel round.",
        })
        self.post(f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request", json={
            "actor_id": self.people["recruiter"]["id"], "chain": [manager["id"], admin["id"]],
            "grade": COST_CENTRE["role_grade"], "salary_band": "QAR 180,000 - 220,000",
            "justification": "Panel unanimously recommends hire; strongest candidate against the approved band.",
        })
        self.post(f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre", json={
            "actor_id": manager["id"], "budget_holder_id": admin["id"],
            "cost_centre_code": COST_CENTRE["code"],
        })
        self.post(f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/grant",
                  json={"actor_id": admin["id"], "note": "Within the approved FY2026 envelope."})
        self.post(f"/api/campaigns/{campaign_id}/offers/{candidate_id}/draft", json={
            "actor_id": self.people["recruiter"]["id"], "base_salary": 200000, "currency": "QAR",
            "grade": COST_CENTRE["role_grade"],
            "start_date": (date.today() + timedelta(days=30)).isoformat(),
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
            "notes": "Standard QChem expatriate package; relocation handled separately.",
        })
        self.post(f"/api/campaigns/{campaign_id}/offers/{candidate_id}/send",
                  json={"actor_id": self.people["recruiter"]["id"]})
        self.log(f"Campaign B left at: offer recorded as sent, awaiting response ({candidate_name})")

    def seed_campaign_b_backup(self, campaign_id: str, evaluations: list[dict]) -> None:
        """Stagger the other two scored candidates so approvals.html has a
        real candidate awaiting HR/budget sign-off, with the cost-centre
        envelope attached. Youssef Al-Attiyah stops at PENDING_COST_CENTRE
        (request + cost-centre, no grant); Daniel Cruz is recorded as not
        proceeding and never enters the lifecycle."""
        by_name = {e["candidate_name"]: e for e in evaluations}
        manager = self.people["manager_b"]
        admin = self.people["admin"]

        youssef = by_name.get("Youssef Al-Attiyah")
        if youssef is not None:
            candidate_id = youssef["candidate_id"]
            status = self.lifecycle_status_or_none(campaign_id, candidate_id)
            if status is not None:
                self.log(f"Youssef Al-Attiyah already progressed ({status})")
            else:
                self.log("Progressing Youssef Al-Attiyah to pending cost-centre approval")
                self.shortlist_and_enter(campaign_id, candidate_id, "Youssef Al-Attiyah")
                self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/send-to-manager",
                          json={"actor_id": self.people["recruiter"]["id"], "manager_id": manager["id"]})
                self.post(f"/api/campaigns/{campaign_id}/lifecycle/{candidate_id}/review",
                          json={"reviewer_id": manager["id"], "outcome": "PROCEED"})
                self.post(f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/schedule", json={
                    "actor_id": manager["id"],
                    "when": (date.today() - timedelta(days=1)).isoformat() + "T14:00:00",
                    "duration_minutes": 45, "mode": "VIDEO", "round": 1, "panel": [manager["id"]],
                })
                self.post(f"/api/campaigns/{campaign_id}/interviews/{candidate_id}/feedback", json={
                    "actor_id": manager["id"], "recommendation": "PROCEED",
                    "strengths": "Solid process-safety fundamentals; second-strongest panel score.",
                })
                self.post(f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/request", json={
                    "actor_id": self.people["recruiter"]["id"], "chain": [manager["id"], admin["id"]],
                    "grade": COST_CENTRE["role_grade"], "salary_band": "QAR 180,000 - 220,000",
                    "justification": "Panel recommends hire as a second Process Engineer headcount.",
                })
                self.post(f"/api/campaigns/{campaign_id}/approvals/{candidate_id}/cost-centre", json={
                    "actor_id": manager["id"], "budget_holder_id": admin["id"],
                    "cost_centre_code": COST_CENTRE["code"],
                })
                self.log("Youssef Al-Attiyah left at: pending cost-centre / budget approval")

        daniel = by_name.get("Daniel Cruz")
        if daniel is not None:
            actions = self.get(f"/api/campaigns/{campaign_id}/candidates/{daniel['candidate_id']}/actions")
            if any(a.get("disposition") for a in actions):
                self.log("Daniel Cruz already dispositioned")
            else:
                self.log("Recording Daniel Cruz as not proceeding")
                self.post(f"/api/campaigns/{campaign_id}/candidates/{daniel['candidate_id']}/disposition",
                          json={"disposition": "REJECT", "actor": self.people["recruiter"]["full_name"]})

    # -- communication log ---------------------------------------------------

    def candidate_thread(self, campaign_id: str, candidate_id: str) -> list[dict]:
        if self.dry_run:
            return []
        return self.get(f"/api/campaigns/{campaign_id}/messages/{candidate_id}")

    def has_message(self, thread: list[dict], *, template_id: str | None = None,
                     recipient: str | None = None) -> bool:
        return any(
            (template_id is None or m.get("template_id") == template_id)
            and (recipient is None or m.get("recipient") == recipient)
            for m in thread
        )

    def send_message(self, campaign_id: str, candidate_id: str, *, channel: str,
                      recipient: str, subject: str, body: str, actor_id: str,
                      template_id: str | None = None) -> None:
        self.post(f"/api/campaigns/{campaign_id}/messages/{candidate_id}/send", json={
            "channel": channel, "recipient": recipient, "subject": subject,
            "body": body, "actor_id": actor_id, "template_id": template_id,
        })

    def seed_campaign_a_messages(self, campaign_id: str, evaluations: list[dict]) -> None:
        if not evaluations:
            return
        top = evaluations[0]
        candidate_id, candidate_name = top["candidate_id"], top["candidate_name"]
        recruiter, manager = self.people["recruiter"], self.people["manager_a"]
        thread = self.candidate_thread(campaign_id, candidate_id)

        if self.has_message(thread, recipient=manager["email"]):
            self.log(f"Shortlist handover already on file: {candidate_name} -> {manager['full_name']}")
        else:
            self.log(f"Recording shortlist handover: {candidate_name} -> {manager['full_name']}")
            self.send_message(
                campaign_id, candidate_id, channel="EMAIL", recipient=manager["email"],
                subject=f"Shortlist report — Maintenance Engineer — {candidate_name}",
                body=(
                    f"Dear {manager['full_name']},\n\n"
                    f"{candidate_name} has been shortlisted for Maintenance Engineer on "
                    "QChem Demo — Campaign A. The shortlist report is attached for your "
                    "review.\n\nRegards,\n" + recruiter["full_name"]
                ),
                actor_id=recruiter["full_name"],
            )

        if self.has_message(thread, template_id="INTERVIEW_INVITE"):
            self.log(f"Interview invite already on file: {candidate_name}")
        else:
            self.log(f"Recording interview invite: {candidate_name}")
            candidate_email = synthetic_candidate_email(candidate_name)
            self.send_message(
                campaign_id, candidate_id, channel="EMAIL", recipient=candidate_email,
                subject="Interview for Maintenance Engineer — 20 Sep 2026, 10:00",
                body=(
                    f"Dear {candidate_name},\n\n"
                    "We would like to invite you to interview for Maintenance Engineer "
                    "at QChem Demo — Campaign A on 20 September 2026 at 10:00 (video "
                    "call). Please confirm you can attend.\n\nThank you."
                ),
                actor_id=recruiter["full_name"], template_id="INTERVIEW_INVITE",
            )

    def seed_campaign_b_messages(self, campaign_id: str, evaluations: list[dict]) -> None:
        if not evaluations:
            return
        top = evaluations[0]
        candidate_id, candidate_name = top["candidate_id"], top["candidate_name"]
        recruiter, manager = self.people["recruiter"], self.people["manager_b"]
        thread = self.candidate_thread(campaign_id, candidate_id)

        if self.has_message(thread, recipient=manager["email"]):
            self.log(f"Shortlist handover already on file: {candidate_name} -> {manager['full_name']}")
        else:
            self.log(f"Recording shortlist handover: {candidate_name} -> {manager['full_name']}")
            self.send_message(
                campaign_id, candidate_id, channel="EMAIL", recipient=manager["email"],
                subject=f"Shortlist report — Process Engineer — {candidate_name}",
                body=(
                    f"Dear {manager['full_name']},\n\n"
                    f"{candidate_name} has been shortlisted for Process Engineer on "
                    "QChem Demo — Campaign B. The shortlist report is attached for your "
                    "review.\n\nRegards,\n" + recruiter["full_name"]
                ),
                actor_id=recruiter["full_name"],
            )

        if self.has_message(thread, template_id="OFFER_COVER"):
            self.log(f"Offer message already on file: {candidate_name}")
        else:
            self.log(f"Recording offer message: {candidate_name}")
            candidate_email = synthetic_candidate_email(candidate_name)
            self.send_message(
                campaign_id, candidate_id, channel="EMAIL", recipient=candidate_email,
                subject="Offer for Process Engineer",
                body=(
                    f"Dear {candidate_name},\n\n"
                    "We are pleased to offer you Process Engineer at QChem Demo — "
                    "Campaign B, base salary QAR 200,000. This offer expires on "
                    "24 September 2026. Details of the offer are attached.\n\n"
                    "Congratulations."
                ),
                actor_id=recruiter["full_name"], template_id="OFFER_COVER",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the plan, make no mutating calls.")
    args = parser.parse_args()

    missing = []
    for role, spec in JDS.items():
        if not spec["file"].exists():
            missing.append(str(spec["file"]))
        for cv in spec["cvs"]:
            if not (CV_DIR / cv).exists():
                missing.append(str(CV_DIR / cv))
    if missing:
        print("Cannot seed: the JD/CV fixture documents were not found.", file=sys.stderr)
        print(f"  Looked for the JDs in: {JD_DIR}", file=sys.stderr)
        print(f"  Looked for the CVs in: {CV_DIR}", file=sys.stderr)
        print("These folders are shared separately and are not in the git repo.", file=sys.stderr)
        print("Set JD_REPOSITORY_DIR and CV_REPOSITORY_DIR to where you unpacked them,", file=sys.stderr)
        print("then run this script again. Missing files:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        seeder = Seeder(client, dry_run=args.dry_run)
        seeder.log("=== JD library ===")
        seeder.seed_jd_library()
        seeder.log("=== People ===")
        seeder.seed_people()
        seeder.log("=== Cost centre (Campaign B's BU envelope) ===")
        seeder.seed_cost_centre()

        seeder.log("=== Campaign A: Maintenance Engineer ===")
        campaign_a_id, evals_a = seeder.build_campaign(
            name=CAMPAIGN_A_NAME, role_title="Maintenance Engineer",
            hiring_manager=seeder.people.get("manager_a", {"full_name": "Yusuf Al-Marri"}),
        )
        seeder.progress_campaign_a(campaign_a_id, evals_a)
        seeder.seed_campaign_a_messages(campaign_a_id, evals_a)
        seeder.seed_campaign_a_backup(campaign_a_id, evals_a)

        seeder.log("=== Campaign B: Process Engineer ===")
        campaign_b_id, evals_b = seeder.build_campaign(
            name=CAMPAIGN_B_NAME, role_title="Process Engineer",
            hiring_manager=seeder.people.get("manager_b", {"full_name": "Noora Al-Thani"}),
        )
        seeder.progress_campaign_b(campaign_b_id, evals_b)
        seeder.seed_campaign_b_messages(campaign_b_id, evals_b)
        seeder.seed_campaign_b_backup(campaign_b_id, evals_b)

        seeder.log(f"Campaign A id: {campaign_a_id}")
        seeder.log(f"Campaign B id: {campaign_b_id}")


if __name__ == "__main__":
    main()
