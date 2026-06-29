import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './views/Dashboard'
import Alerts from './views/Alerts'
import SAR from './views/SAR'
import CaseView from './views/CaseView'
import { BarChart3, AlertCircle, FileText } from 'lucide-react'

const DASHBOARD_STATE_KEY = 'aml_dashboard_state'

function readStoredDashboardState() {
  try {
    const item = window.localStorage.getItem(DASHBOARD_STATE_KEY)
    return item ? JSON.parse(item) : null
  } catch {
    return null
  }
}

function Navigation() {
  const location = useLocation()
  const links = [
    { to: '/', label: 'Dashboard', icon: BarChart3 },
    { to: '/alerts', label: 'Alerts', icon: AlertCircle },
    { to: '/sar', label: 'SAR Reports', icon: FileText },
  ]

  return (
    <nav className="app-navbar">
      <div className="navbar-container">
        <div className="navbar-brand">
          <BarChart3 className="brand-icon" />
          <span className="brand-text">AML CFT System</span>
        </div>
        <div className="navbar-menu">
          {links.map((item) => {
            const isActive = location.pathname === item.to
            const Icon = item.icon
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`nav-tab ${isActive ? 'nav-tab-active' : 'nav-tab-inactive'}`}
              >
                <Icon className="tab-icon" />
                <span>{item.label}</span>
              </Link>
            )
          })}
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  const [dashboardState, setDashboardState] = useState(readStoredDashboardState)

  useEffect(() => {
    window.localStorage.setItem(DASHBOARD_STATE_KEY, JSON.stringify(dashboardState))
  }, [dashboardState])

  return (
    <BrowserRouter>
      <div className="app-shell">
        <Navigation />
        <main className="app-main">
          <div className="app-container">
            <Routes>
              <Route
                path="/"
                element={
                  <Dashboard
                    dashboardState={dashboardState}
                    onDashboardStateChange={setDashboardState}
                  />
                }
              />
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/sar" element={<SAR />} />
              <Route path="/cases/:caseId" element={<CaseView />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
