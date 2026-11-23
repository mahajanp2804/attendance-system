import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import api from '../../hooks/api'
import useAuthStore from '../../store/authStore'

export default function StudentDashboard() {
  const { user } = useAuthStore()
  const [summary, setSummary]     = useState([])
  const [todaySlots, setToday]    = useState([])
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/api/attendance/summary'),
      api.get('/api/timetable/today'),
    ]).then(([s, t]) => {
      setSummary(s.data)
      setToday(t.data)
    }).finally(() => setLoading(false))
  }, [])

  const lowCount = summary.filter(s => s.is_low).length
  const held = summary.filter(s => s.total_classes > 0)   // subjects that have had classes
  const overallPct = held.length
    ? Math.round(held.reduce((a, s) => a + s.percentage, 0) / held.length)
    : null

  if (loading) return <PageSkeleton />

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      {/* Greeting */}
      <div>
        <h1 className="text-xl font-bold text-text-primary">
          Hello, {user?.name?.split(' ')[0]} 👋
        </h1>
        <p className="text-text-secondary text-sm mt-0.5">Here's your attendance overview</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card text-center">
          <p className="text-3xl font-bold text-primary">{overallPct ?? '—'}%</p>
          <p className="text-xs text-text-muted mt-1">Overall attendance</p>
        </div>
        <div className={`card text-center ${lowCount > 0 ? 'border-warning bg-yellow-50' : ''}`}>
          <p className={`text-3xl font-bold ${lowCount > 0 ? 'text-warning' : 'text-success'}`}>
            {lowCount}
          </p>
          <p className="text-xs text-text-muted mt-1">
            {lowCount > 0 ? 'Subjects below 75%' : 'All subjects OK ✓'}
          </p>
        </div>
      </div>

      {/* Low attendance warning */}
      {lowCount > 0 && (
        <div className="rounded-xl bg-yellow-50 border border-yellow-200 px-4 py-3 flex gap-3">
          <svg className="w-5 h-5 text-warning shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-yellow-800">Low attendance warning</p>
            <p className="text-xs text-yellow-700 mt-0.5">
              You have {lowCount} subject{lowCount > 1 ? 's' : ''} below 75%.{' '}
              <Link to="/student/attendance" className="underline font-medium">View details</Link>
            </p>
          </div>
        </div>
      )}

      {/* Chart */}
      {summary.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-text-primary mb-4">Attendance by subject</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={summary} margin={{ left: -20 }}>
              <XAxis dataKey="subject_code" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
              <Tooltip formatter={v => [`${v}%`, 'Attendance']} />
              <Bar dataKey="percentage" radius={[4, 4, 0, 0]}>
                {summary.map((s, i) => (
                  <Cell key={i} fill={s.is_low ? '#D97706' : '#1D4ED8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-text-muted text-center mt-1">
            <span className="inline-block w-2 h-2 rounded-sm bg-primary mr-1" />OK
            <span className="inline-block w-2 h-2 rounded-sm bg-warning mx-1 ml-3" />Below 75%
          </p>
        </div>
      )}

      {/* Today's classes */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">Today's classes</h2>
        {todaySlots.length === 0 ? (
          <p className="text-sm text-text-muted py-4 text-center">No classes today 🎉</p>
        ) : (
          <div className="space-y-2">
            {todaySlots.map(slot => (
              <div key={slot.id} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                <div>
                  <p className="text-sm font-medium text-text-primary">{slot.subject_name}</p>
                  <p className="text-xs text-text-muted">{slot.room} · {slot.professor_name}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-text-secondary">{slot.start_time}</p>
                  <p className="text-xs text-text-muted">– {slot.end_time}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-4 max-w-2xl mx-auto animate-pulse">
      <div className="h-6 bg-slate-200 rounded w-48" />
      <div className="grid grid-cols-2 gap-3">
        <div className="card h-20 bg-slate-100" />
        <div className="card h-20 bg-slate-100" />
      </div>
      <div className="card h-48 bg-slate-100" />
      <div className="card h-32 bg-slate-100" />
    </div>
  )
}
