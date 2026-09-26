import { useState } from "react"
import { PageHeader, Card, Button, Field, Badge, inputClass } from "../components/ui"
import { rubric, campaignList } from "../data/mock"
import { CheckCircle2, Plus, ArrowLeft } from "lucide-react"

const tabs = ["Job Setup", "Extracted Requirements", "Evaluation Rubric", "Control Tower"]

const batches = [
  { label: "Batch 1 (1–1,000)", pct: 100 },
  { label: "Batch 2 (1,001–2,000)", pct: 76 },
  { label: "Batch 3 (2,001–3,000)", pct: 12 },
  { label: "Batch 4 (3,001–4,000)", pct: 0 },
]

export default function Campaigns() {
  const [view, setView] = useState("list") // "list" | "create"
  const [tab, setTab] = useState(0)

  if (view === "list") {
    return (
      <div>
        <PageHeader
          title="Campaigns"
          subtitle={`${campaignList.length} campaigns · ${campaignList.filter(c => c.status === "Active").length} active`}
          action={
            <Button onClick={() => { setView("create"); setTab(0) }}>
              <Plus size={16} /> New Campaign
            </Button>
          }
        />
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-500 border-b border-line">
                <th className="py-2 font-medium">Campaign</th>
                <th className="py-2 font-medium">Business Unit</th>
                <th className="py-2 font-medium">Recruiter</th>
                <th className="py-2 font-medium">Candidates</th>
                <th className="py-2 font-medium">Status</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {campaignList.map((c) => (
                <tr key={c.id} className="border-b border-line/60">
                  <td className="py-2.5 text-ink-900 font-medium">{c.title}</td>
                  <td className="py-2.5 text-ink-500">{c.unit}</td>
                  <td className="py-2.5 text-ink-500">{c.recruiter}</td>
                  <td className="py-2.5 text-ink-700">{c.candidates.toLocaleString()}</td>
                  <td className="py-2.5">
                    <Badge className={c.status === "Active" ? "bg-good-100 text-good-600" : "bg-slate-100 text-ink-500"}>
                      {c.status}
                    </Badge>
                  </td>
                  <td className="py-2.5 text-right">
                    <Button
                      variant="ghost"
                      onClick={() => { setView("create"); setTab(3) }}
                    >
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title="Create New Campaign"
        subtitle="Senior Software Engineer · Engineering"
        action={
          <Button variant="secondary" onClick={() => setView("list")}>
            <ArrowLeft size={15} /> Back to Campaigns
          </Button>
        }
      />

      <div className="flex gap-1 mb-6 border-b border-line">
        {tabs.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === i ? "border-brand-600 text-brand-600" : "border-transparent text-ink-500 hover:text-ink-700"
            }`}
          >
            {i + 1}. {t}
          </button>
        ))}
      </div>

      {tab === 0 && (
        <Card>
          <div className="grid grid-cols-2 gap-5">
            <Field label="Job Title *">
              <input className={inputClass} defaultValue="Senior Software Engineer" />
            </Field>
            <Field label="Vacancies *">
              <input className={inputClass} defaultValue="10" />
            </Field>
            <Field label="Location *">
              <input className={inputClass} defaultValue="Bengaluru, India" />
            </Field>
            <Field label="Business Unit *">
              <input className={inputClass} defaultValue="Engineering" />
            </Field>
            <Field label="Recruiter *">
              <input className={inputClass} defaultValue="Aarav Sharma" />
            </Field>
            <Field label="Hiring Manager *">
              <input className={inputClass} defaultValue="Priya Nair" />
            </Field>
            <Field label="Target Date">
              <input type="date" className={inputClass} defaultValue="2026-06-30" />
            </Field>
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <Button variant="secondary" onClick={() => setView("list")}>Cancel</Button>
            <Button onClick={() => setTab(1)}>Next</Button>
          </div>
        </Card>
      )}

      {tab === 1 && (
        <Card>
          <div className="grid grid-cols-3 gap-6 text-sm">
            <div>
              <p className="font-semibold text-ink-700 mb-2">Skills (12)</p>
              <div className="flex flex-wrap gap-1.5">
                {["Java", "Python", "SQL", "AWS", "Docker", "Kubernetes", "React", "Node.js"].map((s) => (
                  <Badge key={s} className="bg-brand-100 text-brand-600">{s}</Badge>
                ))}
              </div>
              <p className="font-semibold text-ink-700 mt-5 mb-2">Experience</p>
              <p className="text-ink-500">Total Experience: 5+ years</p>
              <p className="text-ink-500">Relevant Experience: 3+ years</p>
              <p className="text-ink-500">Domain: Software Development</p>
            </div>
            <div>
              <p className="font-semibold text-ink-700 mb-2">Qualifications</p>
              <p className="text-ink-500">Bachelor's in Computer Science or related field</p>
              <p className="font-semibold text-ink-700 mt-5 mb-2">Certifications</p>
              <p className="text-ink-500">AWS Certified Developer (Preferred)</p>
            </div>
            <div>
              <p className="font-semibold text-ink-700 mb-2">Requirement Type</p>
              <div className="space-y-1.5">
                {["Mandatory", "Preferred", "Informational"].map((r) => (
                  <label key={r} className="flex items-center gap-2 text-ink-600">
                    <input type="radio" name="reqtype" defaultChecked={r === "Mandatory"} /> {r}
                  </label>
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <Button variant="secondary" onClick={() => setTab(0)}>Back</Button>
            <Button onClick={() => setTab(2)}>Next</Button>
          </div>
        </Card>
      )}

      {tab === 2 && (
        <Card
          title="Evaluation Rubric"
          action={<Badge className="bg-good-100 text-good-600"><CheckCircle2 size={12} className="mr-1 inline" />Approved</Badge>}
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-500 border-b border-line">
                <th className="py-2 font-medium">Criterion</th>
                <th className="py-2 font-medium">Weight</th>
                <th className="py-2 font-medium">Type</th>
              </tr>
            </thead>
            <tbody>
              {rubric.map((r) => (
                <tr key={r.criterion} className="border-b border-line/60">
                  <td className="py-2.5 text-ink-900">{r.criterion}</td>
                  <td className="py-2.5 text-ink-700">{r.weight}%</td>
                  <td className="py-2.5">
                    <Badge className={
                      r.type === "Mandatory" ? "bg-bad-100 text-bad-600" :
                      r.type === "Preferred" ? "bg-brand-100 text-brand-600" : "bg-slate-100 text-ink-500"
                    }>{r.type}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex justify-end gap-2 mt-6">
            <Button variant="secondary">Edit</Button>
            <Button onClick={() => setTab(3)}>Submit for Approval</Button>
          </div>
        </Card>
      )}

      {tab === 3 && (
        <div>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <Card><p className="text-sm text-ink-500">Total Candidates</p><p className="text-2xl font-semibold text-ink-900 mt-2">1,248</p></Card>
            <Card><p className="text-sm text-ink-500">Processed</p><p className="text-2xl font-semibold text-ink-900 mt-2">1,120 (90%)</p></Card>
            <Card><p className="text-sm text-ink-500">Errors</p><p className="text-2xl font-semibold text-bad-600 mt-2">30 (2%)</p></Card>
          </div>
          <Card title="Batch Progress">
            <div className="space-y-4">
              {batches.map((b) => (
                <div key={b.label}>
                  <div className="flex justify-between text-xs text-ink-600 mb-1">
                    <span>{b.label}</span><span>{b.pct}%</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-brand-500 rounded-full" style={{ width: `${b.pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
