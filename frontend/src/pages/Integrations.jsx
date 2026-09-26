import { PageHeader, Card, Badge, Button } from "../components/ui"
import { auditLog } from "../data/mock"

const connectors = [
  { name: "Workday ATS", status: "Connected" },
  { name: "Greenhouse", status: "Connected" },
  { name: "LinkedIn Recruiter", status: "Not Connected" },
  { name: "Slack Notifications", status: "Connected" },
]

export default function Integrations() {
  return (
    <div>
      <PageHeader title="Integrations & Audit Logs" subtitle="ATS connectors and system activity" />

      <div className="grid grid-cols-2 gap-4 mb-6">
        {connectors.map((c) => (
          <Card key={c.name}>
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-ink-900">{c.name}</p>
              <Badge className={c.status === "Connected" ? "bg-good-100 text-good-600" : "bg-slate-100 text-ink-500"}>
                {c.status}
              </Badge>
            </div>
          </Card>
        ))}
      </div>

      <Card title="Audit Logs" action={<Button variant="secondary">Export</Button>}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-500 border-b border-line">
              <th className="py-2 font-medium">Date & Time</th>
              <th className="py-2 font-medium">User</th>
              <th className="py-2 font-medium">Action</th>
              <th className="py-2 font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {auditLog.map((a, i) => (
              <tr key={i} className="border-b border-line/60">
                <td className="py-2.5 text-ink-500">{a.time}</td>
                <td className="py-2.5 text-ink-900">{a.user}</td>
                <td className="py-2.5 text-ink-700">{a.action}</td>
                <td className="py-2.5 text-ink-500">{a.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
