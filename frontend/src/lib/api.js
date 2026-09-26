const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"

export async function screenCandidates(jdText, files, campaignId = 1) {
  console.log("[screenCandidates] start", { jdTextLength: jdText?.length || 0, fileCount: files?.length || 0 })
  const formData = new FormData()
  formData.append("jd_text", jdText)
  formData.append("campaign_id", String(campaignId))
  for (const file of files) formData.append("files", file)

  const response = await fetch(`${API_BASE_URL}/api/campaigns/screen`, {
    method: "POST",
    body: formData,
  })
  if (!response.ok) {
    throw new Error(await response.text() || `Screening failed (${response.status})`)
  }
  return response.json()
}

export async function saveRubric(campaignId, rubric) {
  const response = await fetch(`${API_BASE_URL}/api/campaigns/${campaignId}/rubric`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rubric }),
  })
  if (!response.ok) throw new Error(await response.text() || "Could not save rubric")
  return response.json()
}

export async function approveRubric(campaignId, versionId) {
  const response = await fetch(`${API_BASE_URL}/api/campaigns/${campaignId}/rubric/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version_id: versionId }),
  })
  if (!response.ok) throw new Error(await response.text() || "Could not approve rubric")
  return response.json()
}