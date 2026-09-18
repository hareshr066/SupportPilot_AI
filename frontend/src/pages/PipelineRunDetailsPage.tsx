import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { useWorkspace } from '../context/WorkspaceContext';
import type { PipelineResult, PipelineStageRun } from '../types/api';
import { DEMO_PIPELINE_RESULT_AUTO } from '../data/demoFixtures';
import { DecisionBanner } from '../components/DecisionBanner';
import { ClaimVerificationCard } from '../components/ClaimVerificationCard';
import { EvidenceCard } from '../components/EvidenceCard';
import { SeverityBadge } from '../components/SeverityBadge';
import { StatusBadge } from '../components/StatusBadge';
import { PipelineStageProgress } from '../components/PipelineStageProgress';
import {
  ArrowLeft,
  Copy,
  AlertTriangle,
  FileCheck,
  Clock
} from 'lucide-react';

export const PipelineRunDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { demoMode } = useWorkspace();
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [stages, setStages] = useState<PipelineStageRun[]>([]);
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
          setStages([
            { stage: 'classify_severity', status: 'SUCCEEDED', latency_ms: 120 },
            { stage: 'detect_duplicate', status: 'SUCCEEDED', latency_ms: 180 },
            { stage: 'discover_root_cause', status: 'SUCCEEDED', latency_ms: 210 },
            { stage: 'retrieve_cases', status: 'SUCCEEDED', latency_ms: 240 },
            { stage: 'generate_resolution', status: 'SUCCEEDED', latency_ms: 310 },
            { stage: 'verify_claims', status: 'SUCCEEDED', latency_ms: 110 },
            { stage: 'calculate_confidence', status: 'SUCCEEDED', latency_ms: 40 },
            { stage: 'route_ticket', status: 'SUCCEEDED', latency_ms: 40 },
          ]);
          setLoading(false);
        }, 200);
        return;
      }

      try {
        const [runResult, stageRuns] = await Promise.all([
          api.getPipelineRunResult(id),
          api.getPipelineRunStages(id).catch(() => []),
        ]);
        setResult(runResult);
        setStages(stageRuns || []);
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
[SupportPilot Investigation & Handoff Package]
Run ID: ${result.pipeline_run_id}
Final Decision: ${result.final_decision}
Recommended Team: ${result.recommended_team}
Calibrated Confidence: ${(result.calibrated_confidence * 100).toFixed(1)}%
Status: ${result.status}
Total Latency: ${result.total_latency_ms} ms

Severity: ${result.severity?.predicted_severity || 'NORMAL'}
Root Cause: ${result.root_cause?.component || 'General'} (${result.root_cause?.cluster_name || 'Unclustered'})
Duplicate: ${result.duplicate?.is_duplicate ? `Yes (#${result.duplicate.duplicate_of_issue_number})` : 'No'}

AI Suggested Resolution Summary:
${result.resolution?.summary || 'No resolution text.'}

Diagnosis:
${result.resolution?.diagnosis || 'N/A'}

Recommended Actions:
${result.resolution?.recommended_resolution || 'N/A'}
    `.trim();

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="panel" style={{ textAlign: 'center', padding: '3rem' }}>
        <div className="spinner" style={{ margin: '0 auto 0.75rem auto' }} />
        <p style={{ color: 'var(--text-muted)', fontSize: '0.815rem' }}>Loading 8-stage pipeline audit...</p>
      </div>
    );
  }

  if (error || !result) {
    return (
      <div>
        <button className="btn btn-secondary" onClick={() => navigate('/runs')} style={{ marginBottom: '1rem' }}>
          <ArrowLeft size={13} /> Back to Investigations
        </button>
        <div className="error-banner">
          <AlertTriangle size={15} />
          <div>{error || 'Pipeline run not found.'}</div>
        </div>
      </div>
    );
  }

  const ticketTitle =
    result.escalation_package?.ticket_summary ||
    (result as any).title ||
    `Support Ticket #${result.ticket_id || '1042'}`;

  const repoName = (result as any).repository_name || 'StudySync · Production';
  const severityVal = result.severity?.predicted_severity || result.severity?.predicted_label || 'HIGH';
  const confidenceVal = result.calibrated_confidence ?? 0.91;

  return (
    <div>
      {/* Navigation Bar & Actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <button className="btn btn-secondary" onClick={() => navigate('/runs')}>
          <ArrowLeft size={13} /> <span>Back to Investigations</span>
        </button>

        <button className="btn btn-secondary" onClick={copyEscalationSummary}>
          <Copy size={12} />
          <span>{copied ? 'Copied Package' : 'Copy Handoff Package'}</span>
        </button>
      </div>

      {/* TOP SHOWCASE BAR: Ticket ID, Title, Repo, Badges, Confidence */}
      <div
        className="panel"
        style={{
          borderTop: '2px solid var(--primary)',
          marginBottom: '1rem',
          padding: '1rem 1.25rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 500px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem', flexWrap: 'wrap' }}>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.725rem',
                  color: 'var(--primary)',
                  background: 'rgba(56, 189, 248, 0.08)',
                  padding: '0.1rem 0.4rem',
                  borderRadius: '2px',
                  fontWeight: 600,
                }}
              >
                ID: {result.pipeline_run_id}
              </span>

              <span style={{ fontSize: '0.725rem', color: 'var(--text-dim)' }}>•</span>

              <span style={{ fontSize: '0.785rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                {repoName}
              </span>

              <span style={{ fontSize: '0.725rem', color: 'var(--text-dim)' }}>•</span>

              <SeverityBadge severity={severityVal} />

              <StatusBadge decision={result.final_decision} status={result.status} />
            </div>

            {/* Ticket Title */}
            <h1 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#FFFFFF', letterSpacing: '-0.015em', lineHeight: 1.3 }}>
              {ticketTitle}
            </h1>
          </div>

          {/* Right Side: Calibrated Confidence Badge */}
          <div
            style={{
              background: 'var(--bg-card-subtle)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-xs)',
              padding: '0.65rem 0.95rem',
              textAlign: 'right',
              minWidth: '150px',
            }}
          >
            <div style={{ fontSize: '0.685rem', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-dim)' }}>
              Confidence
            </div>
            <div
              style={{
                fontSize: '1.45rem',
                fontWeight: 800,
                fontFamily: 'var(--font-mono)',
                color: confidenceVal >= 0.85 ? 'var(--success)' : 'var(--warning)',
              }}
            >
              {(confidenceVal * 100).toFixed(1)}%
            </div>
            <div style={{ fontSize: '0.685rem', color: 'var(--text-muted)' }}>
              Threshold: {((result.confidence?.threshold || 0.85) * 100).toFixed(0)}%
            </div>
          </div>
        </div>

        {/* Compact Summary Row */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
            gap: '0.75rem',
            marginTop: '0.85rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '0.785rem',
          }}
        >
          <div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.685rem', textTransform: 'uppercase' }}>Severity</div>
            <div style={{ fontWeight: 600, marginTop: '0.15rem' }}>{severityVal}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.685rem', textTransform: 'uppercase' }}>Duplicate</div>
            <div style={{ fontWeight: 600, marginTop: '0.15rem' }}>
              {result.duplicate?.is_duplicate ? 'Yes' : 'Unique (No)'}
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.685rem', textTransform: 'uppercase' }}>Root Cause</div>
            <div style={{ fontWeight: 600, marginTop: '0.15rem' }}>
              {result.root_cause?.component || result.root_cause?.cluster_name || 'Core'}
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.685rem', textTransform: 'uppercase' }}>Total Latency</div>
            <div style={{ fontWeight: 600, fontFamily: 'var(--font-mono)', marginTop: '0.15rem' }}>
              {result.total_latency_ms} ms
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--text-dim)', fontSize: '0.685rem', textTransform: 'uppercase' }}>Routing Queue</div>
            <div style={{ fontWeight: 600, color: 'var(--primary)', marginTop: '0.15rem' }}>
              {result.recommended_team || 'general-support'}
            </div>
          </div>
        </div>
      </div>

      {/* 8-STAGE INVESTIGATION PIPELINE STEPPER */}
      <div className="panel" style={{ marginBottom: '1rem' }}>
        <div className="panel-header">
          <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <Clock size={15} color="var(--primary)" />
            <span>Investigation Pipeline (8 Stages)</span>
          </div>
          <span style={{ fontSize: '0.725rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            Click stage for audit breakdown
          </span>
        </div>

        <PipelineStageProgress stages={stages} result={result} isCompleted={result.status === 'SUCCEEDED'} />
      </div>

      {/* TWO-COLUMN INVESTIGATION WORKSPACE LAYOUT */}
      <div className="investigation-grid">
        {/* MAIN COLUMN: Grounded Resolution & Evidence */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Grounded Resolution */}
          {result.resolution && (
            <div className="panel" style={{ marginBottom: 0 }}>
              <div className="panel-header">
                <div>
                  <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                    <FileCheck size={15} color="var(--primary)" />
                    <span>Grounded Resolution</span>
                  </div>
                  <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                    Citation-enforced technical resolution synthesized from indexed historical PRs and issues.
                  </div>
                </div>
                <span className="badge badge-success">Grounded</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
                {/* 1. Summary */}
                {result.resolution.summary && (
                  <div className="resolution-section-block">
                    <div className="resolution-section-title" style={{ color: 'var(--primary)' }}>
                      Summary
                    </div>
                    <p style={{ color: 'var(--text-main)', fontSize: '0.825rem', lineHeight: '1.45' }}>
                      {result.resolution.summary}
                    </p>
                  </div>
                )}

                {/* 2. Diagnosis */}
                {result.resolution.diagnosis && (
                  <div className="resolution-section-block">
                    <div className="resolution-section-title" style={{ color: 'var(--text-secondary)' }}>
                      Diagnosis
                    </div>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.815rem', lineHeight: '1.45' }}>
                      {result.resolution.diagnosis}
                    </p>
                  </div>
                )}

                {/* 3. Recommended Actions */}
                {result.resolution.recommended_resolution && (
                  <div className="resolution-section-block" style={{ borderLeft: '3px solid var(--success)' }}>
                    <div className="resolution-section-title" style={{ color: 'var(--success)' }}>
                      Recommended Action
                    </div>
                    <p
                      style={{
                        background: 'var(--bg-input)',
                        border: '1px solid var(--border-color)',
                        padding: '0.65rem 0.85rem',
                        borderRadius: 'var(--radius-xs)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.8rem',
                        color: '#34D399',
                        lineHeight: '1.45',
                      }}
                    >
                      {result.resolution.recommended_resolution}
                    </p>
                  </div>
                )}

                {/* 4. Step-by-Step Fix */}
                {result.resolution.resolution_steps && result.resolution.resolution_steps.length > 0 && (
                  <div className="resolution-section-block">
                    <div className="resolution-section-title" style={{ color: '#FFFFFF' }}>
                      Step-by-Step Fix
                    </div>
                    <ol style={{ paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {result.resolution.resolution_steps.map((step, i) => (
                        <li key={i} style={{ fontSize: '0.815rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                          {step}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {/* Limitations */}
                {result.resolution.limitations && result.resolution.limitations.length > 0 && (
                  <div className="resolution-section-block" style={{ borderLeft: '3px solid var(--warning)' }}>
                    <div className="resolution-section-title" style={{ color: 'var(--warning)' }}>
                      Limitations & Edge Cases
                    </div>
                    <ul style={{ paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                      {result.resolution.limitations.map((lim, i) => (
                        <li key={i} style={{ fontSize: '0.785rem', color: 'var(--text-muted)' }}>
                          {lim}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Evidence Section */}
          <EvidenceCard retrievedCases={result.retrieval?.retrieved_cases || []} />
        </div>

        {/* SIDEBAR COLUMN: Decision Panel, Confidence & Claim Verification */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Decision Panel */}
          <DecisionBanner
            decision={result.final_decision}
            recommendedTeam={result.recommended_team}
            calibratedConfidence={result.calibrated_confidence}
            reasonCodes={result.decision?.reason_codes || []}
          />

          {/* Claim Verification Card */}
          <ClaimVerificationCard
            claims={result.verification?.claims || []}
            overallStatus={result.verification?.overall_faithfulness_status}
          />

          {/* Routing & Maintainer Handoff */}
          <div className="panel" style={{ marginBottom: 0 }}>
            <div className="panel-header">
              <div className="panel-title">Routing & Handoff</div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem', fontSize: '0.8rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Target Queue:</span>
                <span style={{ fontWeight: 600, color: '#FFFFFF', fontFamily: 'var(--font-mono)' }}>
                  {result.recommended_team || 'terminal-maintainers'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.45rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Routing Prob:</span>
                <span style={{ fontWeight: 600, color: 'var(--primary)', fontFamily: 'var(--font-mono)' }}>
                  {((result.routing_probability || 0.88) * 100).toFixed(1)}%
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Human Review:</span>
                <span className={`badge ${result.human_review_required ? 'badge-warning' : 'badge-success'}`}>
                  {result.human_review_required ? 'REQUIRED' : 'OPTIONAL'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
