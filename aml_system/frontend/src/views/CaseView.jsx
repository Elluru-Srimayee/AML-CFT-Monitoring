import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Sparkles, ShieldAlert, FileText, Link as LinkIcon } from 'lucide-react'
import { fetchCaseDetail } from '../api'

export default function CaseView() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [caseData, setCaseData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!caseId) return
    setError('')
    fetchCaseDetail(caseId)
      .then(setCaseData)
      .catch((err) => setError(err.message || 'Failed to load case'))
  }, [caseId])

  if (!caseData && !error) {
    return (
      <div className="card text-center py-12">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        <p className="text-gray-600 mt-3">Loading case details...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <button className="btn-secondary" onClick={() => navigate(-1)}>
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="card bg-danger-50 border border-danger-200">
          <p className="font-semibold text-danger-900">Unable to load case</p>
          <p className="text-sm text-danger-700 mt-2">{error}</p>
        </div>
      </div>
    )
  }

  const rules = caseData.triggered_rules || []
  const profile = caseData.customer_profile || {}

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.24em] text-slate-500">Case details</p>
          <h1 className="text-3xl font-bold text-slate-900 mt-2">{caseData.case_id}</h1>
          <p className="text-gray-600 mt-2">Subject account: <span className="font-mono">{caseData.subject_account}</span></p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/sar" className="btn-secondary inline-flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" /> Back to SAR
          </Link>
          <a
            href={`${process.env.REACT_APP_API_BASE || 'http://localhost:8000'}/api/cases/${caseId}`}
            target="_blank"
            rel="noreferrer"
            className="btn-secondary inline-flex items-center gap-2"
          >
            <LinkIcon className="w-4 h-4" /> Raw JSON
          </a>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="card">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Status</p>
              <div className="badge badge-critical" style={{ background: caseData.status === 'ESCALATED' ? 'rgba(239, 68, 68, 0.12)' : '#eef2ff', color: caseData.status === 'ESCALATED' ? '#b91c1c' : '#1d4ed8' }}>
                {caseData.status}
              </div>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Risk Tier</p>
              <p className="text-xl font-semibold text-slate-900">{caseData.risk_tier}</p>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Risk Score</p>
              <p className="text-xl font-semibold text-slate-900">{caseData.risk_score}</p>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Transaction Count</p>
              <p className="text-xl font-semibold text-slate-900">{caseData.transaction_count}</p>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Total Amount</p>
              <p className="text-xl font-semibold text-slate-900">${Number(caseData.total_amount || 0).toLocaleString()}</p>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Date range</p>
              <p className="text-base text-slate-700">{caseData.date_range_start || 'N/A'} → {caseData.date_range_end || 'N/A'}</p>
            </div>
          </div>

          <div className="mt-6">
            <p className="text-sm font-semibold mb-2">Triggered Rules</p>
            <div className="flex flex-wrap gap-2">
              {rules.length ? (
                rules.map((rule) => (
                  <span key={rule} className="badge badge-medium">{rule}</span>
                ))
              ) : (
                <span className="text-sm text-gray-500">No rules recorded</span>
              )}
            </div>
          </div>
        </div>

        <div className="card">
          <p className="text-sm font-semibold mb-3">Customer profile</p>
          <div className="grid gap-3">
            {profile.full_name && <div className="key-value-row"><span>Name</span><span>{profile.full_name}</span></div>}
            {profile.risk_category && <div className="key-value-row"><span>Risk category</span><span>{profile.risk_category}</span></div>}
            {profile.unique_counterparties != null && <div className="key-value-row"><span>Unique counterparties</span><span>{profile.unique_counterparties}</span></div>}
            {profile.payment_types_used?.length > 0 && <div className="key-value-row"><span>Payment methods</span><span>{profile.payment_types_used.join(', ')}</span></div>}
            {profile.countries_involved?.length > 0 && <div className="key-value-row"><span>Countries</span><span>{profile.countries_involved.join(', ')}</span></div>}
            {profile.first_seen && <div className="key-value-row"><span>First seen</span><span>{profile.first_seen}</span></div>}
            {profile.last_seen && <div className="key-value-row"><span>Last seen</span><span>{profile.last_seen}</span></div>}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm uppercase tracking-[0.24em] text-slate-500">Pattern findings</p>
            <h2 className="text-xl font-bold text-slate-900 mt-2">Case pattern chain</h2>
          </div>
          <Sparkles className="w-6 h-6 text-primary-600" />
        </div>
        {caseData.pattern_findings?.length ? (
          <div className="pattern-chain">
            {caseData.pattern_findings.map((item, index) => (
              <div key={`${item}-${index}`} className="pattern-step">
                <div className="pattern-step-marker" />
                <div className="pattern-step-content">
                  <p className="text-sm text-slate-600">Step {index + 1}</p>
                  <p className="text-base text-slate-900">{item}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-600">No pattern findings were recorded for this case.</p>
        )}
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm uppercase tracking-[0.24em] text-slate-500">Alerts</p>
            <h2 className="text-xl font-bold text-slate-900 mt-2">Included alerts</h2>
          </div>
          <ShieldAlert className="w-6 h-6 text-slate-500" />
        </div>
        <div className="overflow-x-auto">
          <table className="detail-table">
            <thead>
              <tr>
                <th>Alert ID</th>
                <th>Receiver</th>
                <th>Amount</th>
                <th>Risk Tier</th>
                <th>Rules</th>
              </tr>
            </thead>
            <tbody>
              {caseData.alerts.map((alert) => (
                <tr key={alert.alert_id}>
                  <td>{alert.alert_id}</td>
                  <td>{alert.receiver_account}</td>
                  <td>${Number(alert.amount || 0).toLocaleString()}</td>
                  <td>{alert.risk_tier}</td>
                  <td>{alert.triggered_rules}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <p className="text-sm uppercase tracking-[0.24em] text-slate-500">Narrative</p>
        <pre className="case-json mt-4">{caseData.narrative || 'No narrative available.'}</pre>
      </div>

      <div className="card">
        <p className="text-sm uppercase tracking-[0.24em] text-slate-500">Full case payload</p>
        <pre className="case-json mt-4">{JSON.stringify(caseData, null, 2)}</pre>
      </div>
    </div>
  )
}
