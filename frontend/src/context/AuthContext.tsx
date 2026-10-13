import React, { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { api } from '../api/client';
import type { AuthUser, AuthOrganization, LoginPayload, SignupPayload } from '../types/api';

interface AuthContextType {
  user: AuthUser | null;
  organization: AuthOrganization | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  signup: (payload: SignupPayload) => Promise<void>;
  logout: () => void;
  rotateApiKey: () => Promise<string>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [organization, setOrganization] = useState<AuthOrganization | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('sp_token'));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const savedToken = localStorage.getItem('sp_token');
      if (!savedToken) {
        setIsLoading(false);
        return;
      }

      try {
        const res = await api.getMe();
        setUser(res.user);
        setOrganization(res.organization);
        setToken(res.access_token);
        localStorage.setItem('sp_token', res.access_token);
      } catch (err) {
        console.warn('Session expired or invalid, logging out:', err);
        localStorage.removeItem('sp_token');
        setToken(null);
        setUser(null);
        setOrganization(null);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = async (payload: LoginPayload) => {
    const res = await api.login(payload);
    localStorage.setItem('sp_token', res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    setOrganization(res.organization);
  };

  const signup = async (payload: SignupPayload) => {
    const res = await api.signup(payload);
    localStorage.setItem('sp_token', res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    setOrganization(res.organization);
  };

  const logout = () => {
    localStorage.removeItem('sp_token');
    setToken(null);
    setUser(null);
    setOrganization(null);
  };

  const rotateApiKey = async (): Promise<string> => {
    const newOrg = await api.rotateApiKey();
    setOrganization(newOrg);
    return newOrg.api_key;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        signup,
        logout,
        rotateApiKey,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
