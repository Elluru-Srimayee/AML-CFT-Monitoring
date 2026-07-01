import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { FileText, ArrowLeft, AlertTriangle, Loader, RefreshCw } from 'lucide-react'
import { fetchSARDetail } from '../api'

const SAR_DETAIL_CACHE_PREFIX = 'aml_sar_detail_'

export default function SARDetail() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const [sar, setSar] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isCached, setIsCached] = useState(false)

  useEffect(() => {
    async function loadSAR(forceRefresh = false) {
      setLoading(true)
      setError('')
      try {
        // Try to get from cache first if not forcing refresh
        if (!forceRefresh) {
          const cacheKey = `${SAR_DETAIL_CACHE_PREFIX}${caseId}`
          const cached = localStorage.getItem(cacheKey)
          if (cached) {
            setSar(JSON.parse(cached))
            setIsCached(true)
            setLoading(false)
            return
          }
        }

        // Fetch from API
        const data = await fetchSARDetail(caseId)
        if (data.sar) {
          setSar(data.sar)
          setIsCached(false)
          // Save to cache
          const cacheKey = `${SAR_DETAIL_CACHE_PREFIX}${caseId}`
          localStorage.setItem(cacheKey, JSON.stringify(data.sar))
        } else {
          setError('SAR report not found')
        }
      } catch (err) {
        setError(`Failed to load SAR: ${err.message}`)
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    loadSAR()
  }, [caseId])

  function refreshData() {
    const cacheKey = `${SAR_DETAIL_CACHE_PREFIX}${caseId}`
    localStorage.removeItem(cacheKey)
    setIsCached(false)
    // Trigger reload by resetting state and fetching
    setSar(null)
    setLoading(true)
    setError('')
    
    async function reload() {
      try {
        const data = await fetchSARDetail(caseId)
        if (data.sar) {
          setSar(data.sar)
          localStorage.setItem(cacheKey, JSON.stringify(data.sar))
        } else {
          setError('SAR report not found')
        }
      } catch (err) {
        setError(`Failed to load SAR: ${err.message}`)
      } finally {
        setLoading(false)
      }
    }
    reload()
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="card text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
          <p className="text-gray-600 dark:text-gray-400 mt-2">Loading SAR Report...</p>
        </div>
      </div>
    )
  }

  if (error || !sar) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <div className="card bg-danger-50 dark:bg-danger-900 border border-danger-200 dark:border-danger-700">
          <div className="flex gap-3">
            <AlertTriangle className="w-5 h-5 text-danger-600 dark:text-danger-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-danger-900 dark:text-danger-100">{error || 'SAR report not found'}</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const getRiskBadgeColor = (tier) => {
    switch (tier) {
      case 'CRITICAL':
        return 'bg-danger-100 dark:bg-danger-900 text-danger-900 dark:text-danger-100 border border-danger-300 dark:border-danger-700'
      case 'HIGH':
        return 'bg-warning-100 dark:bg-warning-900 text-warning-900 dark:text-warning-100 border border-warning-300 dark:border-warning-700'
      case 'MEDIUM':
        return 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100 border border-blue-300 dark:border-blue-700'
      default:
        return 'bg-success-100 dark:bg-success-900 text-success-900 dark:text-success-100 border border-success-300 dark:border-success-700'
    }
  }

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to SAR Reports
      </button>

      {/* Header */}
      <div className="card">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <h1 className="text-3xl font-bold flex items-center gap-2 mb-2">
              <FileText className="w-8 h-8 text-primary-600 dark:text-primary-400" />
              {sar.sar_id}
            </h1>
            <p className="text-gray-600 dark:text-gray-400">Suspicious Activity Report (SAR)</p>
            {isCached && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                ✓ Data cached from local storage
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={refreshData}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 text-gray-900 dark:text-gray-100 font-semibold text-sm"
              title="Refresh data from server"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <div className={`px-4 py-2 rounded-lg font-semibold ${getRiskBadgeColor(sar.risk_tier)}`}>
              {sar.risk_tier} Risk
            </div>
          </div>
        </div>
      </div>

      {/* Filing Information */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Filing Details</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Filing Date</p>
              <p className="font-semibold">{sar.filing_date}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Report Type</p>
              <p className="font-semibold">{sar.report_type}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Case ID</p>
              <p className="font-mono font-semibold">{sar.case_id}</p>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Filing Institution</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Institution</p>
              <p className="font-semibold">{sar.filing_institution}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Address</p>
              <p className="text-sm">{sar.filing_institution_address}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">TIN</p>
              <p className="font-mono">{sar.filing_institution_tin}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Contact Information */}
      <div className="card">
        <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Contact Information</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Name</p>
            <p className="font-semibold">{sar.contact_name}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Phone</p>
            <p className="font-mono">{sar.contact_phone}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Email</p>
            <p className="font-mono text-sm">{sar.contact_email}</p>
          </div>
        </div>
      </div>

      {/* Subject Account */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Subject Account</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Account</p>
              <p className="font-mono font-semibold text-lg">{sar.subject_account}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Bank Location</p>
              <p className="font-semibold">{sar.subject_bank}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Geographic Location</p>
              <p className="font-semibold">{sar.subject_location}</p>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Risk Assessment</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Risk Tier</p>
              <p className={`text-2xl font-bold ${sar.risk_tier === 'CRITICAL' ? 'text-danger-600 dark:text-danger-400' : 'text-warning-600 dark:text-warning-400'}`}>
                {sar.risk_tier}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Risk Score</p>
              <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{sar.risk_score}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Activity Details */}
      <div className="card">
        <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Activity Details</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Activity Type</p>
            <p className="font-semibold text-sm">{sar.activity_type}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Transaction Date Range</p>
            <p className="font-semibold text-sm">{sar.transaction_date_start} to {sar.transaction_date_end}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Total Transactions</p>
            <p className="text-2xl font-bold">{sar.total_transactions}</p>
          </div>
        </div>
      </div>

      {/* Transaction Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Transaction Summary</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Total Amount</p>
              <p className="text-2xl font-bold">{sar.total_amount}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Countries Involved</p>
              <p className="font-semibold">{sar.countries_involved}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Payment Types</p>
              <p className="text-sm">{sar.payment_types}</p>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Rules & Sanctions</h3>
          <div className="space-y-3">
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Triggered Rules</p>
              <p className="font-semibold">{sar.triggered_rules}</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 dark:text-gray-400">Sanctions Match</p>
              <p className={`font-semibold ${sar.sanctions_hits === 'No watchlist matches identified' ? 'text-success-600 dark:text-success-400' : 'text-danger-600 dark:text-danger-400'}`}>
                {sar.sanctions_hits}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Narrative */}
      <div className="card">
        <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Investigation Narrative</h3>
        <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
          <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
            {sar.narrative}
          </p>
        </div>
      </div>

      {/* Investigator Information */}
      <div className="card">
        <h3 className="text-lg font-bold mb-4 text-primary-600 dark:text-primary-400">Investigator Information</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Name</p>
            <p className="font-semibold">{sar.investigator_name}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Title</p>
            <p className="font-semibold">{sar.investigator_title}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Date</p>
            <p className="font-semibold">{sar.investigator_date}</p>
          </div>
        </div>
      </div>

      {/* Footer with Action Buttons */}
      <div className="card bg-gray-50 dark:bg-gray-800">
        <div className="flex gap-3 justify-between">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 font-semibold"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-600 hover:bg-primary-700 text-white font-semibold"
          >
            Print / Save as PDF
          </button>
        </div>
      </div>
    </div>
  )
}
