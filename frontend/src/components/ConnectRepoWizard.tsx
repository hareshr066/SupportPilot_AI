import React, { useState } from 'react';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import { FolderGit2, CheckCircle2, AlertCircle, X, ArrowRight, Loader2 } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export const ConnectRepoWizard: React.FC<Props> = ({ isOpen, onClose, onSuccess }) => {
  const { refreshRepositories } = useWorkspace();
  const [step, setStep] = useState<number>(1);
  const [owner, setOwner] = useState<string>('');
  const [name, setName] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [, setCreatedRepo] = useState<any>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner.trim() || !name.trim()) {
      setError('Owner and repository name are required.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const repo = await api.createRepository({ owner: owner.trim(), name: name.trim() });
      setCreatedRepo(repo);
      setStep(3);

      // Trigger automatic sync
      try {
        await api.syncRepository(repo.id);
      } catch (syncErr) {
        console.warn('Initial sync trigger failed:', syncErr);
      }

      await refreshRepositories();
      setStep(4);
    } catch (err: any) {
      setError(err.message || 'Failed to connect repository. Please verify GitHub owner and name.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(15, 23, 42, 0.5)',
        backdropFilter: 'blur(4px)',
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
    >
      <div
        className="panel"
        style={{
          width: '100%',
          maxWidth: '520px',
          padding: '1.5rem',
          margin: 0,
          background: '#FFFFFF',
          boxShadow: 'var(--shadow-md)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FolderGit2 size={18} color="var(--primary)" />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>Connect GitHub Repository</h3>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Step Indicator */}
        <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '1.25rem' }}>
          {[1, 2, 3, 4].map((s) => (
            <div
              key={s}
              style={{
                flex: 1,
                height: '4px',
                borderRadius: '2px',
                background: s <= step ? 'var(--primary)' : '#E2E8F0',
              }}
            />
          ))}
        </div>

        {error && (
          <div className="error-banner">
            <AlertCircle size={15} />
            <span>{error}</span>
          </div>
        )}

        {step === 1 && (
          <form onSubmit={() => setStep(2)}>
            <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Enter the owner and repository name of the GitHub repository you wish to connect to SupportPilot.
            </p>
            <div className="form-group">
              <label className="form-label">GitHub Owner / Organization</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. microsoft"
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Repository Name</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. vscode"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem' }}>
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  if (owner.trim() && name.trim()) setStep(2);
                  else setError('Please enter both owner and repository name.');
                }}
              >
                <span>Continue</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </form>
        )}

        {step === 2 && (
          <div>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.5rem' }}>Confirm Repository Details</h4>
            <div style={{ background: '#F8FAFC', padding: '0.85rem', borderRadius: 'var(--radius-sm)', border: '1px solid #E2E8F0', marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Target Repository</div>
              <div style={{ fontSize: '1rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                {owner}/{name}
              </div>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              SupportPilot will register webhooks (if permitted) and index recent issue history to build root cause and retrieval vector context.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button type="button" className="btn btn-secondary" onClick={() => setStep(1)}>
                Back
              </button>
              <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={loading}>
                {loading ? <Loader2 size={14} className="spinner" /> : <FolderGit2 size={14} />}
                <span>Register Repository</span>
              </button>
            </div>
          </div>
        )}

        {step >= 3 && (
          <div style={{ textAlign: 'center', padding: '1rem 0' }}>
            <CheckCircle2 size={40} color="var(--success)" style={{ margin: '0 auto 0.75rem auto' }} />
            <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '0.35rem' }}>
              Repository Connected Successfully!
            </h4>
            <p style={{ fontSize: '0.825rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              {owner}/{name} is now registered. Issue synchronization has been initiated.
            </p>
            <button
              className="btn btn-primary"
              onClick={() => {
                onClose();
                if (onSuccess) onSuccess();
              }}
              style={{ width: '100%' }}
            >
              Go to Workspace
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
