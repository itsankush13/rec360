# Recruitment 360 wide-pass UI contract (`B01`, `B19`)

| Input | Type | Required | Default |
|---|---|---|---|
| Campaign | existing campaign ID | Yes for data/actions | none selected |
| Acting person | active user ID | Yes for writes | none selected |
| Candidate | candidate ID in selected campaign | Yes for writes | none selected |
| Lifecycle, audit, metrics | API responses | Yes after campaign choice | empty while loading |

| State | Surface | Available action |
|---|---|---|
| Loading | “Loading current campaign…” | Change campaign |
| Empty | “No candidates in the hiring journey yet” or equivalent | Go to import/shortlist |
| Error | “Could not load campaign” with server reason | Change campaign or retry by refresh |
| Populated | One headline and a stage chart; raw rows collapsed | Open details or choose a candidate |
| Saving | “Saving the decision…” | Wait for result |
| Saved | “Saved to the candidate record.” | Continue to next valid step |

Selecting campaign reads current state. Opening details reveals raw counts, owners and
timing. Selecting candidate reveals only actions allowed by that screen's stage. Submitting
an action writes real lifecycle/audit rows, then reloads the campaign. No optimistic update.

These screens do not send email, calendar invitations or offer letters; they label those
outward actions **SIMULATED — INTEGRATION PENDING**. They do not create hiring policy,
authenticate actors, or infer a candidate's response from outside the portal.

Native `select`, `button` and `details` controls remain keyboard accessible with visible
focus. Status and save errors use `role="status"`.
