import { useEffect, useState } from 'react'
import api from '../../hooks/api'
import SemesterPicker from '../../components/SemesterPicker'

const DAYS = ['monday','tuesday','wednesday','thursday','friday','saturday']
const DAY_LABELS = { monday:'Monday', tuesday:'Tuesday', wednesday:'Wednesday', thursday:'Thursday', friday:'Friday', saturday:'Saturday' }

export default function StudentTimetable() {
  const [timetable,  setTimetable]  = useState({})
  const [semesterId, setSemesterId] = useState('')
  const [loading,    setLoading]    = useState(true)
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long' }).toLowerCase()

  const load = (semId = semesterId) => {
    setLoading(true)
    const params = semId ? { semester_id: semId } : {}
    api.get('/api/timetable/', { params }).then(r => setTimetable(r.data)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  if (loading) return (
    <div className="animate-pulse space-y-4 max-w-2xl mx-auto">
      {[...Array(3)].map((_, i) => <div key={i} className="card h-24 bg-slate-100" />)}
    </div>
  )

  const activeDays = DAYS.filter(d => timetable[d]?.length > 0)

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-text-primary">My Timetable</h1>

      <SemesterPicker
        value={semesterId}
        onChange={id => { setSemesterId(id); load(id) }}
      />

      {activeDays.length === 0 ? (
        <div className="card text-center py-10 text-text-muted">No timetable set up for this semester.</div>
      ) : activeDays.map(day => (
        <div key={day} className={`card ${day === today ? 'border-primary ring-1 ring-primary/20' : ''}`}>
          <div className="flex items-center gap-2 mb-3">
            <h2 className="font-semibold text-text-primary">{DAY_LABELS[day]}</h2>
            {day === today && <span className="badge badge-blue">Today</span>}
          </div>
          <div className="space-y-2">
            {timetable[day].map(slot => (
              <div key={slot.id} className="flex items-center gap-3 py-2 border-b border-surface-border last:border-0">
                <div className="w-16 text-xs font-mono text-text-secondary shrink-0">{slot.start_time}</div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-text-primary">{slot.subject_name}</p>
                  <p className="text-xs text-text-muted">{slot.subject_code} · {slot.room || 'TBA'}</p>
                </div>
                <div className="text-xs text-text-muted text-right shrink-0">{slot.professor_name}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
