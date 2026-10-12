import type {
  DashboardSummary,
  RecentRunItem,
  Repository,
  IssueItem,
  PipelineResult,
  EvaluationRunSummary
} from '../types/api';

export const DEMO_REPOSITORIES: Repository[] = [
  {
    id: 101,
    github_repository_id: 8912401,
    owner: 'microsoft',
    name: 'vscode',
    full_name: 'microsoft/vscode',
    html_url: 'https://github.com/microsoft/vscode',
    enabled: true,
    webhook_enabled: true,
    auto_analysis_enabled: true,
    last_synced_at: '2026-08-30T18:45:00Z',
    issue_count: 1420,
    created_at: '2026-01-10T10:00:00Z'
  },
  {
    id: 102,
    github_repository_id: 4519203,
    owner: 'facebook',
    name: 'react',
    full_name: 'facebook/react',
    html_url: 'https://github.com/facebook/react',
    enabled: true,
    webhook_enabled: true,
    auto_analysis_enabled: true,
    last_synced_at: '2026-08-31T02:15:00Z',
    issue_count: 890,
    created_at: '2026-02-01T12:00:00Z'
  }
];

export const DEMO_DASHBOARD_SUMMARY: DashboardSummary = {
  total_tickets: 48,
  analyzed_today: 12,
  auto_resolution_recommendations: 28,
  human_escalations: 16,
  high_severity_tickets: 9,
  average_pipeline_latency_ms: 1420.5
};

export const DEMO_RECENT_RUNS: RecentRunItem[] = [
  {
    pipeline_run_id: 'run_demo_001',
    ticket_id: 1042,
    issue_number: 1042,
    title: 'Integrated terminal pty process crash on Windows 11 ARM64',
    repository_name: 'microsoft/vscode',
    severity: 'HIGH',
    duplicate_detected: 'NO',
    root_cause_cluster: 'Terminal Native PTY Subsystem',
    calibrated_confidence: 0.94,
    final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
    status: 'SUCCEEDED',
    created_at: '2026-08-31T08:30:00Z',
    total_latency_ms: 1250.0
  },
  {
    pipeline_run_id: 'run_demo_002',
    ticket_id: 1043,
    issue_number: 1043,
    title: 'Extension host unexpected memory leak after high concurrency workspace indexing',
    repository_name: 'microsoft/vscode',
    severity: 'HIGH',
    duplicate_detected: 'NO',
    root_cause_cluster: 'Extension Host Garbage Collector',
    calibrated_confidence: 0.68,
    final_decision: 'HUMAN_ESCALATION',
    status: 'ESCALATED',
    created_at: '2026-08-31T07:15:00Z',
    total_latency_ms: 1890.0
  },
  {
    pipeline_run_id: 'run_demo_003',
    ticket_id: 1044,
    issue_number: 1044,
    title: 'Git blame annotation tooltip fails to render on custom dark theme',
    repository_name: 'microsoft/vscode',
    severity: 'LOW',
    duplicate_detected: 'YES',
    root_cause_cluster: 'Workbench Decoration Layer',
    calibrated_confidence: 0.91,
    final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
    status: 'SUCCEEDED',
    created_at: '2026-08-31T06:40:00Z',
    total_latency_ms: 980.0
  },
  {
    pipeline_run_id: 'run_demo_004',
    ticket_id: 1045,
    issue_number: 1045,
    title: 'useTransition hook state mismatch during concurrent hydration in SSR',
    repository_name: 'facebook/react',
    severity: 'HIGH',
    duplicate_detected: 'NO',
    root_cause_cluster: 'React Fiber FiberReconciler',
    calibrated_confidence: 0.52,
    final_decision: 'HUMAN_ESCALATION',
    status: 'ESCALATED',
    created_at: '2026-08-30T22:10:00Z',
    total_latency_ms: 2100.0
  }
];

export const DEMO_ISSUES: IssueItem[] = [
  {
    id: 1042,
    issue_number: 1042,
    repository_id: 101,
    repository_name: 'microsoft/vscode',
    title: 'Integrated terminal pty process crash on Windows 11 ARM64',
    body_snippet: 'When starting PowerShell core inside the integrated terminal on Windows 11 ARM64 host, node-pty exits immediately with code 1.',
    state: 'OPEN',
    created_at: '2026-08-31T08:30:00Z',
    html_url: 'https://github.com/microsoft/vscode/issues/1042',
    severity: 'HIGH',
    duplicate_detected: false,
    latest_run_id: 'run_demo_001',
    latest_decision: 'AUTO_RESOLVE_RECOMMENDATION'
  },
  {
    id: 1043,
    issue_number: 1043,
    repository_id: 101,
    repository_name: 'microsoft/vscode',
    title: 'Extension host unexpected memory leak after high concurrency workspace indexing',
    body_snippet: 'RAM usage spikes to 16GB within 10 minutes when opening monorepos with typescript language service enabled.',
    state: 'OPEN',
    created_at: '2026-08-31T07:15:00Z',
    html_url: 'https://github.com/microsoft/vscode/issues/1043',
    severity: 'HIGH',
    duplicate_detected: false,
    latest_run_id: 'run_demo_002',
    latest_decision: 'HUMAN_ESCALATION'
  },
  {
    id: 1044,
    issue_number: 1044,
    repository_id: 101,
    repository_name: 'microsoft/vscode',
    title: 'Git blame annotation tooltip fails to render on custom dark theme',
    body_snippet: 'Hovering over gutter blame line displays transparent text box when using custom color themes.',
    state: 'OPEN',
    created_at: '2026-08-31T06:40:00Z',
    html_url: 'https://github.com/microsoft/vscode/issues/1044',
    severity: 'LOW',
    duplicate_detected: true,
    duplicate_of_issue_number: 892,
    latest_run_id: 'run_demo_003',
    latest_decision: 'AUTO_RESOLVE_RECOMMENDATION'
  }
];

export const DEMO_PIPELINE_RESULT_AUTO: PipelineResult = {
  pipeline_run_id: 'run_demo_001',
  ticket_id: 1042,
  status: 'SUCCEEDED',
  final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
  recommended_team: 'terminal-maintainers',
  calibrated_confidence: 0.94,
  routing_probability: 0.92,
  human_review_required: false,
  total_latency_ms: 1250.0,
  stage_latencies: {
    severity_classification: 120,
    duplicate_detection: 180,
    root_cause_clustering: 210,
    retrieval: 240,
    resolution_generation: 310,
    claim_verification: 110,
    confidence_calibration: 40,
    routing_decision: 40
  },
  stage_statuses: {
    severity_classification: 'SUCCEEDED',
    duplicate_detection: 'SUCCEEDED',
    root_cause_clustering: 'SUCCEEDED',
    retrieval: 'SUCCEEDED',
    resolution_generation: 'SUCCEEDED',
    claim_verification: 'SUCCEEDED',
    confidence_calibration: 'SUCCEEDED',
    routing_decision: 'SUCCEEDED'
  },
  severity: {
    predicted_severity: 'HIGH',
    prediction_score: 0.94,
    explanation: 'Contains technical terms matching critical terminal subsystem crash keywords.'
  },
  duplicate: {
    is_duplicate: false,
    similarity_score: 0.12,
    matching_issue_url: null
  },
  root_cause: {
    predicted_cluster_id: 14,
    cluster_name: 'Terminal Native PTY Subsystem',
    component: 'terminal',
    description: 'Issues relating to winpty/conpty native binary bindings on Windows host environments.'
  },
  retrieval: {
    evidence_completeness: 0.92,
    retrieved_cases: [
      {
        issue_id: 812,
        issue_number: 812,
        title: 'ConPTY exit code 1 crash on Windows 11 Insider Build',
        html_url: 'https://github.com/microsoft/vscode/issues/812',
        dense_similarity: 0.94,
        bm25_score: 18.4,
        rrf_score: 0.032,
        evidence_text_snippet: 'Fixed by updating node-pty native binding DLL loading path to check ARM64 system32 directory.'
      },
      {
        issue_id: 740,
        issue_number: 740,
        title: 'Integrated terminal blank screen on PowerShell startup',
        html_url: 'https://github.com/microsoft/vscode/issues/740',
        dense_similarity: 0.88,
        bm25_score: 14.2,
        rrf_score: 0.028,
        evidence_text_snippet: 'Set terminal.integrated.useConpty: true in settings.json to enforce modern Windows ConPTY API.'
      }
    ]
  },
  resolution: {
    summary: 'Update winpty/conpty native dependencies and ensure ARM64 binary paths are registered.',
    diagnosis: 'The terminal crash stems from winpty native DLL architecture mismatch when running under ARM64 Emulation mode.',
    recommended_resolution: '1. Update setting `terminal.integrated.useConpty` to `true`.\n2. Ensure node-pty v1.0.5 or newer is installed.',
    resolution_steps: [
      '1. Open settings.json and set "terminal.integrated.useConpty": true.',
      '2. Verify winpty.dll architecture matches Windows host target.'
    ],
    limitations: [
      'Applies only to Windows 10/11 environments.'
    ]
  },
  verification: {
    overall_faithfulness_status: 'FULLY_SUPPORTED',
    supported_count: 2,
    unsupported_count: 0,
    has_critical_failure: false,
    claims: [
      {
        claim_id: 'cl_1',
        claim_text: 'Setting terminal.integrated.useConpty to true resolves ConPTY initialization failures.',
        is_critical: true,
        verdict: 'SUPPORTED',
        support_strength: 0.96,
        source_ids: ['issue:812', 'pr:102']
      },
      {
        claim_id: 'cl_2',
        claim_text: 'ARM64 binary paths require node-pty v1.0.5 native module compilation.',
        is_critical: false,
        verdict: 'SUPPORTED',
        support_strength: 0.91,
        source_ids: ['issue:740']
      }
    ]
  },
  confidence: {
    calibrated_confidence: 0.94,
    threshold: 0.85,
    reason_codes: ['ALL_CLAIMS_SUPPORTED', 'HIGH_RETRIEVAL_SIMILARITY']
  },
  routing: {
    predicted_component: 'terminal',
    suggested_team: 'terminal-maintainers',
    routing_probability: 0.92
  },
  decision: {
    final_decision: 'AUTO_RESOLVE_RECOMMENDATION',
    recommended_team: 'terminal-maintainers',
    reason_codes: ['ALL_CLAIMS_SUPPORTED', 'CONFIDENCE_ABOVE_THRESHOLD']
  }
};

export const DEMO_EVALUATION_SUMMARY: EvaluationRunSummary = {
  evaluation_run_id: 'eval_run_20260830_benchmark_v1',
  created_at: '2026-08-30T12:00:00Z',
  dataset_version: 'github_support_eval_v1',
  code_version: 'v1.0.0',
  status: 'COMPLETED',
  summary: {
    evaluation_run_id: 'eval_run_20260830_benchmark_v1',
    dataset_version: 'github_support_eval_v1',
    total_tickets: 500,
    test_tickets: 150,
    severity_weighted_f1: 0.924,
    duplicate_f1: 0.895,
    retrieval_recall_at_5: 0.882,
    retrieval_mrr: 0.841,
    faithfulness_rate: 0.953,
    resolution_correctness: 0.876,
    brier_score: 0.042,
    ece_score: 0.018,
    routing_top1_accuracy: 0.910,
    auto_resolution_coverage: 0.620,
    false_auto_resolution_rate: 0.012,
    human_escalation_rate: 0.380,
    status: 'COMPLETED'
  }
};
