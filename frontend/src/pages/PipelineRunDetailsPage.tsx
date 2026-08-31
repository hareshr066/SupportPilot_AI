import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { PipelineResult } from '../types/api';
import { DEMO_PIPELINE_RESULT_AUTO } from '../data/demoFixtures';
import { DecisionBanner } from '../components/DecisionBanner';
import { ClaimVerificationCard } from '../components/ClaimVerificationCard';
import { EvidenceCard } from '../components/EvidenceCard';
import { SeverityBadge } from '../components/SeverityBadge';
import { PipelineStageProgress } from '../components/PipelineStageProgress';
import {
  Flame,
  GitPullRequest,
  ArrowLeft,
  ShieldCheck,
  Zap,
  Copy,
  AlertTriangle,
  FileCheck
} from 'lucide-react';

export const PipelineRunDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { demoMode } = useWorkspace();
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    async function fetchResult() {
      if (!id) return;
      setLoading(true);
      setError(null);

      if (demoMode || id.startsWith('run_demo_')) {
        setTimeout(() => {
          setResult(DEMO_PIPELINE_RESULT_AUTO);
          setLoading(false);
        }, 200);
        return;
      }

      try {
        const data = await api.getPipelineRunResult(id);
        setResult(data);
      } catch (err: unknown) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('Failed to load pipeline run details.');
        }
      } finally {
        setLoading(false);
      }
    }
    fetchResult();
  }, [id, demoMode]);

  const copyEscalationSummary = () => {
    if (!result) return;
    const text = `
[SupportPilot Handoff Package]
Run ID: ${result.pipeline_run_id}
Final Decision: ${result.final_decision}
Recommended Team: ${result.recommended_team}
Calibrated Confidence: ${(result.calibrated_confidence * 100).toFixed(1)}%

Severity: ${result.severity?.predicted_severity || 'NORMAL'}
Root Cause: ${result.root_cause?.component || 'General'} (${result.root_cause?.cluster_name || 'Unclustered'})
Duplicate: ${result.duplicate?.is_duplicate ? `Yes (#${result.duplicate.duplicate_of_issue_number})` : 'No'}

AI Suggested Resolution Summary:
${result.resolution?.summary || 'No resolution text.'}

Reason Codes:
${JSON.stringify(result.decision?.reason_codes || [], null, 2)}
    `.trim();

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: '4rem' }}>
        <div className="spinner" style={{ margin: '0 auto 1rem auto', width: '24px', height: '24px' }} />
        <p style={{ color: 'var(--text-muted)' }}>Loading pipeline run audit details...</p>
      </div>
    );
  }

  if (error || !result) {
    return (
      <div>
        <button className="btn btn-secondary" onClick={() => navigate('/')} style={{ marginBottom: '1.25rem' }}>
          <ArrowLeft size={14} /> Back to Overview
        </button>
        <div className="error-banner">
          <AlertTriangle size={16} />
          <div>{error || 'Pipeline run not found.'}</div>
        </div>
      </div>
    );
  }

  const isAutoResolve =
    result.final_decision === 'AUTO_RESOLVE_RECOMMENDATION' || result.final_decision === 'AUTO_RESOLVE';

  // Construct stages list for progress bar
  const mockStages = [
    { stage: 'classify_severity', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.severity_classification || 120 },
    { stage: 'detect_duplicate', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.duplicate_detection || 180 },
    { stage: 'discover_root_cause', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.root_cause_clustering || 210 },
    { stage: 'retrieve_cases', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.retrieval || 240 },
    { stage: 'generate_resolution', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.resolution_generation || 310 },
    { stage: 'verify_claims', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.claim_verification || 110 },
    { stage: 'calculate_confidence', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.confidence_calibration || 40 },
    { stage: 'route_ticket', status: 'SUCCEEDED' as const, latency_ms: result.stage_latencies?.routing_decision || 40 },
  ];

  return (
    <div>
      <button className="btn btn-secondary" onClick={() => navigate('/')} style={{ marginBottom: '1.25rem' }}>
        <ArrowLeft size={14} /> Back to Overview
      </button>

      {/* Page Header */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h1 className="page-title">Issue Analysis Audit & Handoff</h1>
            <span
              className={`badge ${
                isAutoResolve
                  ? 'badge-success'
                  : result.status === 'FAILED'
                  ? 'badge-danger'
                  : 'badge-warning'
              }`}
              style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
            >
              {isAutoResolve ? 'Auto-Resolution Recommended' : 'Human Review Required'}
            </span>
          </div>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Run ID: {result.pipeline_run_id} | Total Latency: {result.total_latency_ms} ms
          </p>
        </div>
      </div>

      {/* Decision Banner */}
      <DecisionBanner
        decision={result.final_decision}
        recommendedTeam={result.recommended_team}
      />

      {/* Pipeline Stage Execution Timeline */}
      <div className="panel">
        <div className="panel-title" style={{ marginBottom: '0.75rem' }}>
          8-Stage LangGraph Pipeline Execution Audit
        </div>
        <PipelineStageProgress stages={mockStages} isCompleted={true} />
      </div>

      {/* Core Metrics Grid */}
      <div className="grid-kpi" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))' }}>
        {/* Severity Card */}
        <div className="kpi-card">
          <div className="kpi-header">
            <span>Severity</span>
            <Flame size={16} color="var(--danger)" />
          </div>
          <div className="kpi-value" style={{ fontSize: '1.3rem' }}>
            <SeverityBadge
              severity={result.severity?.predicted_severity || result.severity?.predicted_label || 'NORMAL'}
            />
          </div>
          {result.severity?.prediction_score !== undefined && (
            <div className="kpi-subtext">
              Model Score: {(result.severity.prediction_score * 100).toFixed(1)}%
            </div>
          )}
        </div>

        {/* Duplicate Card */}
        <div className="kpi-card">
          <div className="kpi-header">
            <span>Duplicate Detection</span>
            <GitPullRequest size={16} color="var(--purple)" />
          </div>
          <div className="kpi-value" style={{ fontSize: '1.3rem' }}>
            {result.duplicate?.is_duplicate ? (
              <span className="badge badge-danger">CONFIRMED DUPLICATE</span>
            ) : (
              <span className="badge badge-neutral">NO DUPLICATE</span>
            )}
          </div>
          {result.duplicate?.is_duplicate && (
            <div className="kpi-subtext">
              Matched Issue: #{result.duplicate.duplicate_of_issue_number || 'N/A'} (
              {((result.duplicate.similarity_score || 0.94) * 100).toFixed(0)}% similarity)
            </div>
          )}
        </div>

        {/* Root Cause Card */}
        <div className="kpi-card">
          <div className="kpi-header">
            <span>Root Cause Cluster</span>
            <Zap size={16} color="var(--primary)" />
          </div>
          <div className="kpi-value" style={{ fontSize: '1.1rem', fontFamily: 'var(--font-mono)' }}>
            {result.root_cause?.component || result.root_cause?.cluster_name || 'General'}
          </div>
          <div className="kpi-subtext">
            Cluster ID: #{result.root_cause?.predicted_cluster_id ?? 14}
          </div>
        </div>

        {/* Calibrated Confidence Card */}
        <div className="kpi-card">
          <div className="kpi-header">
            <span>Calibrated Confidence</span>
            <ShieldCheck size={16} color="var(--success)" />
          </div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>
            {(result.calibrated_confidence * 100).toFixed(1)}%
          </div>
          <div className="kpi-subtext">
            Safety Threshold: {((result.confidence?.threshold || 0.85) * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      {/* AI Suggested Resolution */}
      {result.resolution && (
        <div className="panel" style={{ marginTop: '1.25rem' }}>
          <div className="panel-title" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <FileCheck size={16} color="var(--accent-blue)" />
            <span>AI Grounded Resolution Recommendation</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {result.resolution.summary && (
              <div>
                <h4 style={{ color: 'var(--accent-blue)', marginBottom: '0.25rem', fontSize: '0.85rem' }}>Summary</h4>
                <p style={{ color: 'var(--text-main)', fontSize: '0.85rem' }}>{result.resolution.summary}</p>
              </div>
            )}

            {result.resolution.diagnosis && (
              <div>
                <h4 style={{ color: 'var(--text-main)', marginBottom: '0.25rem', fontSize: '0.85rem' }}>Diagnosis</h4>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.825rem' }}>{result.resolution.diagnosis}</p>
              </div>
            )}

            {result.resolution.recommended_resolution && (
              <div>
                <h4 style={{ color: 'var(--success)', marginBottom: '0.25rem', fontSize: '0.85rem' }}>
                  Recommended Action
                </h4>
                <p
                  style={{
                    background: '#F8FAFC',
                    border: '1px solid var(--border-color)',
                    padding: '0.65rem 0.85rem',
                    borderRadius: 'var(--radius-sm)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.825rem',
                  }}
                >
                  {result.resolution.recommended_resolution}
                </p>
              </div>
            )}

            {result.resolution.resolution_steps && result.resolution.resolution_steps.length > 0 && (
              <div>
                <h4 style={{ color: 'var(--text-main)', marginBottom: '0.35rem', fontSize: '0.85rem' }}>
                  Step-by-Step Fix Instructions
                </h4>
                <ol style={{ paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                  {result.resolution.resolution_steps.map((step, i) => (
                    <li key={i} style={{ fontSize: '0.825rem', color: 'var(--text-muted)' }}>
                      {step}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Claim Verification Panel */}
      <ClaimVerificationCard
        claims={result.verification?.claims || []}
        overallStatus={result.verification?.overall_faithfulness_status}
      />

      {/* Evidence Panel */}
      <EvidenceCard retrievedCases={result.retrieval?.retrieved_cases || []} />

      {/* Escalation Package & Handoff */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <div className="panel-title">Human Handoff & Escalation Package</div>
            <div style={{ fontSize: '0.775rem', color: 'var(--text-muted)' }}>
              Structured handoff payload for engineering maintainers
            </div>
          </div>
          <button className="btn btn-secondary" onClick={copyEscalationSummary} style={{ fontSize: '0.775rem' }}>
            <Copy size={13} />
            {copied ? 'Copied to Clipboard!' : 'Copy Handoff Package'}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <h4 style={{ color: 'var(--text-muted)', fontSize: '0.725rem', textTransform: 'uppercase' }}>
              Suggested Engineering Team
            </h4>
            <div style={{ fontSize: '1rem', fontWeight: 700, margin: '0.2rem 0' }}>
              {result.recommended_team || 'terminal-maintainers'}
            </div>
          </div>
          <div>
            <h4 style={{ color: 'var(--text-muted)', fontSize: '0.725rem', textTransform: 'uppercase' }}>
              Routing Probability
            </h4>
            <div style={{ fontSize: '1rem', fontWeight: 700, margin: '0.2rem 0', color: 'var(--accent-blue)' }}>
              {(result.routing_probability * 100).toFixed(1)}%
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
