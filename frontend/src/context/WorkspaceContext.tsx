import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../api/client';
import type { Repository } from '../types/api';

interface WorkspaceContextType {
  repositories: Repository[];
  activeRepoId: number | 'all';
  setActiveRepoId: (id: number | 'all') => void;
  demoMode: boolean;
  setDemoMode: (enabled: boolean) => void;
  systemReady: boolean;
  systemChecks: Record<string, string>;
  globalSearch: string;
  setGlobalSearch: (query: string) => void;
  refreshRepositories: () => Promise<void>;
  loadingRepos: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [activeRepoId, setActiveRepoId] = useState<number | 'all'>('all');
  const [demoMode, setDemoMode] = useState<boolean>(() => {
    return localStorage.getItem('supportpilot_demo_mode') === 'true';
  });
  const [systemReady, setSystemReady] = useState<boolean>(true);
  const [systemChecks, setSystemChecks] = useState<Record<string, string>>({});
  const [globalSearch, setGlobalSearch] = useState<string>('');
  const [loadingRepos, setLoadingRepos] = useState<boolean>(true);

  const refreshRepositories = async () => {
    try {
      setLoadingRepos(true);
      const repos = await api.getRepositories();
      setRepositories(repos);
    } catch (err) {
      console.warn('Could not fetch repositories:', err);
    } finally {
      setLoadingRepos(false);
    }
  };

  const checkReadiness = async () => {
    try {
      const res = await api.getReadiness();
      setSystemReady(res.status === 'ready');
      if (res.checks) {
        setSystemChecks(res.checks);
      }
    } catch {
      setSystemReady(false);
    }
  };

  useEffect(() => {
    refreshRepositories();
    checkReadiness();
  }, []);

  useEffect(() => {
    localStorage.setItem('supportpilot_demo_mode', String(demoMode));
  }, [demoMode]);

  return (
    <WorkspaceContext.Provider
      value={{
        repositories,
        activeRepoId,
        setActiveRepoId,
        demoMode,
        setDemoMode,
        systemReady,
        systemChecks,
        globalSearch,
        setGlobalSearch,
        refreshRepositories,
        loadingRepos,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
};

export const useWorkspace = () => {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
};
