import { useEffect, useState } from 'react'
import api from '../../hooks/api'
import SemesterPicker from '../../components/SemesterPicker'

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']

export default function ProfTimetable() {
  const [timetable,    setTimetable]    = useState({})
  const [subjects,     setSubjects]     = useState([])
  const [semesterId,   setSemesterId]   = useState('')
  const [loading,      setLoading]      = useState(true)
  const [slotForm,     setSlotForm]     = useState(null)
  const [subjectForm,  setSubjectForm]  = useState(null)
  const [semForm,      setSemForm]      = useState(null)
  const [saving,       setSaving]       = useState(false)
  const [error,        setError]        = useState('')
  const [tab,          setTab]          = useState('timetable') // 'timetable' | 'subjects' | 'semesters'

  const loadTimetable = (semId = semesterId) => {
    const params = semId ? { semester_id: semId } : {}
    api.get('/api/timetable/', { params }).then(r => setTimetable(r.data)).finally(() => setLoading(false))
  }

  const loadSubjects = (semId = semesterId) => {
    const params = semId ? { semester_id: semId } : {}
    api.get('/api/subjects/', { params }).then(r => setSubjects(r.data))
  }

  useEffect(() => { loadTimetable(); loadSubjects() }, [])

  const onSemesterChange = (id) => {
    setSemesterId(id)
    loadTimetable(id)
    loadSubjects(id)
  }

  // ── Slot CRUD ──────────────────────────────────────────────────────────────
  const saveSlot = async () => {
    setError(''); setSaving(true)
    try {
      if (slotForm.id) {
        await api.patch(`/api/timetable/slots/${slotForm.id}`, {
          day: slotForm.day, start_time: slotForm.start_time, end_time: slotForm.end_time, room: slotForm.room
        })
      } else {
        await api.post('/api/timetable/slots', slotForm)
      }
      setSlotForm(null); loadTimetable()
    } catch (e) { setError(e.response?.data?.detail || 'Failed to save slot') }
    finally { setSaving(false) }
  }

  const deleteSlot = async (id) => {
    if (!confirm('Delete this slot?')) return
    await api.delete(`/api/timetable/slots/${id}`)
    loadTimetable()
  }

  // ── Subject CRUD ───────────────────────────────────────────────────────────
  const saveSubject = async () => {
    setError(''); setSaving(true)
    try {
      if (subjectForm.id) {
        await api.patch(`/api/subjects/${subjectForm.id}`, subjectForm)
      } else {
        await api.post('/api/subjects/', { ...subjectForm, semester_id: semesterId })
      }
      setSubjectForm(null); loadSubjects()
    } catch (e) { setError(e.response?.data?.detail || 'Failed to save subject') }
    finally { setSaving(false) }
  }

  const deleteSubject = async (id) => {
    if (!confirm('Delete this subject and all its timetable slots?')) return
    await api.delete(`/api/subjects/${id}`)
    loadSubjects(); loadTimetable()
  }

  // ── Semester CRUD ──────────────────────────────────────────────────────────
  const saveSemester = async () => {
    setError(''); setSaving(true)
    try {
      await api.post('/api/semesters/', semForm)
      setSemForm(null)
    } catch (e) { setError(e.response?.data?.detail || 'Failed to create semester') }
    finally { setSaving(false) }
  }

  const activateSemester = async (id) => {
    await api.patch(`/api/semesters/${id}/activate`)
    onSemesterChange(id)
  }

  if (loading) return (
    <div className="animate-pulse space-y-4 max-w-2xl mx-auto">
      {[...Array(3)].map((_, i) => <div key={i} className="card h-24 bg-slate-100" />)}
    </div>
  )

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <h1 className="text-xl font-bold text-text-primary">Timetable & Subjects</h1>

      {/* Semester picker */}
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <SemesterPicker value={semesterId} onChange={onSemesterChange} />
        </div>
        <button className="btn-outline text-sm shrink-0" onClick={() => setTab('semesters')}>
          Manage semesters
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-surface-border">
        {[
          { key: 'timetable', label: 'Timetable' },
          { key: 'subjects',  label: 'Subjects' },
          { key: 'semesters', label: 'Semesters' },
        ].map(t => (
          <button key={t.key}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── TIMETABLE TAB ─────────────────────────────────────────────── */}
      {tab === 'timetable' && (
        <>
          <div className="flex justify-end">
            <button className="btn-primary text-sm"
              onClick={() => setSlotForm({ subject_id: '', day: 'monday', start_time: '09:00', end_time: '10:00', room: '' })}>
              + Add slot
            </button>
          </div>

          {DAYS.map(day => {
            const slots = timetable[day] || []
            return (
              <div key={day} className="card">
                <h2 className="font-semibold text-text-primary capitalize mb-2">{day}</h2>
                {slots.length === 0 ? (
                  <p className="text-xs text-text-muted py-1">No classes</p>
                ) : (
                  <div className="space-y-2">
                    {slots.map(slot => (
                      <div key={slot.id} className="flex items-center justify-between py-2 border-b border-surface-border last:border-0">
                        <div>
                          <p className="text-sm font-medium text-text-primary">{slot.subject_name}</p>
                          <p className="text-xs text-text-muted">{slot.subject_code} · {slot.room || 'No room'}</p>
                        </div>
                        <div className="flex items-center gap-3">
                          <p className="text-sm text-text-secondary font-mono">{slot.start_time}–{slot.end_time}</p>
                          <button className="text-xs text-primary underline"
                            onClick={() => setSlotForm({ ...slot })}>Edit</button>
                          <button className="text-xs text-danger underline"
                            onClick={() => deleteSlot(slot.id)}>Del</button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </>
      )}

      {/* ── SUBJECTS TAB ──────────────────────────────────────────────── */}
      {tab === 'subjects' && (
        <>
          <div className="flex justify-end">
            <button className="btn-primary text-sm"
              onClick={() => setSubjectForm({ name: '', code: '', department: '' })}>
              + Add subject
            </button>
          </div>
          {subjects.length === 0 ? (
            <div className="card text-center py-10 text-text-muted">No subjects in this semester.</div>
          ) : (
            <div className="space-y-2">
              {subjects.map(sub => (
                <div key={sub.id} className="card flex items-center justify-between">
                  <div>
                    <p className="font-medium text-text-primary">{sub.name}</p>
                    <p className="text-xs text-text-muted">{sub.code} · {sub.department} · {sub.professor_name}</p>
                  </div>
                  <div className="flex gap-2">
                    <button className="text-xs text-primary underline"
                      onClick={() => setSubjectForm({ id: sub.id, name: sub.name, code: sub.code, department: sub.department || '' })}>
                      Edit
                    </button>
                    <button className="text-xs text-danger underline"
                      onClick={() => deleteSubject(sub.id)}>Del</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* ── SEMESTERS TAB ─────────────────────────────────────────────── */}
      {tab === 'semesters' && (
        <>
          <div className="flex justify-end">
            <button className="btn-primary text-sm"
              onClick={() => setSemForm({ name: '', start_date: '', end_date: '' })}>
              + New semester
            </button>
          </div>
          <SemesterList onActivate={activateSemester} />
        </>
      )}

      {/* ── Slot form modal ─────────────────────────────────────────── */}
      {slotForm && (
        <Modal title={slotForm.id ? 'Edit slot' : 'New slot'} onClose={() => { setSlotForm(null); setError('') }}>
          {error && <p className="text-sm text-danger">{error}</p>}
          {!slotForm.id && (
            <div>
              <label className="label">Subject</label>
              <select className="input" value={slotForm.subject_id}
                onChange={e => setSlotForm(f => ({ ...f, subject_id: e.target.value }))}>
                <option value="">Select subject</option>
                {subjects.map(s => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
              </select>
            </div>
          )}
          <div>
            <label className="label">Day</label>
            <select className="input" value={slotForm.day}
              onChange={e => setSlotForm(f => ({ ...f, day: e.target.value }))}>
              {DAYS.map(d => <option key={d} value={d} className="capitalize">{d.charAt(0).toUpperCase() + d.slice(1)}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Start time</label>
              <input type="time" className="input" value={slotForm.start_time}
                onChange={e => setSlotForm(f => ({ ...f, start_time: e.target.value }))} />
            </div>
            <div>
              <label className="label">End time</label>
              <input type="time" className="input" value={slotForm.end_time}
                onChange={e => setSlotForm(f => ({ ...f, end_time: e.target.value }))} />
            </div>
          </div>
          <div>
            <label className="label">Room</label>
            <input className="input" placeholder="e.g. CS-101" value={slotForm.room}
              onChange={e => setSlotForm(f => ({ ...f, room: e.target.value }))} />
          </div>
          <div className="flex gap-2">
            <button className="btn-outline flex-1" onClick={() => { setSlotForm(null); setError('') }}>Cancel</button>
            <button className="btn-primary flex-1" onClick={saveSlot} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Subject form modal ───────────────────────────────────────── */}
      {subjectForm && (
        <Modal title={subjectForm.id ? 'Edit subject' : 'New subject'} onClose={() => { setSubjectForm(null); setError('') }}>
          {error && <p className="text-sm text-danger">{error}</p>}
          {[
            { key: 'name',       label: 'Subject name', placeholder: 'Operating Systems' },
            { key: 'code',       label: 'Subject code', placeholder: 'CS301' },
            { key: 'department', label: 'Department',   placeholder: 'Computer Science' },
          ].map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="label">{label}</label>
              <input className="input" placeholder={placeholder} value={subjectForm[key]}
                onChange={e => setSubjectForm(f => ({ ...f, [key]: e.target.value }))} />
            </div>
          ))}
          <div className="flex gap-2">
            <button className="btn-outline flex-1" onClick={() => { setSubjectForm(null); setError('') }}>Cancel</button>
            <button className="btn-primary flex-1" onClick={saveSubject} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Semester form modal ──────────────────────────────────────── */}
      {semForm && (
        <Modal title="New semester" onClose={() => { setSemForm(null); setError('') }}>
          {error && <p className="text-sm text-danger">{error}</p>}
          <div>
            <label className="label">Semester name</label>
            <input className="input" placeholder="Semester 5 (2024-25)" value={semForm.name}
              onChange={e => setSemForm(f => ({ ...f, name: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Start date</label>
              <input type="date" className="input" value={semForm.start_date}
                onChange={e => setSemForm(f => ({ ...f, start_date: e.target.value }))} />
            </div>
            <div>
              <label className="label">End date</label>
              <input type="date" className="input" value={semForm.end_date}
                onChange={e => setSemForm(f => ({ ...f, end_date: e.target.value }))} />
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-outline flex-1" onClick={() => { setSemForm(null); setError('') }}>Cancel</button>
            <button className="btn-primary flex-1" onClick={saveSemester} disabled={saving}>
              {saving ? 'Saving…' : 'Create'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Shared modal wrapper ───────────────────────────────────────────────────────
function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-end md:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-sm p-5 space-y-3 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-text-primary">{title}</h3>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── Semester list sub-component ────────────────────────────────────────────────
function SemesterList({ onActivate }) {
  const [semesters, setSemesters] = useState([])
  useEffect(() => {
    api.get('/api/semesters/').then(r => setSemesters(r.data))
  }, [])

  return (
    <div className="space-y-2">
      {semesters.length === 0 ? (
        <div className="card text-center py-10 text-text-muted">No semesters yet. Create one above.</div>
      ) : semesters.map(sem => (
        <div key={sem.id} className={`card flex items-center justify-between ${sem.is_active ? 'border-primary' : ''}`}>
          <div>
            <p className="font-medium text-text-primary">{sem.name}</p>
            <p className="text-xs text-text-muted">
              {new Date(sem.start_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
              {' – '}
              {new Date(sem.end_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </p>
          </div>
          <div>
            {sem.is_active
              ? <span className="badge badge-blue">Active</span>
              : <button className="btn-outline text-xs" onClick={() => onActivate(sem.id)}>
                  Set active
                </button>
            }
          </div>
        </div>
      ))}
    </div>
  )
}
