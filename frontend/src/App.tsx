import type React from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { Sidebar } from "./components/Sidebar";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Chat from "./pages/Chat";
import Dashboards from "./pages/Dashboards";
import DashboardDetail from "./pages/DashboardDetail";
import Predictions from "./pages/Predictions";
import Profile from "./pages/Profile";
import Team from "./pages/Team";

function AdminOnly({ children }: { children: React.ReactElement }) {
  const { user } = useAuth();
  if (user && user.role !== "admin") return <Navigate to="/chat" replace />;
  return children;
}

function Protected() {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <Outlet />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route element={<Protected />}>
            <Route path="/chat" element={<Chat />} />
            <Route path="/dashboard" element={<Dashboards />} />
            <Route path="/dashboard/:id" element={<DashboardDetail />} />
            <Route path="/predictions" element={<Predictions />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/team" element={<AdminOnly><Team /></AdminOnly>} />
          </Route>
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
