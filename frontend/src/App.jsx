import { useEffect } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { setUnauthorizedHandler } from "./api";
import LoginPage from "./pages/LoginPage";
import ProjectListPage from "./pages/ProjectListPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";
import ScanDetailPage from "./pages/ScanDetailPage";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";

export default function App() {
  const navigate = useNavigate();

  useEffect(() => {
    setUnauthorizedHandler(() => {
      navigate("/login");
    });
  }, [navigate]);

  function handleLogout() {
    navigate("/login");
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout onLogout={handleLogout}>
              <ProjectListPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/projects/:projectId"
        element={
          <RequireAuth>
            <Layout onLogout={handleLogout}>
              <ProjectDetailPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/scans/:scanId"
        element={
          <RequireAuth>
            <Layout onLogout={handleLogout}>
              <ScanDetailPage />
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
