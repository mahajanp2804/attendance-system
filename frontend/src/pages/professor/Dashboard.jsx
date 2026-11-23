import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../hooks/api'
import useAuthStore from '../../store/authStore'

export default function ProfDashboard() {
  const { user }  = useAuthStore()
  // First name for the greeting, skipping titles like "Dr." or "Prof."
  const firstName = (user?.name || '').split(' ').find(w => !/^(dr|prof|mr|mrs|ms)\.?$/i.test(w)) || ''
  const [today,   setToday]   = useState([])
  const [low,     setLow]     = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/api/timetable/today'),
      api.get('/api/attendance/low-attendance'),
    ]).then(([t, l]) => {
      setToday(t.data)
      setLow(l.data.slice(0, 5))
    }).finally(() => setLoading(false))
  }, [])

  // Download through the API client so the request carries the login token
  const exportCSV = async () => {
    try {
      const res = await api.get('/api/attendance/export', { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
      const a   = document.createElement('a')
      a.href    = url
      a.download = `attendance_${new Date().toISOString().split('T')[0]}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('Export failed. Please try again.')
    }
  }

  if (loading) return <div className="animate-pulse space-y-4 max-w-2xl mx-auto">{[...Array(3)].map((_,i) => <div key={i} className="card h-24 bg-slate-100" />)}</div>

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Welcome, {firstName}</h1>
        <p className="text-text-secondary text-sm mt-0.5">Professor dashboard</p>
      </div>

      {/* Today's classes */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-text-primary">Today's classes</h2>
          <Link to="/professor/scanner" className="text-xs text-primary font-medium">Start scan →</Link>
        </div>
        {today.length === 0 ? (
          <p className="text-sm text-text-muted py-4 text-center">No classes scheduled today</p>
        ) : (
          <div className="space-y-2">
            {today.map(slot => (
              <div key={slot.id} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                <div>
                  <p className="text-sm font-medium text-text-primary">{slot.subject_name}</p>
                  <p className="text-xs text-text-muted">{slot.subject_code} · {slot.room}</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className="text-sm font-medium text-text-secondary">{slot.start_time}</p>
                    <p className="text-xs text-text-muted">– {slot.end_time}</p>
                  </div>
                  <Link
                    to="/professor/scanner"
                    state={{ slotId: slot.id, subjectName: slot.subject_name }}
                    className="btn-primary text-xs px-3 py-1.5"
                  >
                    Scan
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Low attendance students */}
      {low.length > 0 && (
        <div className="card border-warning">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-text-primary">⚠ Low attendance students</h2>
            <Link to="/professor/attendance" className="text-xs text-primary font-medium">View all →</Link>
          </div>
          <div className="space-y-2">
            {low.map((item, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                <div>
                  <p className="text-sm font-medium text-text-primary">{item.student_name}</p>
                  <p className="text-xs text-text-muted">{item.roll_number} · {item.subject_name}</p>
                </div>
                <span className="badge badge-yellow">{item.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick links */}
      <div className="grid grid-cols-2 gap-3">
        <Link to="/professor/students" className="card hover:border-primary transition-colors text-center py-5">
          <svg className="w-6 h-6 mx-auto text-primary mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
          </svg>
          <p className="text-sm font-medium text-text-primary">Enroll Student</p>
        </Link>
        <button
          type="button"
          onClick={exportCSV}
          className="card hover:border-primary transition-colors text-center py-5 block w-full"
        >
          <svg className="w-6 h-6 mx-auto text-primary mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-sm font-medium text-text-primary">Export CSV</p>
        </button>
      </div>
    </div>
  )
}
