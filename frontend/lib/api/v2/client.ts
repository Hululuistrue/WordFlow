import type {
  AbuseReport,
  AbuseReportCreateRequest,
  AbuseReportListResponse,
  AbuseStatus,
  AuthTokenResponse,
  ExportAsset,
  ExportCreateRequest,
  ExportDownloadResponse,
  Job,
  JobCreateRequest,
  JobListResponse,
  JobStatus,
  TranscriptDetail,
  TranscriptVersion,
  UploadCompleteResponse,
  UploadContentResponse,
  UploadInitRequest,
  UploadInitResponse,
  UsageSummaryResponse,
  Workspace,
  WorkspaceListResponse,
  YouTubeConnectResponse
} from "./types";

type HttpMethod = "GET" | "POST" | "PATCH";

export type ClientOptions = {
  baseUrl?: string;
  getAccessToken?: () => string | null | undefined;
};

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

function toQueryString(query?: Record<string, string | number | boolean | undefined | null>): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export class TranscriptProV2Client {
  private readonly baseUrl: string;
  private readonly getAccessToken?: () => string | null | undefined;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl || process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    this.getAccessToken = options.getAccessToken;
  }

  resolveUrl(path: string): string {
    if (/^https?:\/\//i.test(path)) return path;
    return `${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  }

  private async request<T>(
    method: HttpMethod,
    path: string,
    body?: unknown,
    query?: Record<string, string | number | boolean | undefined | null>,
    auth: boolean = true
  ): Promise<T> {
    const headers: HeadersInit = {
      "Content-Type": "application/json"
    };
    if (auth && this.getAccessToken) {
      const token = this.getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    const url = `${this.baseUrl}${path}${toQueryString(query)}`;
    const response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail =
        typeof payload === "object" && payload && "detail" in payload
          ? String((payload as { detail?: unknown }).detail)
          : response.statusText || "Request failed";
      throw new ApiError(response.status, detail, payload);
    }
    return payload as T;
  }

  register(email: string, password: string, displayName: string): Promise<AuthTokenResponse> {
    return this.request<AuthTokenResponse>(
      "POST",
      "/v2/auth/register",
      { email, password, display_name: displayName },
      undefined,
      false
    );
  }

  login(email: string, password: string): Promise<AuthTokenResponse> {
    return this.request<AuthTokenResponse>("POST", "/v2/auth/login", { email, password }, undefined, false);
  }

  createWorkspace(name: string): Promise<Workspace> {
    return this.request<Workspace>("POST", "/v2/workspaces", { name });
  }

  listWorkspaces(): Promise<WorkspaceListResponse> {
    return this.request<WorkspaceListResponse>("GET", "/v2/workspaces");
  }

  connectYouTube(workspaceId: string): Promise<YouTubeConnectResponse> {
    return this.request<YouTubeConnectResponse>("POST", "/v2/integrations/youtube/connect", {
      workspace_id: workspaceId
    });
  }

  initUpload(payload: UploadInitRequest): Promise<UploadInitResponse> {
    return this.request<UploadInitResponse>("POST", "/v2/uploads/init", payload);
  }

  completeUpload(uploadId: string): Promise<UploadCompleteResponse> {
    return this.request<UploadCompleteResponse>("POST", `/v2/uploads/${uploadId}/complete`);
  }

  async uploadContent(uploadId: string, file: File): Promise<UploadContentResponse> {
    const form = new FormData();
    form.append("file", file);
    const headers: HeadersInit = {};
    if (this.getAccessToken) {
      const token = this.getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    const response = await fetch(`${this.baseUrl}/v2/uploads/${uploadId}/content`, {
      method: "POST",
      headers,
      body: form
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail =
        typeof payload === "object" && payload && "detail" in payload
          ? String((payload as { detail?: unknown }).detail)
          : response.statusText || "Upload failed";
      throw new ApiError(response.status, detail, payload);
    }
    return payload as UploadContentResponse;
  }

  createJob(payload: JobCreateRequest): Promise<Job> {
    return this.request<Job>("POST", "/v2/jobs", payload);
  }

  listJobs(params: {
    workspaceId: string;
    status?: JobStatus;
    limit?: number;
    cursor?: string;
  }): Promise<JobListResponse> {
    return this.request<JobListResponse>("GET", "/v2/jobs", undefined, {
      workspace_id: params.workspaceId,
      status: params.status,
      limit: params.limit,
      cursor: params.cursor
    });
  }

  getJob(jobId: string): Promise<Job> {
    return this.request<Job>("GET", `/v2/jobs/${jobId}`);
  }

  retryJob(jobId: string): Promise<Job> {
    return this.request<Job>("POST", `/v2/jobs/${jobId}/retry`);
  }

  cancelJob(jobId: string): Promise<Job> {
    return this.request<Job>("POST", `/v2/jobs/${jobId}/cancel`);
  }

  getTranscript(transcriptId: string): Promise<TranscriptDetail> {
    return this.request<TranscriptDetail>("GET", `/v2/transcripts/${transcriptId}`);
  }

  updateTranscript(transcriptId: string, editedText: string): Promise<TranscriptVersion> {
    return this.request<TranscriptVersion>("PATCH", `/v2/transcripts/${transcriptId}`, {
      edited_text: editedText
    });
  }

  publishTranscriptVersion(transcriptId: string, versionId: string): Promise<TranscriptVersion> {
    return this.request<TranscriptVersion>("POST", `/v2/transcripts/${transcriptId}/versions/${versionId}/publish`);
  }

  createExport(payload: ExportCreateRequest): Promise<ExportAsset> {
    return this.request<ExportAsset>("POST", "/v2/exports", payload);
  }

  getExportDownload(exportId: string): Promise<ExportDownloadResponse> {
    return this.request<ExportDownloadResponse>("GET", `/v2/exports/${exportId}/download`);
  }

  getUsageSummary(workspaceId: string, periodStartIso: string, periodEndIso: string): Promise<UsageSummaryResponse> {
    return this.request<UsageSummaryResponse>("GET", "/v2/usage/summary", undefined, {
      workspace_id: workspaceId,
      period_start: periodStartIso,
      period_end: periodEndIso
    });
  }

  createAbuseReport(payload: AbuseReportCreateRequest): Promise<AbuseReport> {
    return this.request<AbuseReport>("POST", "/v2/abuse-reports", payload, undefined, false);
  }

  listAbuseReports(status?: AbuseStatus): Promise<AbuseReportListResponse> {
    return this.request<AbuseReportListResponse>("GET", "/v2/abuse-reports", undefined, { status });
  }
}
