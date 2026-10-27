import { useEffect, useState, useRef } from 'react'
import api from '../../hooks/api'

export default function ProfStudents() {
  const [students, setStudents] = useState([])
  const [search,   setSearch]   = useState('')
  const [loading,  setLoading]  = useState(true)
  const [form,     setForm]     = useState(null)
  const [saving,   setSaving]   = useState(false)
  const [error,    setError]    = useState('')
  const [photoStudent, setPhotoStudent] = useState(null)
  const fileRef = useRef()

  const load = (q = '') => {
    api.get(`/api/students/${q ? `?search=${q}` : ''}`)
      .then(r => setStudents(r.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const createStudent = async () => {
    setError('')
    setSaving(true)
    try {
      await api.post('/api/students/', form)
      setForm(null)
      load()
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create student')
    } finally {
      setSaving(false)
    }
  }

  const uploadPhotos = async (studentId, files) => {
    const fd = new FormData()
    Array.from(files).forEach(f => fd.append('files', f))
    await api.post(`/api/students/${studentId}/photos`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    load()
  }

  const generateEmbedding = async (studentId) => {
    try {
      const res = await api.post(`/api/students/${studentId}/embed`)
      alert(res.data.status === 'success'
        ? `✅ Embedding generated from ${res.data.photos_used} photos`
        : res.data.message)
      load()
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed')
    }
  }

  const deactivate = async (studentId) => {
    if (!confirm('Deactivate this student?')) return
    await api.delete(`/api/students/${studentId}`)
    load()
  }

  const filtered = students.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    (s.roll_number || '').toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <div className="animate-pulse space-y-3 max-w-2xl mx-auto">{[...Array(5)].map((_,i) => <div key={i} className="card h-14 bg-slate-100"/>)}</div>

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text-primary">Students</h1>
        <button className="btn-primary text-sm" onClick={() => setForm({ name:'', email:'', password:'', roll_number:'', department:'', year_of_study:'' })}>
          + Add student
        </button>
      </div>

      {/* Search */}
      <input
        className="input"
        placeholder="Search by name or roll number…"
        value={search}
        onChange={e => { setSearch(e.target.value); load(e.target.value) }}
      />

      {/* Student list */}
      {filtered.length === 0 ? (
        <div className="card text-center py-10 text-text-muted">No students found.</div>
      ) : (
        <div className="space-y-2">
          {filtered.map(student => (
            <div key={student.id} className={`card ${!student.is_active ? 'opacity-50' : ''}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold text-sm shrink-0">
                    {student.name[0].toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">{student.name}</p>
                    <p className="text-xs text-text-muted">{student.roll_number} · {student.department}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {student.embedding_ready
                    ? <span className="badge badge-green">Face ✓</span>
                    : <span className="badge badge-yellow">No face</span>}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 mt-3 flex-wrap">
                <button
                  className="btn-outline text-xs"
                  onClick={() => { setPhotoStudent(student); fileRef.current?.click() }}
                >
                  Upload photos
                </button>
                {!student.embedding_ready ? (
                  <button className="btn-outline text-xs" onClick={() => generateEmbedding(student.id)}>
                    Generate face ID
                  </button>
                ) : (
                  <button className="btn-outline text-xs text-warning" onClick={() => generateEmbedding(student.id)}>
                    Re-generate face ID
                  </button>
                )}
                {student.is_active && (
                  <button className="btn-outline text-xs text-danger" onClick={() => deactivate(student.id)}>
                    Deactivate
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Hidden file input for photos */}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={e => {
          if (photoStudent && e.target.files.length) {
            uploadPhotos(photoStudent.id, e.target.files)
              .then(() => alert(`✅ ${e.target.files.length} photo(s) uploaded`))
              .catch(() => alert('Upload failed'))
          }
          e.target.value = ''
        }}
      />

      {/* Create student modal */}
      {form && (
        <div className="fixed inset-0 bg-black/40 flex items-end md:items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-sm p-5 space-y-3 shadow-xl max-h-[90vh] overflow-y-auto">
            <h3 className="font-semibold text-text-primary">Add new student</h3>
            {error && <p className="text-sm text-danger">{error}</p>}

            {[
              { key:'name',        label:'Full name',    type:'text',     placeholder:'Student Name' },
              { key:'email',       label:'Email',        type:'email',    placeholder:'student@college.edu' },
              { key:'password',    label:'Password',     type:'password', placeholder:'Temporary password' },
              { key:'roll_number', label:'Roll number',  type:'text',     placeholder:'CS2024001' },
              { key:'department',  label:'Department',   type:'text',     placeholder:'Computer Science' },
              { key:'year_of_study', label:'Year',       type:'number',   placeholder:'2' },
            ].map(({ key, label, type, placeholder }) => (
              <div key={key}>
                <label className="label">{label}</label>
                <input
                  className="input"
                  type={type}
                  placeholder={placeholder}
                  value={form[key]}
                  onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                />
              </div>
            ))}

            <div className="flex gap-2 pt-1">
              <button className="btn-outline flex-1" onClick={() => { setForm(null); setError('') }}>Cancel</button>
              <button className="btn-primary flex-1" onClick={createStudent} disabled={saving}>
                {saving ? 'Saving…' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
