import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import useAuthStore from './store/authStore'

import Login from './pages/Login'
import StudentLayout  from './pages/student/Layout'
import ProfessorLayout from './pages/professor/Layout'
import StudentDashboard  from './pages/student/Dashboard'
import StudentAttendance from './pages/student/Attendance'
import StudentTimetable  from './pages/student/Timetable'
import ProfDashboard  from './pages/professor/Dashboard'
import ProfTimetable  from './pages/professor/Timetable'
import ProfStudents   from './pages/professor/Students'
import ProfScanner    from './pages/professor/Scanner'
import ProfAttendance from './pages/professor/Attendance'

function ProtectedRoute({ children, role }) {
  const { user, token } = useAuthStore()
  if (!token) return <Navigate to="/login" replace />
  if (role && user && user.role !== role && !(role === 'professor' && user.role === 'admin'))
    return <Navigate to="/login" replace />
  return children
}

function RootRedirect() {
  const { user, token, fetchMe } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (!token) { navigate('/login'); return }
    if (user) {
      navigate(user.role === 'student' ? '/student' : '/professor')
      return
    }
    fetchMe().then(u => {
      if (u) navigate(u.role === 'student' ? '/student' : '/professor')
      else navigate('/login')
    })
  }, [])

  return <div className="min-h-screen flex items-center justify-center text-text-muted">Loading…</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<Login />} />

        {/* Student portal */}
        <Route path="/student" element={<ProtectedRoute role="student"><StudentLayout /></ProtectedRoute>}>
          <Route index element={<StudentDashboard />} />
          <Route path="attendance" element={<StudentAttendance />} />
          <Route path="timetable"  element={<StudentTimetable />} />
        </Route>

        {/* Professor portal */}
        <Route path="/professor" element={<ProtectedRoute role="professor"><ProfessorLayout /></ProtectedRoute>}>
          <Route index element={<ProfDashboard />} />
          <Route path="timetable"  element={<ProfTimetable />} />
          <Route path="students"   element={<ProfStudents />} />
          <Route path="scanner"    element={<ProfScanner />} />
          <Route path="attendance" element={<ProfAttendance />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
