export type UUID = string;

export type JobSourceType = "youtube_oauth" | "upload";
export type JobStatus = "queued" | "running" | "success" | "failed" | "retrying" | "canceled";
export type ExportFormat = "text" | "txt" | "md" | "srt" | "vtt";
export type YouTubeClient = "web" | "web_ios" | "ios_web" | "tv_web" | "android_web" | "android";
export type YouTubeMode = "strict" | "compat";
export type TranscriptEditStatus = "draft" | "published";
export type AbuseReportType = "copyright" | "privacy" | "illegal" | "other";
export type AbuseStatus = "open" | "reviewing" | "resolved" | "rejected";

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Workspace {
  id: UUID;
  name: string;
  owner_user_id: UUID;
  created_at: string;
}

export interface WorkspaceListResponse {
  items: Workspace[];
}

export interface YouTubeConnectResponse {
  authorization_url: string;
}

export interface UploadInitRequest {
  workspace_id: UUID;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface UploadInitResponse {
  upload_id: UUID;
  object_key: string;
  presigned_url: string;
}

export interface UploadCompleteResponse {
  source_asset_id: UUID;
}

export interface UploadContentResponse {
  upload_id: UUID;
  object_key: string;
  stored_bytes: number;
}

export interface JobCreateRequest {
  workspace_id: UUID;
  project_id?: UUID | null;
  source_type: JobSourceType;
  source_asset_id?: UUID | null;
  youtube_video_id?: string | null;
  youtube_client?: YouTubeClient;
  youtube_mode?: YouTubeMode;
  youtube_use_cookies?: boolean;
  youtube_cookies_txt?: string | null;
  youtube_cookies_acknowledged?: boolean;
  language_pref?: string;
  with_timestamps?: boolean;
}

export interface Job {
  id: UUID;
  workspace_id: UUID;
  project_id?: UUID | null;
  source_type: JobSourceType;
  youtube_client?: YouTubeClient;
  youtube_mode?: YouTubeMode;
  youtube_use_cookies?: boolean;
  status: JobStatus;
  progress: number;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  transcript_id?: UUID | null;
}

export interface JobListResponse {
  items: Job[];
  next_cursor?: string | null;
}

export interface TranscriptSegment {
  index: number;
  start_seconds: number;
  end_seconds: number;
  text: string;
}

export interface TranscriptVersion {
  id: UUID;
  transcript_id: UUID;
  version_number: number;
  edit_status: TranscriptEditStatus;
  edited_text: string;
  editor_user_id: UUID;
  created_at: string;
}

export interface TranscriptDetail {
  id: UUID;
  job_id: UUID;
  title?: string | null;
  language?: string | null;
  source_label?: string | null;
  raw_text: string;
  segments: TranscriptSegment[];
  latest_version: TranscriptVersion;
}

export interface ExportCreateRequest {
  workspace_id: UUID;
  transcript_version_id: UUID;
  format: ExportFormat;
}

export interface ExportAsset {
  id: UUID;
  workspace_id: UUID;
  transcript_version_id: UUID;
  format: ExportFormat;
  object_key: string;
  created_at: string;
}

export interface ExportDownloadResponse {
  download_url: string;
  expires_at: string;
}

export interface UsageSummaryResponse {
  workspace_id: UUID;
  used_minutes: number;
  quota_minutes: number;
  remaining_minutes: number;
}

export interface AbuseReportCreateRequest {
  workspace_id?: UUID | null;
  job_id?: UUID | null;
  reporter_email?: string | null;
  report_type: AbuseReportType;
  description: string;
}

export interface AbuseReport {
  id: UUID;
  workspace_id?: UUID | null;
  job_id?: UUID | null;
  reporter_email?: string | null;
  report_type: AbuseReportType;
  description: string;
  status: AbuseStatus;
  created_at: string;
}

export interface AbuseReportListResponse {
  items: AbuseReport[];
}
