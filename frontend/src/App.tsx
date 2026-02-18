import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Rules from './pages/Rules'
import Messages from './pages/Messages'
import Account from './pages/Account'
import Login from './pages/Login'
import { getToken } from './api/client'

function RequireAuth() {
  if (!getToken()) return <Navigate to="/login" replace />
  return <Outlet />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/messages" element={<Messages />} />
          <Route path="/account" element={<Account />} />
        </Route>
      </Route>
    </Routes>
  )
}
