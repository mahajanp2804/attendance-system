import { create } from 'zustand'
import api from '../hooks/api'

const useAuthStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  loading: false,

  login: async (email, password) => {
    set({ loading: true })
    const form = new URLSearchParams({ username: email, password })
    const res = await api.post('/api/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    const { access_token, refresh_token, role, user_id, name } = res.data
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    set({
      token: access_token,
      refreshToken: refresh_token,
      user: { id: user_id, name, role },
      loading: false,
    })
    return role
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ user: null, token: null, refreshToken: null })
  },

  fetchMe: async () => {
    try {
      const res = await api.get('/api/auth/me')
      set({ user: res.data })
      return res.data
    } catch {
      get().logout()
      return null
    }
  },

  isStudent:   () => get().user?.role === 'student',
  isProfessor: () => ['professor', 'admin'].includes(get().user?.role),
}))

export default useAuthStore
