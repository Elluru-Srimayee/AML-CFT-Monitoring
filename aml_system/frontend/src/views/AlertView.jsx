import React, { useEffect, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { AlertCircle, ArrowLeft, Link as LinkIcon } from 'lucide-react'
import { fetchAlertDetail } from '../api'

export default function AlertView() {
  const { alertId } = useParams()
  const navigate = useNavigate()
  const [alertData, setAlertData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!alertId) return
    setError('')
    fetchAlertDetail(alertId)
      .then((data) => setAlertData(data))
      .catch((err) => setError(err.message || 'Failed to load alert'))
  }, [alertId])

  if (!alertData && !error) {
    return (
      <div className="card text-center py-12">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        <p className="text-gray-600 mt-3">Loading alert details...</p>
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
          <p className="font-semibold text-danger-900">Unable to load alert</p>
          <p className="text-sm text-danger-700 mt-2">{error}</p>
        </div>
      </div>
    )
  }

  const formattedDate = alertData.timestamp ? new Date(alertData.timestamp).toLocaleString() : 'N/A'

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.24em] text-slate-500">Alert details</p>
          <h1 className="text-3xl font-bold text-slate-900 mt-2">{alertData.alert_id}</h1>
          <p className="text-gray-600 mt-2">Sender: <span className="font-mono">{alertData.sender_account || 'N/A'}</span></p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link to="/alerts" className="btn-secondary inline-flex items-center gap-2">
            <ArrowLeft className="w-4 h-4" /> Back to Alerts
          </Link>
          <a
            href={`${process.env.REACT_APP_API_BASE || 'http://localhost:8000'}/api/alerts/${alertId}`}
            target="_blank"
            rel="noreferrer"
            className="btn-secondary inline-flex items-center gap-2"
          >
            <LinkIcon className="w-4 h-4" /> Raw JSON
          </a>
        </div>
      </div>

      <div className="card grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <p className="text-sm text-gray-600">Risk Tier</p>
          <p className="text-3xl font-bold text-slate-900">{alertData.risk_tier || 'N/A'}</p>
        </div>

        <div className="space-y-3">
          <p className="text-sm text-gray-600">Risk Score</p>
          <p className="text-3xl font-bold text-slate-900">{alertData.risk_score ?? 'N/A'}</p>
        </div>

        <div className="space-y-3">
          <p className="text-sm text-gray-600">Amount</p>
          <p className="text-2xl font-semibold text-slate-900">${Number(alertData.amount || 0).toLocaleString()}</p>
        </div>

        <div className="space-y-3">
          <p className="text-sm text-gray-600">Timestamp</p>
          <p className="text-xl font-semibold text-slate-900">{formattedDate}</p>
        </div>
      </div>

      <div className="card">
        <p className="text-sm font-semibold mb-3">Transaction details</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="key-value-row"><span>Sender account</span><span>{alertData.sender_account || 'N/A'}</span></div>
          <div className="key-value-row"><span>Receiver account</span><span>{alertData.receiver_account || 'N/A'}</span></div>
          <div className="key-value-row"><span>Payment currency</span><span>{alertData.payment_currency || 'N/A'}</span></div>
          <div className="key-value-row"><span>Received currency</span><span>{alertData.received_currency || 'N/A'}</span></div>
          <div className="key-value-row"><span>Sender bank location</span><span>{alertData.sender_bank_location || 'N/A'}</span></div>
          <div className="key-value-row"><span>Receiver bank location</span><span>{alertData.receiver_bank_location || 'N/A'}</span></div>
          <div className="key-value-row"><span>Payment type</span><span>{alertData.payment_type || 'N/A'}</span></div>
        </div>
      </div>

      <div className="card">
        <p className="text-sm font-semibold mb-3">Triggered rules</p>
        <div className="flex flex-wrap gap-2">
          {(alertData.triggered_rules || 'N/A').split('|').filter(Boolean).map((rule) => (
            <span key={rule} className="badge badge-medium">{rule}</span>
          ))}
          {!alertData.triggered_rules && <span className="text-sm text-gray-500">No rules recorded</span>}
        </div>
      </div>

      <div className="card">
        <p className="text-sm font-semibold mb-3">Rule reasons</p>
        {alertData.rule_reasons ? (
          <pre className="case-json mt-2 whitespace-pre-wrap">{alertData.rule_reasons}</pre>
        ) : (
          <p className="text-sm text-gray-500">No rule reasons provided.</p>
        )}
      </div>

      <div className="card">
        <p className="text-sm font-semibold mb-3">Full alert payload</p>
        <pre className="case-json mt-2">{JSON.stringify(alertData, null, 2)}</pre>
      </div>
    </div>
  )
}
