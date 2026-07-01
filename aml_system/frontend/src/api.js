const API_BASE = process.env.REACT_APP_API_BASE || ''

const buildUrl = (path) => `${API_BASE}${path}`

const handleResponse = async (res) => {
  const content = await res.text()
  if (!res.ok) {
    let parsed
    try {
      parsed = JSON.parse(content)
    } catch {
      parsed = null
    }
    const message = parsed?.detail || parsed?.message || content || `${res.status} ${res.statusText}`
    throw new Error(message)
  }
  return content ? JSON.parse(content) : null
}

export async function fetchSummary(sample, alertLimit = 100, caseLimit = 100) {
  const params = new URLSearchParams({ alert_limit: String(alertLimit), case_limit: String(caseLimit) })
  if (sample !== undefined && sample !== null && sample !== '') {
    params.set('sample', String(sample))
  }
  const res = await fetch(`${API_BASE}/api/run?${params.toString()}`)
  return res.json()
}

export async function runPipeline(sample, alertLimit = 100, caseLimit = 100) {
  const params = new URLSearchParams({ alert_limit: String(alertLimit), case_limit: String(caseLimit) })
  if (sample !== undefined && sample !== null && sample !== '') {
    params.set('sample', String(sample))
  }
  const res = await fetch(`${API_BASE}/api/run?${params.toString()}`)
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

  const res = await fetch(buildUrl(`/api/alerts/list?${params.toString()}`))
  return handleResponse(res)
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

export async function fetchSARDetail(caseId) {
  const res = await fetch(`${API_BASE}/api/sar/${caseId}`)
  return res.json()
}

export async function fetchCases() {
  const res = await fetch(`${API_BASE}/api/cases`)
  return res.json()
}

export async function fetchAlertDetail(id) {
  const res = await fetch(buildUrl(`/api/alerts/${id}`))
  return handleResponse(res)
}

export async function fetchCaseDetail(id) {
  const res = await fetch(buildUrl(`/api/cases/${id}`))
  return handleResponse(res)
}
