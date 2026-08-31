import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, APIClientError } from '../api/client';
import type { Repository, PipelineStageRun, PipelineResult } from '../types/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { DEMO_PIPELINE_RESULT_AUTO } from '../data/demoFixtures';
import { PipelineStageProgress } from '../components/PipelineStageProgress';
import {
  Send,
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Shield,
  Layers,
  Search,
  CheckSquare,
  Zap,
} from 'lucide-react';

export const AnalyzeTicketPage: React.FC = () => {
  const navigate = useNavigate();
  const { demoMode } = useWorkspace();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loadingRepos, setLoadingRepos] = useState<boolean>(true);

  // Form State
  const [repositoryId, setRepositoryId] = useState<string>('');
  const [title, setTitle] = useState<string>('');
  const [body, setBody] = useState<string>('');
  const [issueNumber, setIssueNumber] = useState<string>('');

  // Validation & Submission
  const [formErrors, setFormErrors] = useState<{ repositoryId?: string; title?: string }>({});
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Polling Pipeline Run State
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [stages, setStages] = useState<PipelineStageRun[]>([]);
  const [pipelineResult, setPipelineResult] = useState<PipelineResult | null>(null);
  const pollingRef = useRef<number | null>(null);

  useEffect(() => {
    async function loadRepos() {
      try {
        const repos = await api.getRepositories();
        setRepositories(repos);
        if (repos.length > 0) {
          setRepositoryId(String(repos[0].id));
        }
      } catch (err: unknown) {
        console.error('Failed to load repositories', err);
      } finally {
        setLoadingRepos(false);
      }
    }
    loadRepos();

    return () => {
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
      }
    };
  }, []);

  const validate = (): boolean => {
    const errors: { repositoryId?: string; title?: string } = {};
    if (!repositoryId) {
      errors.repositoryId = 'Please select a registered repository.';
    }
    if (!title || !title.trim()) {
      errors.title = 'Ticket title is required.';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate() || submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    setPipelineResult(null);

    try {
      if (demoMode) {
        // Fast mock demo execution
        setTimeout(() => {
          setActiveRunId(DEMO_PIPELINE_RESULT_AUTO.pipeline_run_id);
          setPipelineResult(DEMO_PIPELINE_RESULT_AUTO);
          setSubmitting(false);
          navigate(`/runs/${DEMO_PIPELINE_RESULT_AUTO.pipeline_run_id}`);
        }, 1200);
        return;
      }

      const payload = {
        repository_id: Number(repositoryId),
        title: title.trim(),
        body: body.trim() || undefined,
        issue_number: issueNumber ? Number(issueNumber) : undefined,
      };

      const result = await api.analyzeTicket(payload);
      setActiveRunId(result.pipeline_run_id);
      setPipelineResult(result);

      // Start status polling
      startPolling(result.pipeline_run_id);
    } catch (err: unknown) {
      if (demoMode) {
        setActiveRunId(DEMO_PIPELINE_RESULT_AUTO.pipeline_run_id);
        setPipelineResult(DEMO_PIPELINE_RESULT_AUTO);
        setSubmitting(false);
        navigate(`/runs/${DEMO_PIPELINE_RESULT_AUTO.pipeline_run_id}`);
        return;
      }
      if (err instanceof APIClientError) {
        setSubmitError(err.message);
      } else {
        setSubmitError('SupportPilot backend is currently unavailable.');
      }
      setSubmitting(false);
    }
  };

  const startPolling = (runId: string) => {
    if (pollingRef.current) window.clearInterval(pollingRef.current);

    const poll = async () => {
      try {
        const stageRuns = await api.getPipelineRunStages(runId);
        setStages(stageRuns);

        const statusRes = await api.getPipelineRunStatus(runId);
        const currentStatus = String(statusRes.status || '');

        if (['SUCCEEDED', 'FAILED', 'ESCALATED'].includes(currentStatus)) {
          if (pollingRef.current) window.clearInterval(pollingRef.current);
          const fullRes = await api.getPipelineRunResult(runId);
          setPipelineResult(fullRes);
          setSubmitting(false);
        }
      } catch (err: unknown) {
        console.error('Polling error', err);
      }
    };

    poll();
    pollingRef.current = window.setInterval(poll, 1500);
  };

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
      {/* Visual Flow Bar */}
      <div className="flow-pipeline-bar">
        <div className="flow-step active">
          <div className="flow-step-num">1</div> Issue Input
        </div>
        <div className="flow-arrow">→</div>
        <div className="flow-step">
          <div className="flow-step-num">2</div> AI Analysis
        </div>
        <div className="flow-arrow">→</div>
        <div className="flow-step">
          <div className="flow-step-num">3</div> Evidence Retrieval
        </div>
        <div className="flow-arrow">→</div>
        <div className="flow-step">
          <div className="flow-step-num">4</div> Triage Decision
        </div>
      </div>

      <div className="page-header">
        <div>
          <h1 className="page-title">Analyze Support Ticket</h1>
          <p className="page-subtitle">
            Submit a technical issue. SupportPilot will classify severity, search for duplicates, retrieve relevant resolved cases, generate an evidence-backed resolution, verify its claims, estimate calibrated confidence, and recommend whether to resolve or escalate.
          </p>
        </div>
      </div>

      {submitError && (
        <div className="error-banner">
          <AlertCircle size={18} />
          <div>{submitError}</div>
        </div>
      )}

      {/* 2-Column Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '1.5rem', alignItems: 'start' }}>
        {/* Left Column: Input Form */}
        <div className="panel">
          <div className="panel-title" style={{ marginBottom: '1.25rem' }}>
            Ticket Details & Reproduction Context
          </div>

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Target Repository *</label>
              <select
                className="form-select"
                value={repositoryId}
                onChange={(e) => setRepositoryId(e.target.value)}
                disabled={submitting || loadingRepos}
              >
                {loadingRepos ? (
                  <option value="">Loading repositories...</option>
                ) : repositories.length === 0 ? (
                  <option value="">No repositories connected (Please register one first)</option>
                ) : (
                  repositories.map((repo) => (
                    <option key={repo.id} value={repo.id}>
                      {repo.full_name} ({repo.issue_count} historical issues)
                    </option>
                  ))
                )}
              </select>
              {formErrors.repositoryId && <div className="form-error">{formErrors.repositoryId}</div>}
            </div>

            <div className="form-group">
              <label className="form-label">Ticket Title *</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Terminal crash after update on Windows"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={submitting}
              />
              {formErrors.title && <div className="form-error">{formErrors.title}</div>}
            </div>

            <div className="form-group">
              <label className="form-label">Description / Reproduction Steps</label>
              <textarea
                className="form-textarea"
                placeholder="Paste error logs, stack traces, or step-by-step reproduction instructions..."
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={submitting}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Optional GitHub Issue #</label>
              <input
                type="number"
                className="form-input"
                placeholder="e.g. 5212"
                value={issueNumber}
                onChange={(e) => setIssueNumber(e.target.value)}
                disabled={submitting}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || loadingRepos || repositories.length === 0}
              style={{ width: '100%', padding: '0.75rem' }}
            >
              {submitting ? (
                <>
                  <div className="spinner" /> Analyzing Ticket...
                </>
              ) : (
                <>
                  <Send size={16} /> Submit for AI Analysis
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right Column: Pipeline Architecture Preview */}
        <div>
          <div className="panel" style={{ background: 'rgba(15, 23, 42, 0.6)' }}>
            <div className="panel-title" style={{ fontSize: '0.95rem', marginBottom: '0.85rem' }}>
              How SupportPilot Triage Works
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Layers size={14} color="var(--purple)" />
                <span><strong>1. Severity</strong>: Predicts ticket impact</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Search size={14} color="var(--primary)" />
                <span><strong>2. Duplicate</strong>: Cross-references issues</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Zap size={14} color="var(--warning)" />
                <span><strong>3. Root Cause</strong>: Correlates subsystem</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Search size={14} color="var(--success)" />
                <span><strong>4. Evidence</strong>: Retrieves resolved PRs</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <CheckSquare size={14} color="#60a5fa" />
                <span><strong>5. Resolution</strong>: Drafts step-by-step fix</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Shield size={14} color="var(--success)" />
                <span><strong>6. Verification</strong>: Validates claim facts</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Shield size={14} color="var(--purple)" />
                <span><strong>7. Confidence</strong>: Calibrates safety score</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.825rem' }}>
                <Send size={14} color="var(--text-muted)" />
                <span><strong>8. Routing</strong>: Directs to team or auto-resolves</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Real-time Polling & Stage Execution Display */}
      {activeRunId && (
        <div className="panel" style={{ marginTop: '1.5rem' }}>
          <div className="panel-header">
            <div>
              <div className="panel-title">LangGraph Execution Progress</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                Run ID: {activeRunId}
              </div>
            </div>
            {pipelineResult && (
              <span className="badge badge-success">
                <CheckCircle2 size={12} /> Execution Complete
              </span>
            )}
          </div>

          <PipelineStageProgress stages={stages} isCompleted={!submitting} />

          {pipelineResult && (
            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: '1rem' }}
              onClick={() => navigate(`/runs/${activeRunId}`)}
            >
              Open Full Results & Verification Package <ArrowRight size={16} />
            </button>
          )}
        </div>
      )}
    </div>
  );
};
