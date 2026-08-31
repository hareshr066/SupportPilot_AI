export interface Repository {
  id: number;
  github_repository_id?: number | null;
  owner: str;
  name: str;
  full_name: str;
  html_url?: string | null;
  enabled: boolean;
  webhook_enabled: boolean;
  auto_analysis_enabled: boolean;
  last_synced_at?: string | null;
  issue_count: number;
  created_at?: string | null;
}

export interface ReadinessResponse {
  status: 'ready' | 'not_ready' | string;
  checks?: Record<string, string>;
}

export type str = string;

export interface IssueItem {
  id: number;
  issue_number: number;
  repository_id: number;
  repository_name: str;
  title: str;
  body_snippet: str;
  state: str;
  created_at: str;
  closed_at?: str | null;
  html_url: str;
  severity: str;
  duplicate_detected: boolean;
  duplicate_of_issue_number?: number | null;
  latest_run_id?: str | null;
  latest_decision?: str | null;
}

export interface IssueDetail {
  id: number;
  issue_number: number;
  repository_id: number;
  repository_name: str;
  title: str;
  body: str;
  state: str;
  created_at: str;
  closed_at?: str | null;
  html_url: str;
  severity: str;
  duplicate_detected: boolean;
  duplicate_of_issue_number?: number | null;
  comments_count: number;
  comments: Array<{
    id: number;
    body: str;
    created_at: str;
    author: str;
    html_url?: str | null;
  }>;
  pull_requests: Array<{
    id: number;
    pr_number: number;
    html_url?: str | null;
  }>;
  latest_run_id?: str | null;
  latest_decision?: str | null;
}

export interface CreateRepositoryPayload {
  owner: string;
  name: string;
}

export interface SyncResponse {
  sync_run_id: string;
  repository_id: number;
  status: string;
  started_at: string;
}

export interface SyncStatusResponse {
  sync_run_id: string;
  repository_id: number;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PARTIAL';
  started_at: string;
  completed_at?: string | null;
  issues_processed: number;
  comments_processed: number;
  pull_requests_processed: number;
  error_summary?: string | null;
}

export interface TicketAnalyzePayload {
  repository_id: number;
  title: string;
  body?: string;
  issue_number?: number | null;
}

export interface DashboardSummary {
  total_tickets: number;
  analyzed_today: number;
  auto_resolution_recommendations: number;
  human_escalations: number;
  high_severity_tickets: number;
  average_pipeline_latency_ms: number;
}

export interface RecentRunItem {
  pipeline_run_id: string;
  ticket_id?: number | null;
  issue_number?: number | null;
  title: string;
  repository_name: string;
  severity: string;
  duplicate_detected: string;
  root_cause_cluster: string;
  calibrated_confidence: number;
  final_decision: string;
  status: string;
  created_at: string;
  total_latency_ms: number;
}

export interface PipelineStageRun {
  stage: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'SKIPPED';
  latency_ms: number;
  started_at?: string | null;
  completed_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
}

export interface EvidenceReferenceItem {
  issue_id: number;
  issue_number?: number | null;
  title: string;
  html_url?: string | null;
  dense_similarity: number;
  bm25_score: number;
  rrf_score: number;
  evidence_text_snippet: string;
}

export interface ClaimVerificationItem {
  claim_id: string;
  claim_text: string;
  is_critical: boolean;
  is_destructive?: boolean;
  verdict: 'SUPPORTED' | 'UNSUPPORTED' | 'CONTRADICTED' | 'PARTIALLY_SUPPORTED' | 'UNCLEAR';
  support_strength?: number;
  source_ids?: string[];
  explanation?: string;
}

export interface PipelineResult {
  pipeline_run_id: string;
  ticket_id?: number | null;
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'ESCALATED';
  final_decision: 'AUTO_RESOLVE_RECOMMENDATION' | 'HUMAN_ESCALATION' | 'ROUTE_TO_TEAM' | string;
  recommended_team: string;
  calibrated_confidence: number;
  routing_probability: number;
  human_review_required: boolean;
  total_latency_ms: number;
  stage_latencies: Record<string, number>;
  stage_statuses: Record<string, string>;
  severity?: {
    predicted_severity?: string;
    predicted_label?: string;
    prediction_score?: number;
    explanation?: string;
  } | null;
  duplicate?: {
    is_duplicate?: boolean;
    duplicate_of_issue_number?: number | null;
    similarity_score?: number;
    matching_issue_url?: string | null;
  } | null;
  root_cause?: {
    predicted_cluster_id?: number;
    cluster_name?: string;
    component?: string;
    description?: string;
  } | null;
  retrieval?: {
    retrieved_cases?: EvidenceReferenceItem[];
    evidence_completeness?: number;
  } | null;
  resolution?: {
    summary?: string;
    diagnosis?: string;
    recommended_resolution?: string;
    resolution_steps?: string[];
    limitations?: string[];
  } | null;
  verification?: {
    claims?: ClaimVerificationItem[];
    overall_faithfulness_status?: string;
    supported_count?: number;
    unsupported_count?: number;
    has_critical_failure?: boolean;
  } | null;
  confidence?: {
    calibrated_confidence?: number;
    threshold?: number;
    reason_codes?: string[];
  } | null;
  routing?: {
    predicted_component?: string;
    suggested_team?: string;
    routing_probability?: number;
  } | null;
  decision?: {
    final_decision?: string;
    recommended_team?: string;
    reason_codes?: string[];
  } | null;
  escalation_package?: {
    ticket_summary?: string;
    severity?: string;
    root_cause?: string;
    suggested_owner?: string;
    reason_codes?: string[];
    verification_problems?: string[];
  } | null;
  errors?: Array<{ code?: string; message?: string }>;
  audit_reference?: string;
}

export interface APIErrorResponse {
  error: {
    code: string;
    message: string;
    request_id?: string;
  };
}

export interface EvaluationRunSummary {
  evaluation_run_id: string;
  created_at: string;
  dataset_version: string;
  code_version: string;
  status: string;
  summary: {
    evaluation_run_id: string;
    dataset_version: string;
    total_tickets: number;
    test_tickets: number;
    severity_weighted_f1?: number | string;
    duplicate_f1?: number | string;
    retrieval_recall_at_5?: number | string;
    retrieval_mrr?: number | string;
    faithfulness_rate?: number | string;
    resolution_correctness?: number | string;
    brier_score?: number | string;
    ece_score?: number | string;
    routing_top1_accuracy?: number | string;
    auto_resolution_coverage?: number | string;
    false_auto_resolution_rate?: number | string;
    human_escalation_rate?: number | string;
    status: string;
  };
}

export interface EvaluationListResponse {
  total: number;
  limit: number;
  offset: number;
  evaluations: EvaluationRunSummary[];
}

export interface EvaluationFailureItem {
  ticket_id?: number | null;
  failed_stage: string;
  failure_category: string;
  reason_code: string;
  predicted_result?: unknown;
  ground_truth?: unknown;
  evidence?: unknown;
}

export interface EvaluationFailuresResponse {
  evaluation_run_id: string;
  total_failures: number;
  failures: EvaluationFailureItem[];
}

