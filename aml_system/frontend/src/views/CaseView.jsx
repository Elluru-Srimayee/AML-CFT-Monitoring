import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

export default function CaseView() {
  const { caseId } = useParams()
  const [caseData, setCaseData] = useState(null)

  useEffect(() => {
    if (!caseId) return
    fetch(`${process.env.REACT_APP_API_BASE || 'http://localhost:8000'}/api/cases/${caseId}`)
      .then(r => r.json())
      .then(setCaseData)
      .catch(() => {})
  }, [caseId])

  if (!caseData) return <div>Loading case...</div>

  return (
    <div>
      <h2>Case {caseData.case_id}</h2>
      <div>Subject: {caseData.subject_account}</div>
      <div>Risk tier: {caseData.risk_tier}</div>
      <h3>Alerts</h3>
      <ul>
        {caseData.alerts.map(a => <li key={a.alert_id}>{a.alert_id} — {a.sender_account} → {a.receiver_account} ({a.amount})</li>)}
      </ul>
      <h3>Narrative</h3>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{caseData.narrative}</pre>
    </div>
  )
}
