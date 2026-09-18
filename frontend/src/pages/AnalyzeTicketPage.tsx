import React, { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, APIClientError } from '../api/client';
import type { Repository, PipelineStageRun, PipelineResult } from '../types/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { DEMO_PIPELINE_RESULT_AUTO } from '../data/demoFixtures';
import { PipelineStageProgress } from '../components/PipelineStageProgress';
import {
  Send,
  AlertCircle,
  ArrowRight,
  Zap,
  FileText
} from 'lucide-react';

export const AnalyzeTicketPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { demoMode } = useWorkspace();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [loadingRepos, setLoadingRepos] = useState<boolean>(true);

  // Form State
  const [repositoryId, setRepositoryId] = useState<string>(searchParams.get('repo') || '');
  const [title, setTitle] = useState<string>(searchParams.get('title') || '');
  const [body, setBody] = useState<string>('');
  const [issueNumber, setIssueNumber] = useState<string>(searchParams.get('issue') || '');

  // Validation & Submission State
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
        if (repos.length > 0 && !repositoryId) {
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

  const startPolling = (runId: string) => {
    let attempts = 0;
    pollingRef.current = window.setInterval(async () => {
      attempts++;
      try {
        const [statusRes, stageRuns] = await Promise.all([
          api.getPipelineRunStatus(runId),
          api.getPipelineRunStages(runId).catch(() => []),
        ]);

        if (stageRuns && stageRuns.length > 0) {
          setStages(stageRuns);
        }

        if (
          statusRes.status === 'SUCCEEDED' ||
          statusRes.status === 'FAILED' ||
          statusRes.status === 'ESCALATED' ||
          attempts > 30
        ) {
          if (pollingRef.current) {
            window.clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
          const finalRes = await api.getPipelineRunResult(runId);
          setPipelineResult(finalRes);
          setSubmitting(false);
        }
      } catch (err) {
        console.warn('Polling error:', err);
      }
    }, 1500);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate() || submitting) return;

    setSubmitting(true);
    setSubmitError(null);
    setPipelineResult(null);
    setStages([]);

    try {
      if (demoMode) {
        // Fast mock demo execution
        setStages([
          { stage: 'classify_severity', status: 'RUNNING', latency_ms: 0 },
        ]);
        setTimeout(() => {
          setStages([
            { stage: 'classify_severity', status: 'SUCCEEDED', latency_ms: 120 },
            { stage: 'detect_duplicate', status: 'RUNNING', latency_ms: 0 },
          ]);
        }, 400);
        setTimeout(() => {
          setActiveRunId(DEMO_PIPELINE_RESULT_AUTO.pipeline_run_id);
          setPipelineResult(DEMO_PIPELINE_RESULT_AUTO);
          setSubmitting(false);
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

      // Start live status polling
      startPolling(result.pipeline_run_id);
    } catch (err: unknown) {
      if (demoMode) {
        setActiveRunId(DEMO_PIPELINE_RESULT_AUTO.pipeline_run_id);
        setPipelineResult(DEMO_PIPELINE_RESULT_AUTO);
        setSubmitting(false);
        return;
      }
      if (err instanceof APIClientError) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to initiate ticket investigation. Backend may be offline.');
      }
      setSubmitting(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Run Support Investigation</h1>
          <p className="page-subtitle">
            Submit an incoming support ticket to execute SupportPilot's 8-stage investigation pipeline: severity triage, duplicate detection, root-cause clustering, hybrid evidence retrieval, grounded synthesis, claim verification, and calibrated routing.
          </p>
        </div>
      </div>

      {submitError && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <div>{submitError}</div>
        </div>
      )}

      {/* Main Grid: Left Form / Right Pipeline Explanation & Live Status */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 1fr) minmax(340px, 1fr)', gap: '1.5rem', alignItems: 'start' }}>
        {/* Left: Input Form */}
        <div className="panel">
          <div className="panel-title" style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FileText size={17} color="var(--primary)" />
            <span>Support Ticket Input</span>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Repository Field */}
            <div className="form-group">
              <label className="form-label">
                Target Repository <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <select
                className="form-select"
                value={repositoryId}
                onChange={(e) => {
                  setRepositoryId(e.target.value);
                  if (formErrors.repositoryId) {
                    setFormErrors((prev) => ({ ...prev, repositoryId: undefined }));
                  }
                }}
                disabled={submitting || loadingRepos}
              >
                {loadingRepos ? (
                  <option>Loading repositories...</option>
                ) : repositories.length === 0 ? (
                  <option value="">No repositories registered</option>
                ) : (
                  repositories.map((repo) => (
                    <option key={repo.id} value={String(repo.id)}>
                      {repo.full_name || `${repo.owner}/${repo.name}`}
                    </option>
                  ))
                )}
              </select>
              {formErrors.repositoryId && <div className="form-error">{formErrors.repositoryId}</div>}
            </div>

            {/* Title Field */}
            <div className="form-group">
              <label className="form-label">
                Ticket Title / Summary <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Integrated terminal pty crash on Windows with exit code 1"
                value={title}
                onChange={(e) => {
                  setTitle(e.target.value);
                  if (formErrors.title) {
                    setFormErrors((prev) => ({ ...prev, title: undefined }));
                  }
                }}
                disabled={submitting}
              />
              {formErrors.title && <div className="form-error">{formErrors.title}</div>}
            </div>

            {/* Description / Body Field */}
            <div className="form-group">
              <label className="form-label">Issue Description / Stacktrace (Optional)</label>
              <textarea
                className="form-textarea"
                rows={5}
                placeholder="Paste ticket body, error codes, logs, reproduction steps, or environment details..."
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={submitting}
              />
            </div>

            {/* Issue Number (Optional) */}
            <div className="form-group">
              <label className="form-label">GitHub Issue # (Optional Reference)</label>
              <input
                type="number"
                className="form-input"
                placeholder="e.g. 1042"
                value={issueNumber}
                onChange={(e) => setIssueNumber(e.target.value)}
                disabled={submitting}
                style={{ width: '160px' }}
              />
            </div>

            {/* CTA Button */}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || loadingRepos || repositories.length === 0}
              style={{ width: '100%', padding: '0.65rem', marginTop: '0.5rem', fontSize: '0.85rem' }}
            >
              {submitting ? (
                <>
                  <div className="spinner" style={{ width: 14, height: 14 }} />
                  <span>Investigating Ticket...</span>
                </>
              ) : (
                <>
                  <Send size={14} />
                  <span>Run Investigation</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right: Pipeline Architecture / Live Stage Progress */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Zap size={17} color="var(--primary)" />
              <span>
                {activeRunId ? 'Investigation Execution Progress' : '8-Stage Pipeline Lifecycle'}
              </span>
            </div>
            {activeRunId && (
              <span className="badge badge-primary">
                Run: {activeRunId.slice(0, 14)}...
              </span>
            )}
          </div>

          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem', lineHeight: '1.45' }}>
            SupportPilot does not guess resolutions. It retrieves evidence from historical resolved cases, verifies each claim against repository ground truth, and calibrates confidence before proposing an action.
          </p>

          <PipelineStageProgress
            stages={stages}
            result={pipelineResult}
            isCompleted={!!pipelineResult && pipelineResult.status === 'SUCCEEDED'}
          />

          {pipelineResult && (
            <div
              style={{
                marginTop: '1.25rem',
                padding: '1rem',
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                borderRadius: 'var(--radius-sm)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ fontWeight: 700, color: '#34D399', fontSize: '0.9rem' }}>
                  Investigation Complete ({pipelineResult.total_latency_ms} ms)
                </div>
                <div style={{ fontSize: '0.785rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                  Decision: <strong>{pipelineResult.final_decision}</strong> | Confidence:{' '}
                  <strong>{(pipelineResult.calibrated_confidence * 100).toFixed(1)}%</strong>
                </div>
              </div>

              <button
                className="btn btn-primary"
                onClick={() => navigate(`/runs/${pipelineResult.pipeline_run_id}`)}
                style={{ fontSize: '0.785rem', whiteSpace: 'nowrap' }}
              >
                <span>View Full Audit</span>
                <ArrowRight size={13} />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
