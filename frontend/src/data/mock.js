export const candidates = [
  { id: 1, name: "Rahul Sharma", location: "Bengaluru", score: 92, confidence: 96, status: "Strong Fit", exp: 5.5, skills: 90, education: "B.Tech (CS)", certs: "AWS" },
  { id: 2, name: "Priya Menon", location: "Hyderabad", score: 88, confidence: 92, status: "Strong Fit", exp: 5, skills: 85, education: "B.E (IT)", certs: "Azure" },
  { id: 3, name: "Amit Verma", location: "Pune", score: 84, confidence: 88, status: "Potential Fit", exp: 4.5, skills: 80, education: "B.Tech (CS)", certs: "None" },
  { id: 4, name: "Sneha Iyer", location: "Chennai", score: 78, confidence: 80, status: "Potential Fit", exp: 3.5, skills: 74, education: "B.Sc (CS)", certs: "None" },
  { id: 5, name: "Karan Mehta", location: "Delhi", score: 74, confidence: 80, status: "Review Required", exp: 3, skills: 70, education: "B.Tech (IT)", certs: "None" },
  { id: 6, name: "Rohan Das", location: "Kolkata", score: 68, confidence: 72, status: "Review Required", exp: 2.5, skills: 65, education: "BCA", certs: "None" },
  { id: 7, name: "Neha Gupta", location: "Mumbai", score: 62, confidence: 68, status: "Not Recommended", exp: 2, skills: 58, education: "BCA", certs: "None" },
  { id: 8, name: "Arjun Singh", location: "Jaipur", score: 58, confidence: 60, status: "Not Recommended", exp: 1.5, skills: 52, education: "B.Sc (IT)", certs: "None" },
]

export const statusStyles = {
  "Strong Fit": "bg-good-100 text-good-600",
  "Potential Fit": "bg-brand-100 text-brand-600",
  "Review Required": "bg-warn-100 text-warn-600",
  "Not Recommended": "bg-bad-100 text-bad-600",
}

export const throughput = [
  { day: "Apr 1", value: 12 }, { day: "Apr 7", value: 22 }, { day: "Apr 14", value: 18 },
  { day: "Apr 21", value: 30 }, { day: "Apr 28", value: 26 }, { day: "May 5", value: 34 },
]

export const outcomes = [
  { name: "Shortlisted", value: 34, color: "#3b6ef6" },
  { name: "Rejected", value: 52, color: "#e2536b" },
  { name: "On Hold", value: 8, color: "#d68a1f" },
  { name: "In Review", value: 6, color: "#17a673" },
]

export const rubric = [
  { criterion: "Skills & Technical Expertise", weight: 25, type: "Mandatory" },
  { criterion: "Experience & Relevance", weight: 20, type: "Mandatory" },
  { criterion: "Education & Certifications", weight: 10, type: "Mandatory" },
  { criterion: "Industry Experience", weight: 10, type: "Preferred" },
  { criterion: "Role Seniority", weight: 10, type: "Preferred" },
  { criterion: "Cultural Fit", weight: 5, type: "Informational" },
]

export const auditLog = [
  { time: "2026-04-28 14:32", user: "Priya Nair", action: "Rubric Approved", detail: "v1.2" },
  { time: "2026-04-28 11:15", user: "Aarav Sharma", action: "Candidate Override", detail: "Rahul Sharma - score adjusted" },
  { time: "2026-04-27 16:22", user: "System", action: "Batch Completed", detail: "1,000 files processed" },
  { time: "2026-04-26 09:10", user: "Neha Gupta", action: "Comments Added", detail: "For Priya Menon" },
  { time: "2026-04-25 13:45", user: "Rehan Das", action: "Shortlisted", detail: "Amit Verma" },
]

// New: backs the Campaigns list landing view
export const campaignList = [
  { id: 1, title: "Senior Software Engineer", unit: "Engineering", recruiter: "Aarav Sharma", candidates: 1248, status: "Active" },
  { id: 2, title: "Product Manager", unit: "Product", recruiter: "Priya Nair", candidates: 340, status: "Active" },
  { id: 3, title: "Data Analyst", unit: "Analytics", recruiter: "Neha Gupta", candidates: 512, status: "Draft" },
]

// New: backs the genuine Reports page
export const reportsList = [
  { id: 1, name: "Senior Software Engineer — Shortlist", campaign: "Senior Software Engineer", generated: "2026-04-28", candidates: 48, type: "Shortlist" },
  { id: 2, name: "Product Manager — Shortlist", campaign: "Product Manager", generated: "2026-04-20", candidates: 12, type: "Shortlist" },
  { id: 3, name: "Data Analyst — Full Report", campaign: "Data Analyst", generated: "2026-04-15", candidates: 30, type: "Full Report" },
  { id: 4, name: "Rahul Sharma — Candidate 360", campaign: "Senior Software Engineer", generated: "2026-04-28", candidates: 1, type: "Candidate 360" },
]
