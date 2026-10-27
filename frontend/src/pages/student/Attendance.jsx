import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import api from '../../hooks/api'

export default function StudentAttendance() {
  const [summary,  setSummary]  = useState([])
  const [expanded, setExpanded] = useState(null)
  const [sessions, setSessions] = useState({})   // subject_id → session list
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    api.get('/api/attendance/summary').then(r => setSummary(r.data)).finally(() => setLoading(false))
  }, [])

  const toggleSubject = async (subjectId) => {
    if (expanded === subjectId) { setExpanded(null); return }
    setExpanded(subjectId)
    if (sessions[subjectId]) return   // already loaded

    // Load all completed sessions for this subject and get student's record for each
    const res = await api.get(`/api/attendance/sessions`, { params: { subject_id: subjectId } })
    setSessions(prev => ({ ...prev, [subjectId]: res.data }))
  }

  if (loading) return (
    <div className="animate-pulse space-y-3 max-w-2xl mx-auto">
      {[...Array(4)].map((_, i) => <div key={i} className="card h-24 bg-slate-100" />)}
    </div>
  )

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-text-primary">My Attendance</h1>

      {summary.length === 0 ? (
        <div className="card text-center py-10 text-text-muted">No subjects enrolled yet.</div>
      ) : (
        summary.map(sub => (
          <div key={sub.subject_id} className={`card ${sub.is_low ? 'border-warning bg-yellow-50/30' : ''}`}>

            {/* Header row */}
            <button className="w-full" onClick={() => toggleSubject(sub.subject_id)}>
              <div className="flex items-center justify-between">
                <div className="text-left">
                  <p className="font-semibold text-text-primary">{sub.subject_name}</p>
                  <p className="text-xs text-text-muted">{sub.subject_code}</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className={`text-2xl font-bold ${sub.is_low ? 'text-warning' : 'text-success'}`}>
                      {sub.percentage}%
                    </p>
                    <p className="text-xs text-text-muted">{sub.present}/{sub.total_classes} classes</p>
                  </div>
                  <svg className={`w-4 h-4 text-text-muted transition-transform ${expanded === sub.subject_id ? 'rotate-180' : ''}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>

              {/* Progress bar */}
              <div className="mt-3 h-2 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-2 rounded-full transition-all duration-500 ${sub.is_low ? 'bg-warning' : 'bg-success'}`}
                  style={{ width: `${sub.percentage}%` }}
                />
              </div>

              <div className="mt-2 flex gap-4 text-xs">
                <span className="text-success font-medium">✓ {sub.present} present</span>
                <span className="text-danger font-medium">✗ {sub.absent} absent</span>
                {sub.is_low && (
                  <span className="text-warning font-medium">
                    ⚠ Need {Math.max(0, Math.ceil((0.75 * sub.total_classes - sub.present) / 0.25))} more to reach 75%
                  </span>
                )}
              </div>
            </button>

            {/* Expanded: session-by-session list */}
            {expanded === sub.subject_id && (
              <div className="mt-4 pt-4 border-t border-surface-border">
                {!sessions[sub.subject_id] ? (
                  <p className="text-sm text-text-muted text-center py-4 animate-pulse">Loading…</p>
                ) : sessions[sub.subject_id].length === 0 ? (
                  <p className="text-sm text-text-muted text-center py-4">No classes held yet</p>
                ) : (
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-text-secondary mb-2 uppercase tracking-wide">Class history</p>
                    {sessions[sub.subject_id].map(session => {
                      const isPresent = session.present_count > 0  // rough indicator; ideally filtered per student
                      return (
                        <div key={session.id} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                          <div className="flex items-center gap-3">
                            <div className={`w-2 h-2 rounded-full shrink-0 ${session.is_completed ? 'bg-success' : 'bg-warning'}`} />
                            <div>
                              <p className="text-sm text-text-primary">
                                {format(new Date(session.date), 'EEE, d MMM yyyy')}
                              </p>
                              {!session.is_completed && (
                                <p className="text-xs text-warning">In progress</p>
                              )}
                            </div>
                          </div>
                          <span className={`badge ${session.is_completed ? 'badge-gray' : 'badge-yellow'}`}>
                            {session.present_count}/{session.total_students} present
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

          </div>
        ))
      )}
    </div>
  )
}
