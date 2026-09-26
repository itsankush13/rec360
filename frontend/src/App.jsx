import { HashRouter, Routes, Route } from "react-router-dom"
import Sidebar from "./components/Sidebar"
import Dashboard from "./pages/Dashboard"
import Campaigns from "./pages/Campaigns"
import Candidates from "./pages/Candidates"
import Reports from "./pages/Reports"
import Integrations from "./pages/Integrations"
import Settings from "./pages/Settings"

export default function App() {
  return (
    <HashRouter>
      <div className="flex min-h-screen bg-canvas">
        <Sidebar />
        <main className="flex-1 p-8 max-w-[1400px]">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/campaigns" element={<Campaigns />} />
            <Route path="/candidates" element={<Candidates />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/integrations" element={<Integrations />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  )
}
