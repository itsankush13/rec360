import { PageHeader, Card, Stat } from "../components/ui"
import { LineChart, Line, ResponsiveContainer, XAxis, Tooltip, PieChart, Pie, Cell } from "recharts"
import { throughput, outcomes } from "../data/mock"

export default function Dashboard() {
  return (
    <div>
      <PageHeader title="HR KPI Dashboard" subtitle="Last 30 days across all active campaigns" />

      <div className="grid grid-cols-4 gap-4 mb-6">
        <Stat label="Total Applications" value="1,248" delta="12%" />
        <Stat label="Avg. Time to Hire" value="6.2 days" delta="18%" />
        <Stat label="Screening Efficiency" value="92%" delta="4%" />
        <Stat label="Hires" value="48" delta="20%" />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Workload & Throughput" className="col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={throughput}>
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e9f0" }} />
              <Line type="monotone" dataKey="value" stroke="#3b6ef6" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Application Outcomes">
          <div className="flex items-center gap-6">
            <ResponsiveContainer width={140} height={140}>
              <PieChart>
                <Pie data={outcomes} dataKey="value" innerRadius={40} outerRadius={62} paddingAngle={2}>
                  {outcomes.map((o, i) => <Cell key={i} fill={o.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2">
              {outcomes.map((o) => (
                <div key={o.name} className="flex items-center gap-2 text-xs">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: o.color }} />
                  <span className="text-ink-700">{o.name}</span>
                  <span className="text-ink-400">{o.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
