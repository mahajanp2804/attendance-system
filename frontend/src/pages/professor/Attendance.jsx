import { useEffect, useState } from 'react'
import api from '../../hooks/api'
import SemesterPicker from '../../components/SemesterPicker'

export default function ProfAttendance() {
  const [sessions,    setSessions]    = useState([])
  const [expanded,    setExpanded]    = useState(null)
  const [records,     setRecords]     = useState([])
  const [loading,     setLoading]     = useState(true)
  const [override,    setOverride]    = useState(null)
  const [semesterId,  setSemesterId]  = useState('')
  const [fromDate,    setFromDate]    = useState('')
  const [toDate,      setToDate]      = useState('')

  const load = (semId = semesterId, from = fromDate, to = toDate) => {
    setLoading(true)
    const params = {}
    if (semId) params.semester_id = semId
    if (from)  params.from_date   = from
    if (to)    params.to_date     = to
    api.get('/api/attendance/sessions', { params })
      .then(r => setSessions(r.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const loadRecords = async (sessionId) => {
    if (expanded === sessionId) { setExpanded(null); return }
    setExpanded(sessionId)
    const res = await api.get(`/api/attendance/sessions/${sessionId}/records`)
    setRecords(res.data)
  }

  const submitOverride = async () => {
    if (!override) return
    await api.patch(`/api/attendance/records/${override.record.id}`, {
      status: override.newStatus,
      reason: override.reason,
    })
    const res = await api.get(`/api/attendance/sessions/${expanded}/records`)
    setRecords(res.data)
    setOverride(null)
  }

  const exportCSV = async () => {
    try {
      const params = {}
      if (semesterId) params.semester_id = semesterId
      if (fromDate)   params.from_date   = fromDate
      if (toDate)     params.to_date     = toDate
      const res = await api.get('/api/attendance/export', { params, responseType: 'blob' })
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

  const statusBadge = (s, overridden) => {
    const map = { present: 'badge-green', absent: 'badge-red', late: 'badge-yellow', excused: 'badge-gray' }
    return (
      <span className={`badge ${map[s] || 'badge-gray'}`}>
        {s}{overridden ? ' *' : ''}
      </span>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text-primary">Attendance Records</h1>
        <button className="btn-outline text-sm" onClick={exportCSV}>↓ Export CSV</button>
      </div>

      {/* Filters */}
      <div className="card space-y-3">
        <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Filters</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label className="label">Semester</label>
            <SemesterPicker
              value={semesterId}
              onChange={id => { setSemesterId(id); load(id, fromDate, toDate) }}
            />
          </div>
          <div>
            <label className="label">From date</label>
            <input type="date" className="input" value={fromDate}
              onChange={e => { setFromDate(e.target.value); load(semesterId, e.target.value, toDate) }} />
          </div>
          <div>
            <label className="label">To date</label>
            <input type="date" className="input" value={toDate}
              onChange={e => { setToDate(e.target.value); load(semesterId, fromDate, e.target.value) }} />
          </div>
        </div>
      </div>

      {/* Low attendance panel */}
      <LowAttendancePanel semesterId={semesterId} />

      {loading ? (
        <div className="animate-pulse space-y-3">
          {[...Array(4)].map((_, i) => <div key={i} className="card h-16 bg-slate-100" />)}
        </div>
      ) : sessions.length === 0 ? (
        <div className="card text-center py-10 text-text-muted">No sessions recorded yet.</div>
      ) : (
        sessions.map(session => (
          <div key={session.id} className="card">
            <button className="w-full flex items-center justify-between" onClick={() => loadRecords(session.id)}>
              <div className="text-left">
                <p className="font-semibold text-text-primary">{session.subject_name}</p>
                <p className="text-xs text-text-muted">
                  {new Date(session.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                  {' · '}{session.is_completed ? 'Completed' : 'In progress'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-sm font-semibold text-success">{session.present_count} present</p>
                  <p className="text-xs text-text-muted">of {session.total_students}</p>
                </div>
                <svg className={`w-4 h-4 text-text-muted transition-transform ${expanded === session.id ? 'rotate-180' : ''}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </button>

            {expanded === session.id && (
              <div className="mt-3 pt-3 border-t border-surface-border">
                {records.length === 0 ? (
                  <p className="text-sm text-text-muted text-center py-4">No records found</p>
                ) : (
                  <div className="space-y-1">
                    {records.map(rec => (
                      <div key={rec.id} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                        <div>
                          <p className="text-sm font-medium text-text-primary">{rec.student_name}</p>
                          <p className="text-xs text-text-muted">{rec.roll_number}</p>
                          {rec.is_overridden && (
                            <p className="text-xs text-text-muted italic">Override: {rec.override_reason}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {statusBadge(rec.status, rec.is_overridden)}
                          <button className="text-xs text-primary underline"
                            onClick={() => setOverride({ record: rec, newStatus: rec.status, reason: '' })}>
                            Override
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))
      )}

      {/* Override modal */}
      {override && (
        <div className="fixed inset-0 bg-black/40 flex items-end md:items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-sm p-5 space-y-4 shadow-xl">
            <h3 className="font-semibold text-text-primary">Override attendance</h3>
            <p className="text-sm text-text-secondary">{override.record.student_name} · {override.record.roll_number}</p>
            <div>
              <label className="label">New status</label>
              <select className="input" value={override.newStatus}
                onChange={e => setOverride(o => ({ ...o, newStatus: e.target.value }))}>
                {['present', 'absent', 'late', 'excused'].map(s => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Reason (required)</label>
              <input className="input" placeholder="e.g. Medical leave"
                value={override.reason}
                onChange={e => setOverride(o => ({ ...o, reason: e.target.value }))} />
            </div>
            <div className="flex gap-2">
              <button className="btn-outline flex-1" onClick={() => setOverride(null)}>Cancel</button>
              <button className="btn-primary flex-1" onClick={submitOverride}
                disabled={!override.reason.trim()}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function LowAttendancePanel({ semesterId }) {
  const [low,  setLow]  = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const params = semesterId ? { semester_id: semesterId } : {}
    api.get('/api/attendance/low-attendance', { params }).then(r => setLow(r.data))
  }, [semesterId])

  if (low.length === 0) return null
  return (
    <div className="card border-warning">
      <button className="w-full flex items-center justify-between" onClick={() => setOpen(o => !o)}>
        <p className="text-sm font-semibold text-warning">⚠ {low.length} student{low.length > 1 ? 's' : ''} below 75%</p>
        <svg className={`w-4 h-4 text-warning transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="mt-3 pt-3 border-t border-yellow-200 space-y-1">
          {low.map((item, i) => (
            <div key={i} className="flex items-center justify-between py-1.5">
              <div>
                <p className="text-sm font-medium text-text-primary">{item.student_name}</p>
                <p className="text-xs text-text-muted">{item.roll_number} · {item.subject_name}</p>
              </div>
              <span className="badge badge-yellow">{item.percentage}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
