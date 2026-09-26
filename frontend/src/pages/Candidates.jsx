import { useState } from "react"
import { PageHeader, Card, Button, Badge } from "../components/ui"
import { candidates, statusStyles } from "../data/mock"
import { UploadCloud, X } from "lucide-react"

const tabs = ["Ranking", "360 Report", "Compare", "What-if", "Shortlist"]

export default function Candidates() {
  const [tab, setTab] = useState(0)
  const [selected, setSelected] = useState([1, 2, 3])
  const [checked, setChecked] = useState([1, 2])
  const focus = candidates[0]

  return (
    <div>
      <PageHeader title="Candidates — Senior Software Engineer" subtitle="1,248 total applications · 1,120 processed" />

      <div className="flex gap-1 mb-6 border-b border-line">
        {tabs.map((t, i) => (
          <button
            key={t}
            onClick={() => setTab(i)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px ${
              tab === i ? "border-brand-600 text-brand-600" : "border-transparent text-ink-500 hover:text-ink-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 0 && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-center gap-4 border-2 border-dashed border-line rounded-lg p-6 justify-center text-center">
              <UploadCloud className="text-ink-400" size={22} />
              <div>
                <p className="text-sm text-ink-700 font-medium">Drag & drop resumes here</p>
                <p className="text-xs text-ink-400">Supports PDF, DOCX (max 50MB each)</p>
              </div>
              <Button className="ml-4">Choose Files</Button>
            </div>
          </Card>

          <Card title="Candidate Ranking">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-ink-500 border-b border-line">
                  <th className="py-2 font-medium">#</th>
                  <th className="py-2 font-medium">Candidate</th>
                  <th className="py-2 font-medium">Score</th>
                  <th className="py-2 font-medium">Confidence</th>
                  <th className="py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c, i) => (
                  <tr key={c.id} className="border-b border-line/60">
                    <td className="py-2.5 text-ink-500">{i + 1}</td>
                    <td className="py-2.5 text-ink-900 font-medium">{c.name}</td>
                    <td className="py-2.5 text-ink-700">{c.score}</td>
                    <td className="py-2.5 text-ink-500">{c.confidence}%</td>
                    <td className="py-2.5"><Badge className={statusStyles[c.status]}>{c.status}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {tab === 1 && (
        <Card>
          <div className="flex items-center gap-4 mb-6">
            <div className="w-14 h-14 rounded-full bg-brand-100 text-brand-600 flex items-center justify-center font-semibold text-lg">
              {focus.name.split(" ").map(n => n[0]).join("")}
            </div>
            <div className="flex-1">
              <p className="font-semibold text-ink-900">{focus.name}</p>
              <p className="text-sm text-ink-500">{focus.location}</p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-semibold text-brand-600">{focus.score}%</p>
              <p className="text-xs text-ink-500">Overall Score</p>
            </div>
            <Badge className={statusStyles[focus.status]}>{focus.status}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-6">
            {[
              ["Mandatory Requirements", 95],
              ["Skills", 90],
              ["Experience", 88],
              ["Education", 85],
              ["Certifications", 80],
            ].map(([label, pct]) => (
              <div key={label}>
                <div className="flex justify-between text-xs text-ink-500 mb-1">
                  <span>{label}</span><span>{pct}%</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-brand-500 rounded-full" style={{ width: `${pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {tab === 2 && (
        <Card title={`Compare Candidates (${selected.length}/3)`}>
          <table className="w-full text-sm">
            <tbody>
              {[
                ["Overall Score", (c) => c.score],
                ["Experience (yrs)", (c) => c.exp],
                ["Skills Match", (c) => `${c.skills}%`],
                ["Education", (c) => c.education],
                ["Certifications", (c) => c.certs],
                ["Location", (c) => c.location],
              ].map(([label, fn]) => (
                <tr key={label} className="border-b border-line/60">
                  <td className="py-2.5 text-ink-500 w-40">{label}</td>
                  {selected.map((id) => {
                    const c = candidates.find((x) => x.id === id)
                    return <td key={id} className="py-2.5 text-ink-900 font-medium">{fn(c)}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === 3 && <WhatIf />}

      {tab === 4 && (
        <Card title="Shortlist & Actions">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-500 border-b border-line">
                <th className="py-2 w-8"></th>
                <th className="py-2 font-medium">Candidate</th>
                <th className="py-2 font-medium">Score</th>
                <th className="py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {candidates.slice(0, 5).map((c) => (
                <tr key={c.id} className="border-b border-line/60">
                  <td className="py-2.5">
                    <input
                      type="checkbox"
                      checked={checked.includes(c.id)}
                      onChange={() =>
                        setChecked((s) => s.includes(c.id) ? s.filter((x) => x !== c.id) : [...s, c.id])
                      }
                    />
                  </td>
                  <td className="py-2.5 text-ink-900 font-medium">{c.name}</td>
                  <td className="py-2.5 text-ink-700">{c.score}</td>
                  <td className="py-2.5"><Badge className={statusStyles[c.status]}>{c.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between mt-5">
            <p className="text-sm text-ink-500">{checked.length} candidates selected</p>
            <div className="flex gap-2">
              <Button variant="secondary">Reject</Button>
              <Button variant="secondary">Hold</Button>
              <Button variant="secondary">Export</Button>
              <Button>Shortlist</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}

function WhatIf() {
  const [weights, setWeights] = useState({ Skills: 30, Experience: 20, Education: 10, Industry: 10, Seniority: 10, Cultural: 10 })
  return (
    <div className="grid grid-cols-3 gap-4">
      <Card title="Adjust Weights" className="col-span-1">
        {Object.entries(weights).map(([k, v]) => (
          <div key={k} className="mb-4">
            <div className="flex justify-between text-xs text-ink-600 mb-1">
              <span>{k}</span><span>{v}%</span>
            </div>
            <input
              type="range" min="0" max="50" value={v}
              onChange={(e) => setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))}
              className="w-full accent-brand-600"
            />
          </div>
        ))}
        <Button className="w-full justify-center mt-2">Apply (Simulation Only)</Button>
      </Card>
      <Card title="Impact on Ranking" className="col-span-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-500 border-b border-line">
              <th className="py-2 font-medium">Rank</th>
              <th className="py-2 font-medium">Candidate</th>
              <th className="py-2 font-medium">New Score</th>
              <th className="py-2 font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {candidates.slice(0, 5).map((c, i) => {
              const change = Math.round((weights.Skills - 30) / 5) + (i % 2 === 0 ? 1 : -1)
              return (
                <tr key={c.id} className="border-b border-line/60">
                  <td className="py-2.5 text-ink-500">{i + 1}</td>
                  <td className="py-2.5 text-ink-900 font-medium">{c.name}</td>
                  <td className="py-2.5 text-ink-700">{Math.max(0, Math.min(100, c.score + change))}</td>
                  <td className={`py-2.5 font-medium ${change >= 0 ? "text-good-600" : "text-bad-600"}`}>
                    {change >= 0 ? `+${change}` : change}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
