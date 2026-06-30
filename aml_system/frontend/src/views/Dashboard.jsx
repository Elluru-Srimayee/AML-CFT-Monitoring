import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bar } from 'react-chartjs-2'
import { fetchSummary, runPipeline } from '../api'
import { Play, TrendingUp, AlertTriangle, FileText, Loader } from 'lucide-react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

export default function Dashboard({ dashboardState, onDashboardStateChange }) {
  const [summary, setSummary] = useState(dashboardState?.summary || null)
  const [sampleInput, setSampleInput] = useState(dashboardState?.sampleInput || '1000')
  const [status, setStatus] = useState(dashboardState?.status || 'Ready')
  const [runResult, setRunResult] = useState(dashboardState?.runResult || null)
  const [loading, setLoading] = useState(false)
  const [alertsVisible, setAlertsVisible] = useState(8)
  const [casesVisible, setCasesVisible] = useState(8)
  const alertsListRef = useRef(null)
  const casesListRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (dashboardState?.summary) {
      setSummary(dashboardState.summary)
      setRunResult(dashboardState.runResult || null)
      setStatus(dashboardState.status || 'Ready')
      setSampleInput(dashboardState.sampleInput || '1000')
      return
    }

    fetchSummary(100).then(d => setSummary(d.summary)).catch(() => {})
  }, [dashboardState])

  function persistState(nextSummary, nextRunResult, nextStatus, nextSampleInput) {
    const nextState = {
      summary: nextSummary,
      runResult: nextRunResult,
      status: nextStatus,
      sampleInput: nextSampleInput,
    }
    setSummary(nextSummary)
    setRunResult(nextRunResult)
    setStatus(nextStatus)
    setSampleInput(nextSampleInput)
    onDashboardStateChange?.(nextState)
  }

  const byTier = summary?.rule_summary || {}
  const tiers = Object.keys(byTier).sort()
  const counts = tiers.map(t => byTier[t])

  const barData = {
    labels: tiers,
    datasets: [
      {
        label: 'Transactions Flagged',
        data: counts,
        backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#22c55e'],
        borderRadius: 8,
        borderSkipped: false,
      },
    ],
  }

  async function handleRun() {
    const sample = Number(sampleInput)
    if (!sample || sample <= 0) {
      setStatus('Please enter a valid positive number of transactions')
      return
    }

    setLoading(true)
    setStatus(`Running AML pipeline for ${sample} transactions...`)
    try {
      const data = await runPipeline(sample, 200, 200)
      persistState(data.summary, data, `Completed for ${sample} transactions`, String(sample))
    } catch (error) {
      persistState(summary, runResult, 'Pipeline failed. Check backend logs.', String(sample))
    } finally {
      setLoading(false)
    }
  }

  const alerts = runResult?.alerts || []
  const cases = runResult?.cases || []
  const visibleAlerts = alerts.slice(0, alertsVisible)
  const visibleCases = cases.slice(0, casesVisible)

  useEffect(() => {
    setAlertsVisible(8)
    setCasesVisible(8)
  }, [runResult])

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

  const handleAlertsScroll = (event) => {
    const { scrollTop, clientHeight, scrollHeight } = event.currentTarget
    if (scrollTop + clientHeight >= scrollHeight - 24) {
      setAlertsVisible((value) => Math.min(value + 8, alerts.length))
    }
  }

  const handleCasesScroll = (event) => {
    const { scrollTop, clientHeight, scrollHeight } = event.currentTarget
    if (scrollTop + clientHeight >= scrollHeight - 24) {
      setCasesVisible((value) => Math.min(value + 8, cases.length))
    }
  }

  return (
    <div className="space-y-8">
      {/* Pipeline Control Section */}
      <div className="card">
        <div className="mb-6">
          <h2 className="text-2xl font-bold mb-2 flex items-center gap-2">
            <TrendingUp className="w-6 h-6 text-primary-600 dark:text-primary-400" />
            AML Pipeline Execution
          </h2>
          <p className="text-gray-600 dark:text-gray-400">Run the AML pipeline on a sample of transactions</p>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium mb-2">Number of Transactions</label>
            <input
              type="number"
              min="1"
              value={sampleInput}
              onChange={(e) => setSampleInput(e.target.value)}
              className="input-field"
              placeholder="Enter number of transactions"
            />
          </div>
          <button
            onClick={handleRun}
            disabled={loading}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader className="w-4 h-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Run Pipeline
              </>
            )}
          </button>
        </div>

        <div className={`mt-4 p-4 rounded-lg flex items-center gap-2 ${
          status.includes('failed') 
            ? 'bg-danger-50 dark:bg-danger-900 text-danger-700 dark:text-danger-200'
            : 'bg-primary-50 dark:bg-primary-900 text-primary-700 dark:text-primary-200'
        }`}>
          <div className="w-2 h-2 rounded-full bg-current" />
          {status}
        </div>
      </div>

      {/* Results Section */}
      {runResult && (
        <>
          {/* Summary Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-600 dark:text-gray-400 text-sm">Transactions Processed</p>
                  <p className="text-3xl font-bold text-primary-600 dark:text-primary-400">{runResult.summary?.rows}</p>
                </div>
                <TrendingUp className="w-8 h-8 text-primary-600 dark:text-primary-400 opacity-20" />
              </div>
            </div>

            <div className="card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-600 dark:text-gray-400 text-sm">Alerts Generated</p>
                  <p className="text-3xl font-bold text-warning-600 dark:text-warning-400">{runResult.summary?.alerts}</p>
                </div>
                <AlertTriangle className="w-8 h-8 text-warning-600 dark:text-warning-400 opacity-20" />
              </div>
            </div>

            <div className="card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-600 dark:text-gray-400 text-sm">Cases Created</p>
                  <p className="text-3xl font-bold text-danger-600 dark:text-danger-400">{runResult.summary?.cases}</p>
                </div>
                <FileText className="w-8 h-8 text-danger-600 dark:text-danger-400 opacity-20" />
              </div>
            </div>

            <div className="card">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-600 dark:text-gray-400 text-sm">Rules Triggered</p>
                  <p className="text-3xl font-bold text-blue-600 dark:text-blue-400">{Object.keys(runResult.summary?.rule_summary || {}).length}</p>
                </div>
                <TrendingUp className="w-8 h-8 text-blue-600 dark:text-blue-400 opacity-20" />
              </div>
            </div>
          </div>

          {/* Charts and Details Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Chart */}
            <div className="lg:col-span-2 card">
              <h3 className="text-xl font-bold mb-6">Rule Triggers Distribution</h3>
              {tiers.length > 0 ? (
                <div className="relative h-72">
                  <Bar
                    data={barData}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                        legend: {
                          display: false,
                        },
                      },
                      scales: {
                        y: {
                          beginAtZero: true,
                        },
                      },
                    }}
                  />
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500 dark:text-gray-400">No trigger data</div>
              )}
            </div>

            {/* Alert Count by Tier */}
            <div className="card">
              <h3 className="text-xl font-bold mb-4">Breakdown</h3>
              <div className="space-y-3">
                {Object.entries(runResult.summary?.rule_summary || {}).map(([rule, count]) => (
                  <div key={rule} className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                    <span className="font-medium text-sm">{rule}</span>
                    <span className="badge bg-primary-100 dark:bg-primary-900 text-primary-700 dark:text-primary-200">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Alerts and Cases Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Recent Alerts */}
            <div className="card">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-warning-600 dark:text-warning-400" />
                Recent Alerts ({alerts.length})
              </h3>
              {alerts.length > 0 ? (
                <div
                  ref={alertsListRef}
                  onScroll={handleAlertsScroll}
                  className="space-y-3 max-h-96 overflow-y-auto"
                >
                  {visibleAlerts.map((alert) => (
                    <div
                    key={alert.alert_id}
                    className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                    onClick={() => navigate(`/alerts/${alert.alert_id}`)}
                  >
                      <div className="flex justify-between items-start gap-2 mb-2">
                        <span className="font-semibold text-sm truncate">{alert.alert_id}</span>
                        <span className={`badge ${getRiskBadgeColor(alert.risk_tier)}`}>{alert.risk_tier}</span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        <strong>Sender:</strong> {alert.sender_account}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        <strong>Score:</strong> {alert.risk_score}
                      </p>
                      {alert.triggered_rules && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1 truncate">
                          Rules: {alert.triggered_rules}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">No alerts in this run</div>
              )}
            </div>

            {/* Generated Cases */}
            <div className="card">
              <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
                <FileText className="w-5 h-5 text-danger-600 dark:text-danger-400" />
                Generated Cases ({cases.length})
              </h3>
              {cases.length > 0 ? (
                <div
                  ref={casesListRef}
                  onScroll={handleCasesScroll}
                  className="space-y-3 max-h-96 overflow-y-auto"
                >
                  {visibleCases.map((caseItem) => (
                    <div
                      key={caseItem.case_id}
                      className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                      onClick={() => navigate(`/cases/${caseItem.case_id}`)}
                    >
                      <div className="flex justify-between items-start gap-2 mb-2">
                        <span className="font-semibold text-sm truncate">{caseItem.case_id}</span>
                        <span className={`badge ${getRiskBadgeColor(caseItem.risk_tier)}`}>{caseItem.status}</span>
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        <strong>Account:</strong> {caseItem.subject_account}
                      </p>
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        <strong>Recommendation:</strong> {caseItem.recommendation || 'Monitor'}
                      </p>
                      {caseItem.pattern_findings && caseItem.pattern_findings.length > 0 && (
                        <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                          Patterns: {caseItem.pattern_findings.length} finding(s)
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">No cases in this run</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
