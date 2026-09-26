# Demo guide — Campaign C, end to end

**Written 2026-09-14, from a complete run on this machine.** Every step below was
actually performed, not imagined. Where something behaved badly, it says so.

This guide covers the full journey: uploading the third job description, screening
three CVs, deciding, messaging candidates, arranging interviews, approving the hire,
sending the offer, and recording the answer. Real emails and real calendar invites
are sent along the way.

Read [DEMO-RUNBOOK-2026-09-14.md](DEMO-RUNBOOK-2026-09-14.md) first for the wider
session plan. This file is the click-by-click detail for the live segment.

---

## 0. Before you start

Two terminals.

Terminal 1 — the API:

```bash
$env:QUEUE_BACKEND = "inline"; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Terminal 2 — the web pages:

```bash
cd web ; python -m http.server 8124
```

`QUEUE_BACKEND` must be set as a shell variable in the same terminal that starts
`uvicorn`. Put it in `.env` and it will not work: uploads sit on `QUEUED` for ever
and every screen looks empty.

Then, in the browser you will present from:

1. Open `http://127.0.0.1:8124/login.html` and sign in.
2. Press **Ctrl+Shift+R** at least once. A normal reload can serve stale JavaScript,
   which makes fixes look broken. This happened repeatedly while building this guide.
3. Check the send mode is real: open `http://127.0.0.1:8000/api/config/send-modes`.
   It must say `{"email_backend":"outlook","calendar_backend":"outlook"}`.

**Outlook must be open and signed in on this machine.** The app sends as whichever
account is signed in. If Outlook is closed, sends fail with a clear 422 rather than
silently going out as the wrong person.

---

## 1. Who the emails actually go to

No email ever goes to a candidate's own address. The candidates are synthetic; their
CVs carry addresses like `hana.alemadi@example.com`, which do not exist.

Five addresses are approved. Everything else is rejected before the mail adapter is
reached:

| Person | Address | Plays |
|---|---|---|
| Subhadeep | `subhadeep.m@protivitiglobal.in` | Hiring manager, report recipient |
| Ankush | `ankush.saxena@protivitiglobal.in` | Co-manager, CC on the report |
| Daipayan | `daipayan.r@protivitiglobal.in` | Proxy for **Hana Al-Emadi** |
| Chiranjib | `chiranjib.sarma@protivitiglobal.in` | Proxy for **Suresh Nair** |
| Preetam | `preetam.c@protivitiglobal.me` | Proxy for **James O'Brien** |

Preetam's address really does end `.me`, not `.in`. That is correct, not a typo.

---

## 2. The journey

### Step 1 — Pick the job description (2 min)

Open **Start Campaign**, then **Browse the JD library**. Four saved descriptions
appear. Click **Use for a new campaign** on **Process Operator**.

Say out loud: the library is a real saved-JD store, not a mock. It is deliberately
simple — no versioning, no approval workflow on the description itself.

### Step 2 — Describe the role (2 min)

The role title, site and full job description are already filled in from the library.
Fill in the rest:

| Field | Value used |
|---|---|
| Hiring manager | Subhadeep |
| Business unit | Operations |
| Recruiter | Subhadeep |
| Closing date | 2026-09-30 |
| Vacancies | 1 |
| Site | Coastal Terminal |

Click **Read the description**.

This makes a real call to Azure OpenAI. It takes about five seconds and produced
**34 requirements** — genuine content from the description, including DCS/SCADA
control systems, permit-to-work compliance, and equipment isolation. A rubric is
created at version 1 with the weights totalling 100.

### Step 3 — Upload the CVs and start screening (3 min)

Scroll to **Applications to assess** and click **Choose applications**. Select all
three Process Operator CVs:

- `Resume_ProcessOperator_HanaAlEmadi.pptx` — a PowerPoint, not a Word file
- `Resume_ProcessOperator_JamesOBrien_PoorFormat_HeaderInfo.docx` — badly formatted
- `Resume_ProcessOperator_SureshNair_ScannedPDF.pdf` — a scanned image, no text layer

Click **Approve and start screening**.

This is the strongest moment in the demo. Three very different files, all read:

| CV | Name extracted | Note |
|---|---|---|
| Hana Al-Emadi | Clean | A PowerPoint CV, parsed correctly |
| James O'Brien | **Blank** | Flagged `requires review`, shown not hidden |
| Suresh Nair | `SURESH NAIR` | **OCR genuinely read the scanned image** |

The blank name is the point worth making, not the thing to apologise for. The system
screened the CV, scored it, and flagged that a human should check the identity. It did
not silently drop the application.

### Step 4 — The shortlist (3 min)

Open **Candidate shortlist**. Real scores from this run:

| Rank | Candidate | Score | Confidence |
|---|---|---|---|
| 1 | Hana Al-Emadi | 64 / 100 | Low (43%) |
| 2 | SURESH NAIR | 53 / 100 | Low (31%) |
| 3 | Unknown | 40 / 100 | Low (35%) |

**Wait for the page to finish loading before you talk about it.** For about a second
the collapsed shortlist header shows a placeholder count of "24" before the real "3"
arrives. If you start narrating too early, a client sees a number that is not true.

Low confidence across the board is honest: these are short synthetic CVs with thin
evidence. Say so. It is better than pretending to certainty.

### Step 5 — Decide (2 min)

Open **Decisions and export**. Each row has Shortlist / Hold / Reject.

- Hana Al-Emadi → **Shortlist**
- SURESH NAIR → **Shortlist**
- Unknown → **Hold**

Holding the unnamed candidate is the honest action. They were not rejected for a
parsing failure; they are held for a human to read the CV and confirm the identity.

The header updates to "3 of 3 decided · 2 shortlisted".

### Step 6 — Email the shortlist to the hiring manager (2 min)

Still on the Decisions page, open **Send the report to the hiring manager**.

- Hiring manager's email: `subhadeep.m@protivitiglobal.in`
- CC: `ankush.saxena@protivitiglobal.in`

Click **Email the shortlist**. The status line reads "Sent via local Outlook to
subhadeep.m@protivitiglobal.in."

**This is a real email.** Check the inbox live if you want to prove it.

This is the only screen that offers a CC field.

### Step 7 — Message the candidates (4 min)

Open **Communication record** → **Record a message**. The badge reads
**SENDS FOR REAL — OUTLOOK LIVE**, and the button says "Send message", not "Record
message". The badge is read from the server, so it cannot lie about the send mode.

**Do the rejection first — it is the best moment on this screen.**

1. Acting person **Subhadeep**, candidate **Hana Al-Emadi**, template
   **Shortlist invite**.
2. Leave the recipient as the address the system pulled off the CV
   (`hana.alemadi@example.com`) and press Send.
3. It is refused: *"'hana.alemadi@example.com' is not an approved recipient for a
   real Outlook send."*

Say plainly: the system will not email an address just because it appeared in a
document. That is the guard you want in front of a tool that can send mail on your
behalf.

Now pick the proxy from the dropdown and send for real:

| Candidate | Template | Send to |
|---|---|---|
| Hana Al-Emadi | Shortlist invite | `daipayan.r@protivitiglobal.in` |
| SURESH NAIR | Shortlist invite | `chiranjib.sarma@protivitiglobal.in` |
| Unknown | Document chase | `preetam.c@protivitiglobal.me` |

For the **Document chase** on the unnamed candidate, a **Candidate name** box
appears, because the system has no name to use. Type `James O'Brien` — read from the
CV the way a recruiter would. This is the flagged-for-review workflow paying off: a
human supplies what the parser could not.

All three arrive as real email. There is **no CC field** on this screen, so Ankush is
not copied on candidate messages — only on the shortlist report in Step 6.

### Step 8 — Hand over to the hiring manager (2 min)

Open **Manager review**.

**Choose the acting person before you touch a candidate row.** The screen reads the
acting person when the row opens. Change it afterwards and it still uses the old one,
and you get a confusing "Your role does not allow you to..." message that is really
about the wrong person being selected.

- Acting person: **Layla Haddad (Recruiter)** — only a recruiter may hand a candidate
  to a manager.
- Click **Send to hiring manager** on each candidate, choose **Subhadeep**, Confirm.

The badge here says **SIMULATED — INTEGRATION PENDING**, and the panel explains that
a real system would email the manager. That is accurate: this specific step sends no
mail. Do not let it be confused with the real sends in Steps 6 and 7 — say "the
handover notification is not wired to Outlook; the candidate emails you just watched
are."

Then switch the acting person to **Subhadeep (Hiring manager)** and click **Record
verdict** → **Proceed to interview** for Hana Al-Emadi.

### Step 9 — Arrange the interviews (4 min)

Open **Interviews and feedback** and choose the campaign. Click a candidate in
**Waiting to be scheduled**.

The invite only ever goes to the two people you select — the co-hiring manager and
the interview recipient. The candidate's CV address is never used.

Two interviews were arranged, so that all four colleagues receive one:

| Candidate | When (IST) | Co-hiring manager | Recipient |
|---|---|---|---|
| Hana Al-Emadi | 2026-09-15, 11:00, 45 min, Video | Daipayan | Chiranjib |
| SURESH NAIR | 2026-09-15, 14:00, 45 min, Video | Ankush | Preetam |

Set **Arranged by** to **Subhadeep**. It must be the signed-in Outlook account —
the audit trail has to name the person whose mailbox actually sent it. A seeded
fictional manager is refused.

Click **Schedule interview**. The page confirms: *"Outlook invite sent to the selected
co-hiring manager and interview recipient."* Both were verified as genuinely sent.

Then record feedback for Hana: recommendation **Proceed**, acting person
**Subhadeep**, scores 4 / 4 / 5, with a note.

### Step 10 — Approve the hire (3 min)

Open **HR and budget approvals**, choose Hana Al-Emadi.

1. Acting person **Subhadeep**. First approver **Imran Qureshi**. Grade
   `Operator, Grade 3`. Salary band `QAR 12,000 - 15,000 per month (illustrative)`.
   Add a justification. Click **Request approval**.
2. Switch acting person to **Imran Qureshi**. Record the cost centre
   `CC-QCHEM-PE — Technical Services (QAR)` with Imran as budget holder.
3. Click **Grant approval**.

The status becomes **Approved**. The badge notes approvers are not emailed from this
screen — true, and worth saying.

All budget figures are illustrative and labelled as such on screen. They show the
shape of a business-unit pre-approval, not a live ERP feed.

### Step 11 — Offer and answer (4 min)

Open **Offers and responses**, choose Hana Al-Emadi.

**Acting person must be a recruiter** (Layla Haddad). A hiring manager cannot draft
an offer, and the refusal message will not make that obvious.

Draft it:

| Field | Value used |
|---|---|
| Base salary | 13,500 |
| Currency | QAR |
| Grade | Operator, Grade 3 |
| Start date | 2026-10-12 |
| Expiry date | 2026-09-28 |

Then open **Record offer as sent**. The note says "A real letter email is sent to the
candidate." Set **Send to** to `daipayan.r@protivitiglobal.in` and click **Record
send**.

**This is a real email**, confirmed sent through local Outlook.

Finally record the answer: **Accepted**. The candidate reaches **Offer accepted** and
the journey is complete.

---

## 3. What to say if asked "is any of this faked?"

- **Screening, scoring and the rubric** are real. Azure OpenAI is called live.
- **OCR on the scanned PDF** is real. No manual fallback.
- **Emails and calendar invites** are real, sent through the local Outlook profile,
  restricted to five approved colleagues.
- **Candidates are synthetic** and their addresses do not exist. That is why proxies
  are used.
- **Budget and cost-centre figures are illustrative.** Labelled on screen.
- **The handover notification to a hiring manager is not wired to email.** The screen
  says so itself.
- Never say a message was *received*. The product says "recorded as sent", which is
  accurate. Keep that phrasing.

---

## 4. Things that will bite you

| Problem | What to do |
|---|---|
| Uploads stay on `QUEUED` | `QUEUE_BACKEND=inline` was not set in the API terminal. Restart it. |
| A fix looks missing | Hard reload, Ctrl+Shift+R. Stale JavaScript is the single most common cause. |
| "Your role does not allow you to…" | Wrong acting person. Recruiter hands over and drafts offers; hiring manager reviews and requests approval; the approver grants. |
| Acting person change ignored | Set it **before** opening a candidate row, or reload. |
| Shortlist header briefly shows "24" | A placeholder. Wait for the page to settle before narrating. |
| Sends refused with 422 | The recipient is not one of the five approved addresses. Use the dropdown. |
| Nothing sends at all | Outlook is not open or not signed in on this machine. |

---

## 5. A limitation worth knowing before you are asked

A campaign built live in the browser **cannot reach the Review and Hire stages by
clicking alone**. Moving a shortlisted candidate into the hiring process
(`lifecycle/enter`) has no button anywhere in the interface; only the seeding script
calls it. For this run it was triggered directly against the API.

If you build a fresh campaign live in front of a client, plan to stop at
**Decisions**, then switch to a pre-seeded campaign for interviews, approvals and
offers. Do not promise a single unbroken click-through on a brand new campaign until
that gap is closed.

---

## 6. Reference — the campaign this guide was built from

- Campaign id `dc7c2909-f403-4c9f-9d2b-83cfb9994ed5`, Process Operator, Coastal
  Terminal, 1 vacancy.
- Candidates: Hana Al-Emadi `a241bbf9`, SURESH NAIR `4a93de92`, Unknown `28d8c095`.
- 34 requirements, rubric version 1, weights totalling 100.
- Four real emails and two real calendar invites were sent during the run described
  here. If you rehearse the whole thing again, those colleagues get another set.
