import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { WorkspaceProvider } from './context/WorkspaceContext';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { DashboardPage } from './pages/DashboardPage';
import { AnalyzeTicketPage } from './pages/AnalyzeTicketPage';
import { PipelineRunDetailsPage } from './pages/PipelineRunDetailsPage';
import { RepositoriesPage } from './pages/RepositoriesPage';
import { EscalationsPage } from './pages/EscalationsPage';
import { EvaluationPage } from './pages/EvaluationPage';
import { TicketsPage } from './pages/TicketsPage';
import { RunsPage } from './pages/RunsPage';
import { SettingsPage } from './pages/SettingsPage';

export const App: React.FC = () => {
  return (
    <WorkspaceProvider>
      <BrowserRouter>
        <div className="app-container">
          <Sidebar />
          <div className="app-main">
            <TopBar />
            <main className="main-content">
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/analyze" element={<AnalyzeTicketPage />} />
                <Route path="/tickets/new" element={<AnalyzeTicketPage />} />
                <Route path="/tickets" element={<TicketsPage />} />
                <Route path="/runs/:id" element={<PipelineRunDetailsPage />} />
                <Route path="/runs" element={<RunsPage />} />
                <Route path="/repositories" element={<RepositoriesPage />} />
                <Route path="/escalations" element={<EscalationsPage />} />
                <Route path="/evaluation" element={<EvaluationPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="*" element={<DashboardPage />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </WorkspaceProvider>
  );
};

export default App;
