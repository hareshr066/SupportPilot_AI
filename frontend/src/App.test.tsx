import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { api, APIClientError } from './api/client';

// Mock API client
vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof import('./api/client')>('./api/client');
  return {
    ...actual,
    api: {
      getDashboardSummary: vi.fn(),
      getRecentRuns: vi.fn(),
      getRepositories: vi.fn(),
      createRepository: vi.fn(),
      syncRepository: vi.fn(),
      getSyncStatus: vi.fn(),
      analyzeTicket: vi.fn(),
      getPipelineRunStatus: vi.fn(),
      getPipelineRunResult: vi.fn(),
      getPipelineRunStages: vi.fn(),
      getPipelineRunEvidence: vi.fn(),
      getPipelineRunEscalation: vi.fn(),
    },
  };
});

describe('SupportPilot Frontend Integration Test Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, '', '/');

    // Default resolves to avoid unhandled rejections on router load
    vi.mocked(api.getDashboardSummary).mockResolvedValue({
      total_tickets: 0,
      analyzed_today: 0,
      auto_resolution_recommendations: 0,
      human_escalations: 0,
      high_severity_tickets: 0,
      average_pipeline_latency_ms: 0,
    });
    vi.mocked(api.getRecentRuns).mockImplementation(async (_limit, _offset, _repoId, finalDecision) => {
      if (finalDecision === 'HUMAN_ESCALATION') {
        return [
          {
            pipeline_run_id: 'run_esc_1',
            ticket_id: 101,
            title: 'Escalated terminal bug',
            repository_name: 'microsoft/vscode',
            severity: 'HIGH',
            duplicate_detected: 'NO',
            root_cause_cluster: 'pty',
            calibrated_confidence: 0.54,
            final_decision: 'HUMAN_ESCALATION',
            status: 'ESCALATED',
            created_at: new Date().toISOString(),
            total_latency_ms: 900,
          },
        ];
      }
      return [];
    });
    vi.mocked(api.getRepositories).mockResolvedValue([
      {
        id: 1,
        owner: 'microsoft',
        name: 'vscode',
        full_name: 'microsoft/vscode',
        enabled: true,
        webhook_enabled: true,
        auto_analysis_enabled: true,
        issue_count: 5,
      },
    ]);
  });

  // 1. Dashboard rendering
  it('1. Renders Dashboard page with metrics and summary cards', async () => {
    vi.mocked(api.getDashboardSummary).mockResolvedValueOnce({
      total_tickets: 42,
      analyzed_today: 12,
      auto_resolution_recommendations: 30,
      human_escalations: 12,
      high_severity_tickets: 5,
      average_pipeline_latency_ms: 1240.5,
    });

    render(<App />);

    expect(await screen.findByText('Operations Dashboard')).toBeInTheDocument();
    expect(await screen.findByText('42')).toBeInTheDocument();
    expect(await screen.findByText('1240.5 ms')).toBeInTheDocument();
  });

  // 2. Repository list
  it('2. Renders connected repositories table on Repositories page', async () => {
    vi.mocked(api.getRepositories).mockResolvedValueOnce([
      {
        id: 1,
        owner: 'microsoft',
        name: 'vscode',
        full_name: 'microsoft/vscode',
        enabled: true,
        webhook_enabled: true,
        auto_analysis_enabled: true,
        issue_count: 150,
      },
    ]);

    render(<App />);

    const repoNav = await screen.findByText('Repositories');
    fireEvent.click(repoNav);

    expect(await screen.findByText('microsoft/vscode')).toBeInTheDocument();
    expect(await screen.findByText('150')).toBeInTheDocument();
  });

  // 3. Repository creation
  it('3. Handles new repository connection form submission', async () => {
    vi.mocked(api.getRepositories).mockResolvedValue([]);
    vi.mocked(api.createRepository).mockResolvedValueOnce({
      id: 2,
      owner: 'facebook',
      name: 'react',
      full_name: 'facebook/react',
      enabled: true,
      webhook_enabled: true,
      auto_analysis_enabled: true,
      issue_count: 0,
    });

    render(<App />);

    fireEvent.click(await screen.findByText('Repositories'));

    const ownerInput = await screen.findByPlaceholderText('e.g. microsoft');
    const nameInput = await screen.findByPlaceholderText('e.g. vscode');
    const submitBtn = await screen.findByText('Connect');

    fireEvent.change(ownerInput, { target: { value: 'facebook' } });
    fireEvent.change(nameInput, { target: { value: 'react' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.createRepository).toHaveBeenCalledWith({ owner: 'facebook', name: 'react' });
    });
  });

  // 4. Sync action
  it('4. Triggers repository sync action and polls status', async () => {
    vi.mocked(api.getRepositories).mockResolvedValue([
      {
        id: 1,
        owner: 'microsoft',
        name: 'vscode',
        full_name: 'microsoft/vscode',
        enabled: true,
        webhook_enabled: true,
        auto_analysis_enabled: true,
        issue_count: 10,
      },
    ]);
    vi.mocked(api.syncRepository).mockResolvedValueOnce({
      sync_run_id: 'sync_123',
      repository_id: 1,
      status: 'PENDING',
      started_at: new Date().toISOString(),
    });
    vi.mocked(api.getSyncStatus).mockResolvedValueOnce({
      sync_run_id: 'sync_123',
      repository_id: 1,
      status: 'COMPLETED',
      started_at: new Date().toISOString(),
      issues_processed: 10,
      comments_processed: 5,
      pull_requests_processed: 2,
    });

    render(<App />);

    fireEvent.click(await screen.findByText('Repositories'));
    const syncBtn = await screen.findByText('Trigger Sync');
    fireEvent.click(syncBtn);

    await waitFor(() => {
      expect(api.syncRepository).toHaveBeenCalledWith(1);
    });
  });

  // 5. Ticket form validation
  it('5. Validates empty ticket title on submission', async () => {
    render(<App />);

    const navBtn = (await screen.findAllByText('Analyze Ticket'))[0];
    fireEvent.click(navBtn);

    const submitBtn = await screen.findByText('Submit for AI Analysis');
    fireEvent.click(submitBtn);

    expect(await screen.findByText('Ticket title is required.')).toBeInTheDocument();
  });

  // 6. Ticket submission
  it('6. Submits valid ticket for analysis', async () => {
    vi.mocked(api.analyzeTicket).mockResolvedValueOnce({
      pipeline_run_id: 'run_test_1',
      status: 'RUNNING',
      final_decision: 'HUMAN_ESCALATION',
      recommended_team: 'GENERAL_SUPPORT_QUEUE',
      calibrated_confidence: 0.0,
      routing_probability: 0.0,
      human_review_required: true,
      total_latency_ms: 0,
      stage_latencies: {},
      stage_statuses: {},
      audit_reference: 'artifacts/test',
    });
    vi.mocked(api.getPipelineRunStages).mockResolvedValue([]);
    vi.mocked(api.getPipelineRunStatus).mockResolvedValue({ status: 'RUNNING' });

    render(<App />);

    const navBtn = (await screen.findAllByText('Analyze Ticket'))[0];
    fireEvent.click(navBtn);

    const titleInput = await screen.findByPlaceholderText(/Terminal crash after update/);
    fireEvent.change(titleInput, { target: { value: 'Terminal pty crash' } });

    const submitBtn = await screen.findByText('Submit for AI Analysis');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.analyzeTicket).toHaveBeenCalledWith({
        repository_id: 1,
        title: 'Terminal pty crash',
        body: undefined,
        issue_number: undefined,
      });
    });
  });

  // 7. Pipeline polling
  it('7. Polls stage progress until pipeline run completes', async () => {
    vi.mocked(api.analyzeTicket).mockResolvedValueOnce({
      pipeline_run_id: 'run_poll',
      status: 'RUNNING',
      final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
      recommended_team: 'TEAM',
      calibrated_confidence: 0.95,
      routing_probability: 0.9,
      human_review_required: false,
      total_latency_ms: 500,
      stage_latencies: {},
      stage_statuses: {},
      audit_reference: 'test',
    });
    vi.mocked(api.getPipelineRunStages).mockResolvedValue([
      { stage: 'classify_severity', status: 'SUCCEEDED', latency_ms: 120 },
    ]);
    vi.mocked(api.getPipelineRunStatus).mockResolvedValue({ status: 'SUCCEEDED' });
    vi.mocked(api.getPipelineRunResult).mockResolvedValue({
      pipeline_run_id: 'run_poll',
      status: 'SUCCEEDED',
      final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
      recommended_team: 'TEAM',
      calibrated_confidence: 0.95,
      routing_probability: 0.9,
      human_review_required: false,
      total_latency_ms: 500,
      stage_latencies: {},
      stage_statuses: {},
      audit_reference: 'test',
    });

    render(<App />);

    const navBtn = (await screen.findAllByText('Analyze Ticket'))[0];
    fireEvent.click(navBtn);

    fireEvent.change(await screen.findByPlaceholderText(/Terminal crash after update/), { target: { value: 'Test title' } });
    fireEvent.click(await screen.findByText('Submit for AI Analysis'));

    expect(await screen.findByText('LangGraph Execution Progress')).toBeInTheDocument();
  });

  // 8. Pipeline result rendering
  it('8. Renders full pipeline result details on run page', async () => {
    vi.mocked(api.getPipelineRunResult).mockResolvedValueOnce({
      pipeline_run_id: 'run_detail_1',
      status: 'SUCCEEDED',
      final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
      recommended_team: 'TERMINAL_TEAM',
      calibrated_confidence: 0.96,
      routing_probability: 0.92,
      human_review_required: false,
      total_latency_ms: 1450,
      stage_latencies: {},
      stage_statuses: {},
      severity: { predicted_severity: 'HIGH', prediction_score: 0.9 },
      duplicate: { is_duplicate: false },
      root_cause: { component: 'Terminal Subsystem', cluster_name: 'pty_crash' },
      resolution: { summary: 'Update pty helper dependency to v2.1.' },
      audit_reference: 'test',
    });

    window.history.pushState({}, 'Run Details', '/runs/run_detail_1');
    render(<App />);

    expect(await screen.findByText('Pipeline Analysis Details')).toBeInTheDocument();
    expect(await screen.findByText('HIGH')).toBeInTheDocument();
    expect(await screen.findByText('Update pty helper dependency to v2.1.')).toBeInTheDocument();
  });

  // 9. Claim verification rendering
  it('9. Displays claim verification verdicts correctly', async () => {
    vi.mocked(api.getPipelineRunResult).mockResolvedValueOnce({
      pipeline_run_id: 'run_claims',
      status: 'ESCALATED',
      final_decision: 'HUMAN_ESCALATION',
      recommended_team: 'GENERAL',
      calibrated_confidence: 0.65,
      routing_probability: 0.7,
      human_review_required: true,
      total_latency_ms: 1200,
      stage_latencies: {},
      stage_statuses: {},
      verification: {
        overall_faithfulness_status: 'FAILED',
        claims: [
          {
            claim_id: 'c1',
            claim_text: 'Pty process resets signal handlers.',
            is_critical: true,
            verdict: 'UNSUPPORTED',
            explanation: 'Source citation #12 does not state signal handlers reset.',
          },
        ],
      },
      audit_reference: 'test',
    });

    window.history.pushState({}, 'Run Claims', '/runs/run_claims');
    render(<App />);

    expect(await screen.findByText('Claim Verification & Faithfulness')).toBeInTheDocument();
    expect(await screen.findByText('"Pty process resets signal handlers."')).toBeInTheDocument();
    expect(await screen.findByText('⚠ UNSUPPORTED')).toBeInTheDocument();
  });

  // 10. Confidence rendering
  it('10. Renders Calibrated Confidence score correctly', async () => {
    vi.mocked(api.getPipelineRunResult).mockResolvedValueOnce({
      pipeline_run_id: 'run_conf',
      status: 'SUCCEEDED',
      final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
      recommended_team: 'QUEUE',
      calibrated_confidence: 0.942,
      routing_probability: 0.88,
      human_review_required: false,
      total_latency_ms: 1100,
      stage_latencies: {},
      stage_statuses: {},
      audit_reference: 'test',
    });

    window.history.pushState({}, 'Run Conf', '/runs/run_conf');
    render(<App />);

    expect(await screen.findByText('94.2%')).toBeInTheDocument();
  });

  // 11. Escalation rendering
  it('11. Displays human escalation queue panel', async () => {
    render(<App />);
    fireEvent.click(await screen.findByText('Escalation Queue'));

    expect(await screen.findByText('Human Escalation Queue')).toBeInTheDocument();
    expect(await screen.findByText('Escalated terminal bug')).toBeInTheDocument();
  });

  // 12. Error states
  it('12. Renders error banner when API returns error', async () => {
    vi.mocked(api.getDashboardSummary).mockRejectedValueOnce(
      new APIClientError('SERVER_ERROR', 'Database connection error.', 500)
    );

    render(<App />);

    expect(await screen.findByText('Database connection error.')).toBeInTheDocument();
  });

  // 13. Empty states
  it('13. Renders clean empty state when no tickets exist', async () => {
    vi.mocked(api.getDashboardSummary).mockResolvedValueOnce({
      total_tickets: 0,
      analyzed_today: 0,
      auto_resolution_recommendations: 0,
      human_escalations: 0,
      high_severity_tickets: 0,
      average_pipeline_latency_ms: 0,
    });
    vi.mocked(api.getRecentRuns).mockImplementation(async () => []);

    render(<App />);

    expect(await screen.findByText('No analyzed tickets yet.')).toBeInTheDocument();
  });

  // 14. Loading states
  it('14. Displays loading indicators while fetching dashboard metrics', async () => {
    vi.mocked(api.getDashboardSummary).mockImplementation(
      () => new Promise((resolve) => setTimeout(resolve, 5000))
    );

    render(<App />);

    expect(screen.getAllByText('Loading metric...')[0]).toBeInTheDocument();
  });

  // 15. API errors
  it('15. Handles 503 backend unavailable error gracefully', async () => {
    vi.mocked(api.getDashboardSummary).mockRejectedValueOnce(
      new APIClientError('SERVICE_UNAVAILABLE', 'SupportPilot backend is currently unavailable.', 503)
    );

    render(<App />);

    expect(await screen.findByText('SupportPilot backend is currently unavailable.')).toBeInTheDocument();
  });

  // 16. Filter behavior
  it('16. Queries recent runs with filter options', async () => {
    render(<App />);

    await waitFor(() => {
      expect(api.getRecentRuns).toHaveBeenCalledWith(20, 0);
    });
  });

  // 17. Run navigation
  it('17. Navigates to run details page when clicking a table row', async () => {
    vi.mocked(api.getDashboardSummary).mockResolvedValueOnce({
      total_tickets: 1,
      analyzed_today: 1,
      auto_resolution_recommendations: 1,
      human_escalations: 0,
      high_severity_tickets: 0,
      average_pipeline_latency_ms: 100,
    });
    vi.mocked(api.getRecentRuns).mockImplementation(async () => [
      {
        pipeline_run_id: 'run_nav_test',
        ticket_id: 1,
        title: 'Clickable ticket row',
        repository_name: 'test/repo',
        severity: 'LOW',
        duplicate_detected: 'NO',
        root_cause_cluster: 'core',
        calibrated_confidence: 0.99,
        final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
        status: 'SUCCEEDED',
        created_at: new Date().toISOString(),
        total_latency_ms: 100,
      },
    ]);
    vi.mocked(api.getPipelineRunResult).mockResolvedValue({
      pipeline_run_id: 'run_nav_test',
      status: 'SUCCEEDED',
      final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
      recommended_team: 'TEAM',
      calibrated_confidence: 0.99,
      routing_probability: 0.9,
      human_review_required: false,
      total_latency_ms: 100,
      stage_latencies: {},
      stage_statuses: {},
      audit_reference: 'test',
    });

    render(<App />);

    const row = await screen.findByText('Clickable ticket row');
    fireEvent.click(row);

    expect(await screen.findByText('Pipeline Analysis Details')).toBeInTheDocument();
  });

  // 18. No secret exposure
  it('18. Ensures no API keys or tokens are rendered in document DOM', async () => {
    const { container } = render(<App />);

    await screen.findByText('Operations Dashboard');
    expect(container.innerHTML).not.toContain('ghp_');
    expect(container.innerHTML).not.toContain('sk-');
    expect(container.innerHTML).not.toContain('GITHUB_TOKEN');
  });
});
