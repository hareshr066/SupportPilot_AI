import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Ticket,
  GitFork,
  ShieldAlert,
  BarChart3,
} from 'lucide-react';

export const Navigation: React.FC = () => {
  return (
    <header className="navbar">
      <div className="nav-brand">
        <div className="nav-brand-icon">SP</div>
        <span>SupportPilot Ops</span>
      </div>

      <nav className="nav-links">
        <NavLink
          to="/"
          end
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          <LayoutDashboard size={16} />
          <span>Dashboard</span>
        </NavLink>

        <NavLink
          to="/analyze"
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          <Ticket size={16} />
          <span>Analyze Ticket</span>
        </NavLink>

        <NavLink
          to="/repositories"
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          <GitFork size={16} />
          <span>Repositories</span>
        </NavLink>

        <NavLink
          to="/escalations"
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          <ShieldAlert size={16} />
          <span>Escalation Queue</span>
        </NavLink>

        <NavLink
          to="/evaluation"
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          <BarChart3 size={16} />
          <span>Evaluation</span>
        </NavLink>
      </nav>

      <div className="status-badge">
        <span className="status-dot"></span>
        <span>AI Engine Connected</span>
      </div>
    </header>
  );
};
