import { PageHeader, Card, Button, Badge } from "../components/ui"
import { reportsList } from "../data/mock"
import { Download, FileText } from "lucide-react"

export default function Reports() {
  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="Candidate 360 assessments and campaign shortlist exports"
        action={<Button>Generate New Report</Button>}
      />

      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-ink-500 border-b border-line">
              <th className="py-2 font-medium">Report</th>
              <th className="py-2 font-medium">Campaign</th>
              <th className="py-2 font-medium">Generated</th>
              <th className="py-2 font-medium">Candidates</th>
              <th className="py-2 font-medium">Type</th>
              <th className="py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {reportsList.map((r) => (
              <tr key={r.id} className="border-b border-line/60">
                <td className="py-2.5 text-ink-900 font-medium flex items-center gap-2">
                  <FileText size={15} className="text-ink-400" /> {r.name}
                </td>
                <td className="py-2.5 text-ink-500">{r.campaign}</td>
                <td className="py-2.5 text-ink-500">{r.generated}</td>
                <td className="py-2.5 text-ink-700">{r.candidates}</td>
                <td className="py-2.5">
                  <Badge className="bg-brand-100 text-brand-600">{r.type}</Badge>
                </td>
                <td className="py-2.5 text-right">
                  <Button variant="ghost">
                    <Download size={15} /> Download
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
