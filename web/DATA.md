# Shared facts — every screen must agree with this

This is the single source of truth for the instance. If a number appears on two
screens it must be identical. Do not invent figures that contradict this file.

## Organisation

- Client: **Recruitment 360** (Talent Acquisition). Petrochemical. Makes polyethylene,
  normal alpha olefins, 1-hexene, sulphur.
- Sites: **North Plant** (main plant), **Coastal Terminal**, **Head Office** (head office, Amwal Tower).
- Their ATS is **SAP SuccessFactors Recruiting**. Never call it "a mock" or "generic".
- Currency **USD**. Loaded recruiter rate **$42.00/hour** — always shown as configurable.
- Signed-in user: whoever authenticated this session (real login via `/api/auth/me`),
  not a fixed name. Historical rubric approvals recorded under Fatima Al-Rashid (below)
  describe a past event and stay as recorded.
- Today is **Thursday 10 September 2026**. Reporting period **1–30 September**.
- Approved rubric version **4.2**, approved by F. Al-Rashid on **2 September**.

## Period totals (must match on Today and Performance)

| Figure | Value | How it is derived |
|---|---|---|
| Applications assessed | 3,420 | |
| Recruiter hours returned | 393 | 3,420 × 6.9 min saved ÷ 60 |
| Manual equivalent | 456 hours | 3,420 × 8.0 min |
| Actual recruiter time | 63 hours | 3,420 × 1.1 min |
| Screening time not spent | $16,506 | 393 × $42.00 |
| Annualised at this volume | $198,000 | |
| Days to a shortlist | 4.2 | baseline 11.0 last year, −62% |
| Processed without a problem | 99.1% | 3,389 of 3,420 |
| Evidence coverage | 100% | every scored criterion cites a CV line |
| High scores the checker could not justify | 0.3% | limit is 1% |
| Assessments the team overruled | 6.4% | 219 of 3,420 |
| Files held, could not be read | 31 | |

## Campaigns (six open)

| Ref | Role | Site | Vac | State | Progress | Shortlist | Median |
|---|---|---|---|---|---|---|---|
| CAM-2611 | Control Room Operator | Coastal Terminal | 8 | Awaiting decision | 604 of 622 | 24 | 58.9 |
| CAM-2599 | HSE Advisor | Head Office | 2 | Awaiting decision | 188 of 188 | 9 | 66.7 |
| CAM-2618 | Rotating Equipment Engineer | North Plant | 3 | Running | 268 of 412 | — | 61.4 |
| CAM-2604 | Instrumentation Technician | North Plant | 12 | Running | 389 of 941 | — | 54.2 |
| CAM-2588 | Turnaround Planner | North Plant | 4 | Handed over to SuccessFactors | 311 of 311 | 11 | 60.1 |
| CAM-2575 | Process Engineer | North Plant | 5 | Closed | 268 of 268 | 7 | 63.5 |

Closing dates: 2611 → 19 Sep, 2599 → 17 Sep, 2618 → 24 Sep, 2604 → 30 Sep.
Live run detail for CAM-2618: 6 of 8 workers, queue depth 107, mean assessment 8.7 s,
412 CV/hour sustained, estimated finish today 11:47, last checkpoint 09:41:22.

## Held files (31 total)

| Count | Plain-English reason | Action offered |
|---|---|---|
| 12 | Photographs of a CV, with no text to read | Send for scanning |
| 9 | The same person applied twice | Merge them |
| 6 | The file is password protected | Ask for it again |
| 4 | No employment dates anywhere in the CV | Read by hand |

## The rubric for Control Room Operator (CAM-2611), version 4.2

Mandatory (must be met, otherwise not eligible):
- REQ-01 Right to work, or transferable sponsorship
- REQ-02 Diploma or higher in a process, chemical or mechanical discipline
- REQ-03 Console hours on a live continuous-process unit — minimum 3 years
- REQ-04 Trained on a distributed control system (DCS)
- REQ-05 Fitness-to-work and offshore/onshore medical clearance

Preferred (adds to the score, never disqualifies):
- REQ-06 Ethylene, polyethylene or olefins experience — weight 20
- REQ-07 Wrote or owned an operating procedure — weight 12
- REQ-08 Turnaround or shutdown participation — weight 10
- REQ-09 Permit-to-work authority — weight 8
- REQ-10 Arabic and English — weight 6

Eligibility conditions, approved and recorded separately from scoring:
- **National workforce preference** — Nationals of the host country are advanced to review automatically.
  Recorded as an approved eligibility rule, with the approver and date visible.
  It is never a hidden weight.
- Protected characteristics are excluded from scoring entirely.

Weights: Mandatory 45, Skills 20, Experience 18, Qualifications 10, Certifications 7.

## The Control Room Operator shortlist (24 people). Top of the list:

| Rank | Name | Score | Verdict | Mandatory | Confidence |
|---|---|---|---|---|---|
| 1 | Haitham Al-Otaibi | 91 | Strong fit | 5 of 5 | High |
| 2 | Reem Al-Suwaidi | 84 | Strong fit | 5 of 5 | High |
| 3 | Yousef Al-Marri | 79 | Strong fit | 5 of 5 | High |
| 4 | Ahmed Karim | 76 | Potential fit | 5 of 5 | Medium |
| 5 | Priya Raghunathan | 74 | Potential fit | 5 of 5 | High |
| 6 | Bilal Haque | 72 | Review required | 4 of 5 | Low |
| 7 | Omar Al-Kuwari | 71 | Potential fit | 5 of 5 | Medium |
| 8 | Daniel Okonkwo | 68 | Potential fit | 5 of 5 | Medium |
| 9 | Sara Al-Hajri | 66 | Potential fit | 5 of 5 | High |
| 10 | Ravi Menon | 61 | Review required | 4 of 5 | Low |

Verdict spread across all 622: Strong 8%, Potential 22%, Review 30%, Not recommended 40%.

## Evidence quotes — reuse these exactly, they are the product's whole argument

- **Haitham Al-Otaibi**, REQ-03 mandatory, confirmed:
  "Held a **DCS console licence** on a live ethylene unit for **seven years**, including two full turnarounds."
  Source: CV page 2, Experience.
- **Haitham Al-Otaibi**, REQ-09 preferred, confirmed:
  "Named **permit-to-work authority** for the olefins area."  Source: CV page 2, Responsibilities.
- **Reem Al-Suwaidi**, REQ-07 preferred, confirmed:
  "Ran **shift handover** for a four-crew rotation and wrote the unit's **emergency depressurisation procedure**."
  Source: CV page 1, Summary.
- **Bilal Haque**, REQ-03 mandatory, insufficient evidence — raised by the checking agent:
  "Nine years in operations, but the CV never says whether the role was **console** or **field**."
  Suggested question for the recruiter: "How many hours did you spend on the console, and on which unit?"
- **Ahmed Karim**, REQ-06 preferred, adjacent match not a direct one:
  "Ran an **ammonia** plant, not olefins. The control philosophy is close but the process is not."

## Language rules

- Write for someone who does not work in software. "Photographs of a CV, with no text
  to read", never "OCR failure" or "E-204".
- Never use the words demo, sample, mock, test, placeholder, or Lorem in anything visible.
- Never show a percentage without its denominator.
- Never show a saving without the baseline it is measured against.
- AI never decides. It recommends, a person decides. Say so on any screen with a decision.
