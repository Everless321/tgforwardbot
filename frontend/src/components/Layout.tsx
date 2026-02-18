import { NavLink, Outlet } from 'react-router-dom'

export default function Layout() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-icon">✈</span>
          <span className="logo-text">TG Forward Bot</span>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/dashboard" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">⬛</span>
            Dashboard
          </NavLink>
          <NavLink to="/rules" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">⚙</span>
            Rules
          </NavLink>
          <NavLink to="/messages" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">💬</span>
            Messages
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <NavLink to="/account" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">👤</span>
            Account
          </NavLink>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
