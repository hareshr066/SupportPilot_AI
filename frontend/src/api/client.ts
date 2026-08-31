import type {
  DashboardSummary,
  RecentRunItem,
  Repository,
  CreateRepositoryPayload,
  SyncResponse,
  SyncStatusResponse,
  TicketAnalyzePayload,
  PipelineResult,
  PipelineStageRun,
  APIErrorResponse,
  EvaluationListResponse,
  EvaluationRunSummary,
  EvaluationFailuresResponse,
  IssueItem,
  IssueDetail,
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export class APIClientError extends Error {
  public code: string;
  public status: number;
  public details?: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = 'APIClientError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: APIErrorResponse | null = null;
    try {
      errorData = await response.json();
    } catch {
      // Ignore JSON parse errors for non-JSON error responses
    }

    const code = errorData?.error?.code || 'HTTP_ERROR';
    const message = errorData?.error?.message || `HTTP ${response.status}: ${response.statusText}`;

    throw new APIClientError(code, message, response.status);
  }

  return response.json();
}

export const api = {
  // Health & System
  async getReadiness(): Promise<{ status: string; checks?: Record<string, string> }> {
    const res = await fetch(`${API_BASE_URL}/ready`);
    return handleResponse<{ status: string; checks?: Record<string, string> }>(res);
  },

  // Dashboard Endpoints
  async getDashboardSummary(): Promise<DashboardSummary> {
    const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/summary`);
    return handleResponse<DashboardSummary>(res);
  },

  async getRecentRuns(
    limit: number = 20,
    offset: number = 0,
    repositoryId?: number,
    finalDecision?: string
  ): Promise<RecentRunItem[]> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (repositoryId !== undefined) params.append('repository_id', String(repositoryId));
    if (finalDecision !== undefined) params.append('final_decision', finalDecision);

    const res = await fetch(`${API_BASE_URL}/api/v1/dashboard/recent-runs?${params.toString()}`);
    return handleResponse<RecentRunItem[]>(res);
  },

  // Repositories Endpoints
  async getRepositories(): Promise<Repository[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/repositories`);
    return handleResponse<Repository[]>(res);
  },

  async getRepository(repositoryId: number): Promise<Repository> {
    const res = await fetch(`${API_BASE_URL}/api/v1/repositories/${repositoryId}`);
    return handleResponse<Repository>(res);
  },

  async createRepository(payload: CreateRepositoryPayload): Promise<Repository> {
    const res = await fetch(`${API_BASE_URL}/api/v1/repositories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<Repository>(res);
  },

  async syncRepository(repositoryId: number): Promise<SyncResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/repositories/${repositoryId}/sync`, {
      method: 'POST',
    });
    return handleResponse<SyncResponse>(res);
  },

  async getSyncStatus(syncRunId: string): Promise<SyncStatusResponse> {
    const res = await fetch(`${API_BASE_URL}/api/v1/sync-runs/${syncRunId}`);
    return handleResponse<SyncStatusResponse>(res);
  },

  // Issues Endpoints
  async getIssues(
    limit: number = 20,
    offset: number = 0,
    repositoryId?: number,
    state?: string,
    search?: string
  ): Promise<{ total: number; limit: number; offset: number; issues: IssueItem[] }> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (repositoryId !== undefined) params.append('repository_id', String(repositoryId));
    if (state) params.append('state', state);
    if (search) params.append('search', search);

    const res = await fetch(`${API_BASE_URL}/api/v1/issues?${params.toString()}`);
    return handleResponse<{ total: number; limit: number; offset: number; issues: IssueItem[] }>(res);
  },

  async getIssue(issueId: number): Promise<IssueDetail> {
    const res = await fetch(`${API_BASE_URL}/api/v1/issues/${issueId}`);
    return handleResponse<IssueDetail>(res);
  },

  // Ticket Analysis & Pipeline Execution Endpoints
  async analyzeTicket(payload: TicketAnalyzePayload): Promise<PipelineResult> {
    const res = await fetch(`${API_BASE_URL}/api/v1/tickets/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse<PipelineResult>(res);
  },

  async listRuns(
    limit: number = 20,
    offset: number = 0,
    repositoryId?: number,
    statusFilter?: string,
    finalDecision?: string
  ): Promise<RecentRunItem[]> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (repositoryId !== undefined) params.append('repository_id', String(repositoryId));
    if (statusFilter) params.append('status', statusFilter);
    if (finalDecision) params.append('final_decision', finalDecision);

    const res = await fetch(`${API_BASE_URL}/api/v1/runs?${params.toString()}`);
    return handleResponse<RecentRunItem[]>(res);
  },

  async getPipelineRunStatus(runId: string): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}`);
    return handleResponse<{ status: string }>(res);
  },

  async getPipelineRunResult(runId: string): Promise<PipelineResult> {
    const res = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/result`);
    return handleResponse<PipelineResult>(res);
  },

  async getPipelineRunStages(runId: string): Promise<PipelineStageRun[]> {
    const res = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/stages`);
    return handleResponse<PipelineStageRun[]>(res);
  },

  async getPipelineRunEvidence(runId: string): Promise<unknown> {
    const res = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/evidence`);
    return handleResponse<unknown>(res);
  },

  async getPipelineRunEscalation(runId: string): Promise<unknown> {
    const res = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/escalation`);
    return handleResponse<unknown>(res);
  },

  // Evaluation Framework Endpoints
  async getEvaluations(limit: number = 20, offset: number = 0): Promise<EvaluationListResponse> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    const res = await fetch(`${API_BASE_URL}/api/v1/evaluations?${params.toString()}`);
    return handleResponse<EvaluationListResponse>(res);
  },

  async getEvaluationDetails(evalRunId: string): Promise<EvaluationRunSummary> {
    const res = await fetch(`${API_BASE_URL}/api/v1/evaluations/${evalRunId}`);
    return handleResponse<EvaluationRunSummary>(res);
  },

  async getEvaluationMetrics(evalRunId: string): Promise<{ evaluation_run_id: string; stage_metrics: Record<string, unknown> }> {
    const res = await fetch(`${API_BASE_URL}/api/v1/evaluations/${evalRunId}/metrics`);
    return handleResponse<{ evaluation_run_id: string; stage_metrics: Record<string, unknown> }>(res);
  },

  async getEvaluationFailures(evalRunId: string, limit: number = 50): Promise<EvaluationFailuresResponse> {
    const params = new URLSearchParams({ limit: String(limit) });
    const res = await fetch(`${API_BASE_URL}/api/v1/evaluations/${evalRunId}/failures?${params.toString()}`);
    return handleResponse<EvaluationFailuresResponse>(res);
  },
};
