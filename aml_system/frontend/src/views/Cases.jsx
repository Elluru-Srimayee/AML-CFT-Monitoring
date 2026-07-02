import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchCasesList } from '../api'
import { FileText, Filter } from 'lucide-react'

export default function Cases() {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [limit] = useState(50)
  const [total, setTotal] = useState(0)
  const [riskTierFilter, setRiskTierFilter] = useState('')
  const [stats, setStats] = useState({})

  async function loadCases() {
    setLoading(true)
    try {
      const data = await fetchCasesList(offset, limit, riskTierFilter)
      setCases(data.cases || [])
      setTotal(data.total || 0)
      setStats(data.by_tier || {})
    } catch (error) {
      console.error('Failed to load cases:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCases()
  }, [offset, limit, riskTierFilter])

  const navigate = useNavigate()

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

  const startItem = total === 0 ? 0 : offset + 1
  const endItem = Math.min(offset + limit, total)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card">
        <h2 className="text-2xl font-bold flex items-center gap-2 mb-4">
          <FileText className="w-6 h-6 text-danger-600 dark:text-danger-400" />
          Cases Management
        </h2>
        <p className="text-gray-600 dark:text-gray-400">Review and manage investigation cases</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-gray-600 dark:text-gray-400 text-sm">Total Cases</p>
          <p className="text-2xl font-bold text-primary-600 dark:text-primary-400">{total}</p>
        </div>
        {Object.entries(stats).map(([tier, count]) => (
          <div key={tier} className="card">
            <p className="text-gray-600 dark:text-gray-400 text-sm">{tier}</p>
            <p className="text-2xl font-bold">{count}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="card">
        <div className="flex flex-col sm:flex-row gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-2 flex items-center gap-2">
              <Filter className="w-4 h-4" />
              Filter by Risk Tier
            </label>
            <select
              value={riskTierFilter}
              onChange={(e) => {
                setRiskTierFilter(e.target.value)
                setOffset(0)
              }}
              className="input-field"
            >
              <option value="">All Tiers</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </div>
          <button
            onClick={() => {
              setRiskTierFilter('')
              setOffset(0)
            }}
            className="btn-secondary"
          >
            Clear Filters
          </button>
        </div>
      </div>

      {/* Cases Table */}
      <div className="card overflow-x-auto">
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          </div>
        ) : cases.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="border-b-2 border-gray-200 dark:border-gray-700">
                <th className="text-left">Case ID</th>
                <th className="text-left">Risk Tier</th>
                <th className="text-left">Status</th>
                <th className="text-left">Account</th>
                <th className="text-left">Risk Score</th>
                <th className="text-left">Txn Count</th>
                <th className="text-left">Amount (USD)</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr
                  key={c.case_id}
                  className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                  onClick={() => navigate(`/cases/${c.case_id}`)}
                >
                  <td className="font-semibold text-primary-600 dark:text-primary-400">{c.case_id}</td>
                  <td>
                    <span className={`badge ${getRiskBadgeColor(c.risk_tier)}`}>
                      {c.risk_tier}
                    </span>
                  </td>
                  <td className="font-medium">{c.status}</td>
                  <td className="text-sm font-mono">{c.subject_account}</td>
                  <td className="text-sm font-medium">{c.risk_score}</td>
                  <td className="text-sm">{c.transaction_count}</td>
                  <td className="text-sm">${Number(c.total_amount || 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            No cases found
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="card flex flex-col sm:flex-row justify-between items-center gap-3">
          <span className="text-sm text-gray-600 dark:text-gray-400">
            Showing {total === 0 ? 0 : startItem}-{endItem} of {total} cases
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="btn-secondary disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={offset + limit >= total}
              className="btn-secondary disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
