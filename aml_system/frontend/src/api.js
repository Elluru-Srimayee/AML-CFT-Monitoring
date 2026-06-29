const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8000'

export async function fetchSummary(sample = 100) {
  const res = await fetch(`${API_BASE}/api/run?sample=${sample}`)
  return res.json()
}

export async function runPipeline(sample) {
  const res = await fetch(`${API_BASE}/api/run?sample=${sample}`)
  return res.json()
}

export async function fetchTransactions(sample=100) {
  const res = await fetch(`${API_BASE}/api/transactions?sample=${sample}`)
  return res.json()
}

export async function fetchAlerts(offset = 0, limit = 50, riskTier = '') {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  })
  if (riskTier) params.append('risk_tier', riskTier)

  const res = await fetch(`${API_BASE}/api/alerts/list?${params.toString()}`)
  return res.json()
}

export async function fetchSARCandidates() {
  const res = await fetch(`${API_BASE}/api/sar/candidates`)
  return res.json()
}

export async function generateSAR(caseId) {
  const res = await fetch(`${API_BASE}/api/sar/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ case_id: caseId }),
  })
  return res.json()
}

export async function fetchCases() {
  const res = await fetch(`${API_BASE}/api/cases`)
  return res.json()
}

export async function fetchAlertDetail(id) {
  const res = await fetch(`${API_BASE}/api/alerts/${id}`)
  return res.json()
}

export async function fetchCaseDetail(id) {
  const res = await fetch(`${API_BASE}/api/cases/${id}`)
  return res.json()
}
