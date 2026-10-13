import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { WorkspaceProvider } from './context/WorkspaceContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { DashboardPage } from './pages/DashboardPage';
import { AnalyzeTicketPage } from './pages/AnalyzeTicketPage';
import { PipelineRunDetailsPage } from './pages/PipelineRunDetailsPage';
import { RepositoriesPage } from './pages/RepositoriesPage';
import { EscalationsPage } from './pages/EscalationsPage';
import { EvaluationPage } from './pages/EvaluationPage';
import { TicketsPage } from './pages/TicketsPage';
import { RunsPage } from './pages/RunsPage';
import { SettingsPage } from './pages/SettingsPage';
import { IntegrationPage } from './pages/IntegrationPage';

const AppLayout: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  return (
    <div className="app-container">
      <Sidebar />
      <div className="app-main">
        <TopBar />
        <main className="main-content">{children}</main>
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <WorkspaceProvider>
          <Routes>
            {/* Public Authentication Pages */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />

            {/* Protected App Routes */}
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Routes>
                      <Route path="/" element={<DashboardPage />} />
                      <Route path="/dashboard" element={<DashboardPage />} />
                      <Route path="/analyze" element={<AnalyzeTicketPage />} />
                      <Route path="/tickets/new" element={<AnalyzeTicketPage />} />
                      <Route path="/tickets" element={<TicketsPage />} />
                      <Route path="/runs/:id" element={<PipelineRunDetailsPage />} />
                      <Route path="/runs" element={<RunsPage />} />
                      <Route path="/repositories" element={<RepositoriesPage />} />
                      <Route path="/integration" element={<IntegrationPage />} />
                      <Route path="/escalations" element={<EscalationsPage />} />
                      <Route path="/evaluation" element={<EvaluationPage />} />
                      <Route path="/settings" element={<SettingsPage />} />
                      <Route path="*" element={<Navigate to="/dashboard" replace />} />
                    </Routes>
                  </AppLayout>
                </ProtectedRoute>
              }
            />
          </Routes>
        </WorkspaceProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
