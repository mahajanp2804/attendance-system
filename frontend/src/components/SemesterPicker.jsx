import { useEffect, useState } from 'react'
import api from '../hooks/api'

/**
 * Semester picker dropdown.
 * Props:
 *   value       — current semester_id string
 *   onChange    — (id) => void
 *   className   — optional extra classes
 */
export default function SemesterPicker({ value, onChange, className = '' }) {
  const [semesters, setSemesters] = useState([])

  useEffect(() => {
    api.get('/api/semesters/').then(res => {
      setSemesters(res.data)
      // Auto-select active semester if nothing selected
      if (!value) {
        const active = res.data.find(s => s.is_active)
        if (active) onChange(active.id)
      }
    })
  }, [])

  return (
    <select
      className={`input ${className}`}
      value={value || ''}
      onChange={e => onChange(e.target.value)}
    >
      <option value="">All semesters</option>
      {semesters.map(s => (
        <option key={s.id} value={s.id}>
          {s.name}{s.is_active ? ' (Active)' : ''}
        </option>
      ))}
    </select>
  )
}
