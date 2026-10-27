import { NavLink, useNavigate } from 'react-router-dom'
import useAuthStore from '../store/authStore'

export default function SidebarLayout({ navItems, children }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => { logout(); navigate('/login') }

  return (
    <div className="min-h-screen flex bg-surface">

      {/* ── Sidebar (desktop) ─────────────────────────────────────── */}
      <aside className="hidden md:flex w-60 flex-col bg-white border-r border-surface-border shrink-0">
        {/* Brand */}
        <div className="px-5 py-5 border-b border-surface-border">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="font-bold text-text-primary">AttendAI</span>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ` +
                (isActive
                  ? 'bg-blue-50 text-primary'
                  : 'text-text-secondary hover:bg-slate-50 hover:text-text-primary')
              }
            >
              <span className="w-5 h-5 shrink-0">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User / logout */}
        <div className="px-3 py-4 border-t border-surface-border">
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-semibold text-sm">
              {user?.name?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">{user?.name}</p>
              <p className="text-xs text-text-muted capitalize">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="mt-2 w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-red-50 hover:text-danger transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile top bar */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-surface-border">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944" />
              </svg>
            </div>
            <span className="font-bold text-text-primary text-sm">AttendAI</span>
          </div>
          <div className="text-xs text-text-secondary capitalize">{user?.name} · {user?.role}</div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4 md:p-6">{children}</main>

        {/* Mobile bottom nav */}
        <nav className="md:hidden flex border-t border-surface-border bg-white">
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex-1 flex flex-col items-center py-2 text-xs font-medium transition-colors ` +
                (isActive ? 'text-primary' : 'text-text-muted')
              }
            >
              <span className="w-5 h-5 mb-0.5">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}
