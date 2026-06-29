import React, { useEffect, useState } from 'react'
import { FileText, Download, CheckCircle, AlertTriangle, Loader } from 'lucide-react'
import { fetchSARCandidates, generateSAR } from '../api'

export default function SAR() {
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState({})
  const [error, setError] = useState('')
  const [generated, setGenerated] = useState({})

  async function loadCandidates() {
    setLoading(true)
    setError('')
    try {
      const data = await fetchSARCandidates()
      setCandidates(data.candidates || data.sar_candidates || [])
    } catch (err) {
      setError('Failed to load SAR candidates')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCandidates()
  }, [])

  async function handleGenerateSAR(caseId) {
    setGenerating(prev => ({ ...prev, [caseId]: true }))
    try {
      const result = await generateSAR(caseId)
      if (result.success || result.sar_file) {
        setGenerated(prev => ({ ...prev, [caseId]: result.sar_file || result.filename }))
      } else {
        setError(`Failed to generate SAR for ${caseId}`)
      }
    } catch (err) {
      setError(`Error generating SAR: ${err.message}`)
      console.error(err)
    } finally {
      setGenerating(prev => ({ ...prev, [caseId]: false }))
    }
  }

  const getRiskBadgeColor = (tier) => {
    switch (tier) {
      case 'CRITICAL':
        return 'badge-critical'
      case 'HIGH':
        return 'badge-high'
      case 'MEDIUM':
        return 'badge-medium'
      default:
        return 'badge-low'
    }
  }

  const getRiskTextColor = (tier) => {
    switch (tier) {
      case 'CRITICAL':
        return 'text-danger-600 dark:text-danger-400'
      case 'HIGH':
        return 'text-warning-600 dark:text-warning-400'
      case 'MEDIUM':
        return 'text-blue-600 dark:text-blue-400'
      default:
        return 'text-success-600 dark:text-success-400'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card">
        <h2 className="text-2xl font-bold flex items-center gap-2 mb-4">
          <FileText className="w-6 h-6 text-primary-600 dark:text-primary-400" />
          SAR Report Generation
        </h2>
        <p className="text-gray-600 dark:text-gray-400">Review escalated cases and generate Suspicious Activity Reports (SAR) for regulatory filing</p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="card bg-danger-50 dark:bg-danger-900 border border-danger-200 dark:border-danger-700">
          <div className="flex gap-3">
            <AlertTriangle className="w-5 h-5 text-danger-600 dark:text-danger-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-danger-900 dark:text-danger-100">{error}</p>
              <button
                onClick={() => setError('')}
                className="text-sm text-danger-700 dark:text-danger-300 hover:underline mt-1"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card">
          <p className="text-gray-600 dark:text-gray-400 text-sm">Total Candidates</p>
          <p className="text-3xl font-bold text-primary-600 dark:text-primary-400">{candidates.length}</p>
        </div>
        <div className="card">
          <p className="text-gray-600 dark:text-gray-400 text-sm">Escalated (CRITICAL)</p>
          <p className="text-3xl font-bold text-danger-600 dark:text-danger-400">
            {candidates.filter(c => c.risk_tier === 'CRITICAL').length}
          </p>
        </div>
        <div className="card">
          <p className="text-gray-600 dark:text-gray-400 text-sm">Generated Reports</p>
          <p className="text-3xl font-bold text-success-600 dark:text-success-400">
            {Object.keys(generated).length}
          </p>
        </div>
      </div>

      {/* Candidates List */}
      <div className="space-y-4">
        {loading ? (
          <div className="card text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            <p className="text-gray-600 dark:text-gray-400 mt-2">Loading SAR candidates...</p>
          </div>
        ) : candidates.length > 0 ? (
          candidates.map((candidate) => (
            <div key={candidate.case_id} className="card">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Case Details */}
                <div>
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-bold text-primary-600 dark:text-primary-400">
                        {candidate.case_id}
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        Subject Account: <span className="font-mono">{candidate.subject_account}</span>
                      </p>
                    </div>
                    <span className={`badge ${getRiskBadgeColor(candidate.risk_tier)}`}>
                      {candidate.status}
                    </span>
                  </div>

                  <div className="space-y-3 mb-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                        <p className="text-xs text-gray-600 dark:text-gray-400">Risk Tier</p>
                        <p className={`text-lg font-bold ${getRiskTextColor(candidate.risk_tier)}`}>
                          {candidate.risk_tier}
                        </p>
                      </div>
                      <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                        <p className="text-xs text-gray-600 dark:text-gray-400">Risk Score</p>
                        <p className="text-lg font-bold text-blue-600 dark:text-blue-400">
                          {candidate.risk_score}
                        </p>
                      </div>
                    </div>

                    {candidate.total_amount && (
                      <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                        <p className="text-xs text-gray-600 dark:text-gray-400">Total Transaction Amount</p>
                        <p className="text-lg font-bold">${Number(candidate.total_amount).toLocaleString()}</p>
                      </div>
                    )}

                    {candidate.transaction_count && (
                      <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                        <p className="text-xs text-gray-600 dark:text-gray-400">Transaction Count</p>
                        <p className="text-lg font-bold">{candidate.transaction_count}</p>
                      </div>
                    )}
                  </div>

                  <div>
                    <p className="text-sm font-semibold mb-2">Triggered Rules:</p>
                    <div className="flex flex-wrap gap-2">
                      {candidate.triggered_rules && candidate.triggered_rules.map((rule) => (
                        <span key={rule} className="badge bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200">
                          {rule}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Narrative and Action */}
                <div className="flex flex-col">
                  <div className="flex-1 mb-4">
                    <p className="text-sm font-semibold mb-2">Investigation Summary:</p>
                    <p className="text-sm text-gray-600 dark:text-gray-400 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg h-40 overflow-y-auto">
                      {candidate.narrative || 'No narrative available'}
                    </p>
                  </div>

                  {candidate.sanctions_hits && candidate.sanctions_hits.length > 0 && (
                    <div className="mb-4 p-3 bg-danger-50 dark:bg-danger-900 border border-danger-200 dark:border-danger-700 rounded-lg">
                      <p className="text-sm font-semibold text-danger-900 dark:text-danger-100 mb-2 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" />
                        Sanctions Hits: {candidate.sanctions_hits.length}
                      </p>
                      <ul className="text-xs text-danger-800 dark:text-danger-200 space-y-1">
                        {candidate.sanctions_hits.slice(0, 3).map((hit, i) => (
                          <li key={i}>• {hit.matched_entity} ({hit.list_type})</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Action Button */}
                  <div className="flex gap-2">
                    {generated[candidate.case_id] ? (
                      <div className="flex items-center gap-2 flex-1 px-4 py-3 rounded-lg bg-success-50 dark:bg-success-900 border border-success-200 dark:border-success-700">
                        <CheckCircle className="w-5 h-5 text-success-600 dark:text-success-400" />
                        <div>
                          <p className="text-sm font-semibold text-success-900 dark:text-success-100">SAR Generated</p>
                          <p className="text-xs text-success-700 dark:text-success-300">{generated[candidate.case_id]}</p>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => handleGenerateSAR(candidate.case_id)}
                        disabled={generating[candidate.case_id]}
                        className="btn-primary flex items-center gap-2 flex-1 justify-center disabled:opacity-50"
                      >
                        {generating[candidate.case_id] ? (
                          <>
                            <Loader className="w-4 h-4 animate-spin" />
                            Generating...
                          </>
                        ) : (
                          <>
                            <Download className="w-4 h-4" />
                            Generate SAR Report
                          </>
                        )}
                      </button>
                    )}
                  </div>

                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
                    Recommendation: <strong>{candidate.recommendation || 'Monitor'}</strong>
                  </p>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="card text-center py-12">
            <FileText className="w-12 h-12 text-gray-400 dark:text-gray-600 mx-auto mb-3 opacity-50" />
            <p className="text-gray-600 dark:text-gray-400 font-medium">No SAR candidates at this time</p>
            <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">Run the AML pipeline to generate escalated cases</p>
          </div>
        )}
      </div>
    </div>
  )
}
