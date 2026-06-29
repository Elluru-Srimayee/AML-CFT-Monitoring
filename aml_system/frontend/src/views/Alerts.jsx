import React, { useEffect, useState } from 'react'
import { fetchAlerts } from '../api'
import { AlertCircle, Filter, ChevronDown } from 'lucide-react'

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState(50)
  const [total, setTotal] = useState(0)
  const [riskTierFilter, setRiskTierFilter] = useState('')
  const [stats, setStats] = useState({})

  async function loadAlerts() {
    setLoading(true)
    try {
      const data = await fetchAlerts(offset, limit, riskTierFilter)
      if (data.alerts) {
        setAlerts(data.alerts)
        setTotal(data.total || data.alerts.length)
        setStats(data.by_tier || {})
      }
    } catch (error) {
      console.error('Failed to load alerts:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAlerts()
  }, [offset, limit, riskTierFilter])

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

  const filteredAlerts = alerts

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card">
        <h2 className="text-2xl font-bold flex items-center gap-2 mb-4">
          <AlertCircle className="w-6 h-6 text-warning-600 dark:text-warning-400" />
          Alerts Management
        </h2>
        <p className="text-gray-600 dark:text-gray-400">Review and manage all generated AML alerts</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-gray-600 dark:text-gray-400 text-sm">Total Alerts</p>
          <p className="text-2xl font-bold text-primary-600 dark:text-primary-400">{total}</p>
        </div>
        {Object.entries(stats).map(([tier, count]) => (
          <div key={tier} className="card">
            <p className="text-gray-600 dark:text-gray-400 text-sm">{tier}</p>
            <p className={`text-2xl font-bold ${getRiskTextColor(tier)}`}>{count}</p>
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
              onChange={(e) => setRiskTierFilter(e.target.value)}
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
            onClick={() => setRiskTierFilter('')}
            className="btn-secondary"
          >
            Clear Filters
          </button>
        </div>
      </div>

      {/* Alerts Table */}
      <div className="card overflow-x-auto">
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          </div>
        ) : filteredAlerts.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="border-b-2 border-gray-200 dark:border-gray-700">
                <th className="text-left">Alert ID</th>
                <th className="text-left">Risk Tier</th>
                <th className="text-left">Score</th>
                <th className="text-left">Sender Account</th>
                <th className="text-left">Amount (USD)</th>
                <th className="text-left">Timestamp</th>
                <th className="text-left">Rules Triggered</th>
              </tr>
            </thead>
            <tbody>
              {filteredAlerts.slice(0, limit).map((alert) => (
                <tr key={alert.alert_id} className="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                  <td className="font-semibold text-primary-600 dark:text-primary-400">{alert.alert_id}</td>
                  <td>
                    <span className={`badge ${getRiskBadgeColor(alert.risk_tier)}`}>
                      {alert.risk_tier}
                    </span>
                  </td>
                  <td className="font-medium">{alert.risk_score}</td>
                  <td className="text-sm">{alert.sender_account}</td>
                  <td className="text-sm">${Number(alert.amount || 0).toLocaleString()}</td>
                  <td className="text-sm text-gray-600 dark:text-gray-400">{new Date(alert.timestamp).toLocaleDateString()}</td>
                  <td className="text-xs text-gray-500 dark:text-gray-500">{alert.triggered_rules || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            No alerts found
          </div>
        )}
      </div>

      {/* Pagination */}
      {filteredAlerts.length > limit && (
        <div className="card flex justify-between items-center">
          <span className="text-sm text-gray-600 dark:text-gray-400">
            Showing {Math.min(limit, filteredAlerts.length)} of {filteredAlerts.length} alerts
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
              disabled={offset + limit >= filteredAlerts.length}
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
