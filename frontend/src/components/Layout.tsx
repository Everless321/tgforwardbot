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
            仪表盘
          </NavLink>
          <NavLink to="/rules" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">⚙</span>
            转发规则
          </NavLink>
          <NavLink to="/messages" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">💬</span>
            消息记录
          </NavLink>
          <NavLink to="/logs" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">📋</span>
            系统日志
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <NavLink to="/account" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">👤</span>
            账户
          </NavLink>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
