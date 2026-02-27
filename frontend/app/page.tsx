"use client";

import { useMemo, useRef, useState } from "react";

import {
  ApiError,
  TranscriptDetail,
  TranscriptProV2Client,
  Workspace,
  type ExportFormat,
  type ExportAsset,
  type Job,
  type YouTubeClient,
  type YouTubeMode
} from "../lib/api/v2";

const client = new TranscriptProV2Client({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"
});

class JobStillRunningError extends Error {
  constructor() {
    super("Job is still running in the background.");
    this.name = "JobStillRunningError";
  }
}

export default function HomePage() {
  const duplicateCooldownMs = 10000;
  const jobPollingIntervalMs = 500;
  const jobPollingAttempts = 360;
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [youtubeClient, setYoutubeClient] = useState<YouTubeClient>("web");
  const [youtubeMode, setYoutubeMode] = useState<YouTubeMode>("compat");
  const [youtubeUseCookies, setYoutubeUseCookies] = useState(false);
  const [youtubeCookiesTxt, setYoutubeCookiesTxt] = useState("");
  const [youtubeCookiesAcknowledged, setYoutubeCookiesAcknowledged] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [transcript, setTranscript] = useState<TranscriptDetail | null>(null);
  const [exportAsset, setExportAsset] = useState<ExportAsset | null>(null);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("md");
  const [usage, setUsage] = useState<{ used: number; quota: number; remaining: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [cookiesHint, setCookiesHint] = useState<string | null>(null);
  const [submitHint, setSubmitHint] = useState<string | null>(null);
  const [backgroundJobHint, setBackgroundJobHint] = useState<string | null>(null);
  const activeRequestKeyRef = useRef<string | null>(null);
  const lastSubmissionRef = useRef<{ key: string; at: number } | null>(null);

  const statusText = useMemo(() => {
    if (loading) return "Running V2 flow...";
    if (job) return `Last job status: ${job.status} (${job.progress}%)`;
    return "Idle";
  }, [loading, job]);
  const jobProgress = Math.max(0, Math.min(100, job?.progress ?? 0));
  const progressTone = job?.status === "failed" ? "failed" : job?.status === "success" ? "success" : "running";

  function toMessage(error: unknown): string {
    if (error instanceof ApiError) {
      const raw = String(error.message || "");
      if (youtubeUseCookies && raw.toLowerCase().includes("invalid cookies format")) {
        setCookiesHint("Cookies format invalid. Use Netscape cookies.txt, JSON export, or Cookie header text, then retry.");
      }
      return `[${error.status}] ${raw}`;
    }
    if (error instanceof Error) return error.message;
    return "Unexpected error";
  }

  function isActiveJob(current: Job | null): boolean {
    if (!current) return false;
    return current.status === "queued" || current.status === "running" || current.status === "retrying";
  }

  function youtubeRequestKey(videoId: string): string {
    const cookiesFingerprint = youtubeUseCookies ? `${youtubeCookiesTxt.length}:${youtubeCookiesTxt.slice(0, 32)}` : "none";
    return `youtube:${videoId}:${youtubeMode}:${youtubeClient}:${youtubeUseCookies}:${cookiesFingerprint}:auto:true`;
  }

  function uploadRequestKey(file: File): string {
    return `upload:${file.name}:${file.size}:${file.lastModified}:auto:true`;
  }

  function guardDuplicateSubmission(requestKey: string): boolean {
    const now = Date.now();
    if (activeRequestKeyRef.current === requestKey && isActiveJob(job)) {
      setSubmitHint("Same request is already running. Wait for the current job to finish.");
      return true;
    }

    const last = lastSubmissionRef.current;
    if (last && last.key === requestKey && now - last.at < duplicateCooldownMs) {
      const remainSeconds = Math.max(1, Math.ceil((duplicateCooldownMs - (now - last.at)) / 1000));
      setSubmitHint(`Duplicate submission blocked. Please wait ${remainSeconds}s before retrying the same request.`);
      return true;
    }
    return false;
  }

  function markSubmissionStarted(requestKey: string): void {
    activeRequestKeyRef.current = requestKey;
    lastSubmissionRef.current = { key: requestKey, at: Date.now() };
    setSubmitHint(null);
  }

  function markSubmissionFinished(requestKey: string): void {
    if (activeRequestKeyRef.current === requestKey) {
      activeRequestKeyRef.current = null;
    }
    lastSubmissionRef.current = { key: requestKey, at: Date.now() };
  }

  function buildYoutubeFailureMessage(doneJob: Job): string {
    const code = doneJob.error_code || "";
    const base = doneJob.error_message || `Job ended with status: ${doneJob.status}`;
    if (!youtubeUseCookies) {
      return base;
    }

    if (code === "bot_or_rate_limited" || code === "cookies_invalid_or_blocked") {
      setCookiesHint(
        "Cookies may be expired, incomplete, or the current IP is challenged. Re-export cookies.txt from a logged-in browser and retry."
      );
      return "YouTube access blocked. Cookies were accepted but may be expired/incomplete, or this IP is being challenged.";
    }

    if (code === "subtitle_fetch_failed") {
      setCookiesHint(
        "Cookies were accepted, but yt-dlp still hit a generic extractor failure. Check backend logs for the raw yt-dlp error and retry with a different video or network."
      );
      return "YouTube request failed after cookies were accepted. This is not necessarily an expired-cookie problem.";
    }

    if (code === "cookies_db_locked") {
      setCookiesHint(
        "If you used browser-cookie mode elsewhere, close all Chrome windows completely, or use uploaded cookies.txt only."
      );
      return base;
    }

    setCookiesHint(null);
    return base;
  }

  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function extractYouTubeVideoId(url: string): string | null {
    const raw = url.trim();
    if (!raw) return null;
    try {
      const parsed = new URL(raw);
      const host = parsed.hostname.toLowerCase();
      if (host.includes("youtu.be")) {
        const id = parsed.pathname.split("/").filter(Boolean)[0];
        return id || null;
      }
      if (host.includes("youtube.com")) {
        const idFromQuery = parsed.searchParams.get("v");
        if (idFromQuery) return idFromQuery;
        const pathParts = parsed.pathname.split("/").filter(Boolean);
        const shortsIdx = pathParts.indexOf("shorts");
        if (shortsIdx >= 0 && pathParts[shortsIdx + 1]) return pathParts[shortsIdx + 1];
        const embedIdx = pathParts.indexOf("embed");
        if (embedIdx >= 0 && pathParts[embedIdx + 1]) return pathParts[embedIdx + 1];
      }
      return null;
    } catch {
      return null;
    }
  }

  async function onCookiesFileSelected(file: File | null): Promise<void> {
    if (!file) {
      setYoutubeCookiesTxt("");
      return;
    }
    const text = await file.text();
    setYoutubeCookiesTxt(text);
  }

  async function ensureWorkspace(): Promise<Workspace> {
    if (workspace) return workspace;
    const ws = await client.createWorkspace(`Workspace-${Date.now()}`);
    setWorkspace(ws);
    return ws;
  }

  async function waitForTerminalJob(jobId: string): Promise<Job> {
    for (let i = 0; i < jobPollingAttempts; i += 1) {
      const current = await client.getJob(jobId);
      setJob(current);
      if (current.status === "success" || current.status === "failed" || current.status === "canceled") {
        return current;
      }
      await sleep(jobPollingIntervalMs);
    }
    throw new JobStillRunningError();
  }

  async function hydrateSuccessfulJob(doneJob: Job): Promise<void> {
    if (!doneJob.transcript_id) {
      throw new Error("Missing transcript_id in job response");
    }
    const detail = await client.getTranscript(doneJob.transcript_id);
    setTranscript(detail);

    const ws = await ensureWorkspace();
    if (exportAsset?.transcript_version_id === detail.latest_version.id && exportAsset.format === "txt") {
      return;
    }

    const createdExport = await client.createExport({
      workspace_id: ws.id,
      transcript_version_id: detail.latest_version.id,
      format: "txt"
    });
    setExportAsset(createdExport);
    setExportFormat("txt");
  }

  async function resumeCurrentJob(): Promise<void> {
    if (!job || !isActiveJob(job)) {
      setBackgroundJobHint(null);
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setBackgroundJobHint(null);
    try {
      const doneJob = await waitForTerminalJob(job.id);
      if (doneJob.status !== "success") {
        const message =
          doneJob.source_type === "youtube_oauth" ? buildYoutubeFailureMessage(doneJob) : doneJob.error_message || `Job ended with status: ${doneJob.status}`;
        throw new Error(message);
      }
      await hydrateSuccessfulJob(doneJob);
      setSubmitHint("Upload completed. TXT export is ready. Click Download Export below.");
    } catch (error) {
      if (error instanceof JobStillRunningError) {
        setBackgroundJobHint("Current job is still processing on the backend. Use Continue Monitoring to keep polling this same job.");
      } else {
        setErrorMessage(toMessage(error));
      }
    } finally {
      setLoading(false);
    }
  }

  async function runUploadToTranscriptFlow() {
    setLoading(true);
    setErrorMessage(null);
    setCookiesHint(null);
    setSubmitHint(null);
    setBackgroundJobHint(null);
    let requestKey: string | null = null;
    let submissionStarted = false;
    let keepSubmissionActive = false;
    try {
      if (!uploadFile) {
        throw new Error("Please choose an audio/video file first.");
      }
      requestKey = uploadRequestKey(uploadFile);
      if (guardDuplicateSubmission(requestKey)) {
        return;
      }
      const ws = await ensureWorkspace();

      const upload = await client.initUpload({
        workspace_id: ws.id,
        filename: uploadFile.name,
        content_type: uploadFile.type || "application/octet-stream",
        size_bytes: uploadFile.size || 1
      });
      await client.uploadContent(upload.upload_id, uploadFile);
      const completed = await client.completeUpload(upload.upload_id);

      const createdJob = await client.createJob({
        workspace_id: ws.id,
        source_type: "upload",
        source_asset_id: completed.source_asset_id,
        language_pref: "auto",
        with_timestamps: true
      });
      markSubmissionStarted(requestKey);
      submissionStarted = true;
      setJob(createdJob);
      setTranscript(null);
      setExportAsset(null);

      const doneJob = await waitForTerminalJob(createdJob.id);
      if (doneJob.status !== "success") {
        throw new Error(doneJob.error_message || `Job ended with status: ${doneJob.status}`);
      }
      await hydrateSuccessfulJob(doneJob);

      const now = new Date();
      const later = new Date(now.getTime() + 60 * 60 * 1000);
      const summary = await client.getUsageSummary(ws.id, now.toISOString(), later.toISOString());
      setUsage({
        used: summary.used_minutes,
        quota: summary.quota_minutes,
        remaining: summary.remaining_minutes
      });
    } catch (error) {
      if (error instanceof JobStillRunningError) {
        keepSubmissionActive = true;
        setBackgroundJobHint("Current job is still processing on the backend. Use Continue Monitoring to keep polling this same job.");
      } else {
        setErrorMessage(toMessage(error));
      }
    } finally {
      if (submissionStarted && requestKey && !keepSubmissionActive) {
        markSubmissionFinished(requestKey);
      }
      setLoading(false);
    }
  }

  async function runYoutubeUrlFlow() {
    setLoading(true);
    setErrorMessage(null);
    setCookiesHint(null);
    setSubmitHint(null);
    setBackgroundJobHint(null);
    let requestKey: string | null = null;
    let submissionStarted = false;
    let keepSubmissionActive = false;
    try {
      const videoId = extractYouTubeVideoId(youtubeUrl);
      if (!videoId) {
        throw new Error("Invalid YouTube URL");
      }
      requestKey = youtubeRequestKey(videoId);
      if (guardDuplicateSubmission(requestKey)) {
        return;
      }
      if (youtubeUseCookies) {
        if (!youtubeCookiesAcknowledged) {
          throw new Error("Please acknowledge cookie security risks before using cookies mode.");
        }
        if (!youtubeCookiesTxt.trim()) {
          throw new Error("Please upload or paste cookies.txt content.");
        }
      }
      const ws = await ensureWorkspace();

      const createdJob = await client.createJob({
        workspace_id: ws.id,
        source_type: "youtube_oauth",
        youtube_video_id: videoId,
        youtube_client: youtubeClient,
        youtube_mode: youtubeMode,
        youtube_use_cookies: youtubeUseCookies,
        youtube_cookies_txt: youtubeUseCookies ? youtubeCookiesTxt : null,
        youtube_cookies_acknowledged: youtubeUseCookies ? youtubeCookiesAcknowledged : false,
        language_pref: "auto",
        with_timestamps: true
      });
      markSubmissionStarted(requestKey);
      submissionStarted = true;
      setJob(createdJob);
      setTranscript(null);
      setExportAsset(null);

      const doneJob = await waitForTerminalJob(createdJob.id);
      if (doneJob.status !== "success") {
        throw new Error(buildYoutubeFailureMessage(doneJob));
      }
      await hydrateSuccessfulJob(doneJob);
    } catch (error) {
      if (error instanceof JobStillRunningError) {
        keepSubmissionActive = true;
        setBackgroundJobHint("Current job is still processing on the backend. Use Continue Monitoring to keep polling this same job.");
      } else {
        setErrorMessage(toMessage(error));
      }
    } finally {
      if (submissionStarted && requestKey && !keepSubmissionActive) {
        markSubmissionFinished(requestKey);
      }
      setLoading(false);
    }
  }

  async function exportCurrentTranscript(format: ExportFormat): Promise<void> {
    setLoading(true);
    setErrorMessage(null);
    try {
      const ws = await ensureWorkspace();
      if (!transcript) {
        throw new Error("No transcript available to export.");
      }
      const createdExport = await client.createExport({
        workspace_id: ws.id,
        transcript_version_id: transcript.latest_version.id,
        format
      });
      setExportAsset(createdExport);
      setExportFormat(format);
    } catch (error) {
      setErrorMessage(toMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function downloadCurrentExport(): Promise<void> {
    setErrorMessage(null);
    try {
      if (!exportAsset) {
        throw new Error("Create an export first.");
      }
      const download = await client.getExportDownload(exportAsset.id);
      window.open(client.resolveUrl(download.download_url), "_blank", "noopener,noreferrer");
    } catch (error) {
      setErrorMessage(toMessage(error));
    }
  }

  return (
    <main className="page">
      <h1 className="title">WordFlow</h1>
      <p className="subtitle">Paste a YouTube URL or upload a file to generate transcript text and export it.</p>

      <div className="split-grid">
        <section className="card">
          <h2 className="section-title">YouTube URL</h2>
          <div className="form-row">
            <input
              type="url"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
            />
            <button className="primary" onClick={runYoutubeUrlFlow} disabled={loading}>
              Fetch from YouTube
            </button>
          </div>
          <div className="form-row">
            <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              Mode
              <span
                className="inline-help"
                title="Compat：会有限尝试多个 client，并在被限流时短暂重试一次，成功率更高。Strict：只按当前 client 快速尝试，请求更少。"
                aria-label="Mode help"
              >
                ?
              </span>
              <select value={youtubeMode} onChange={(e) => setYoutubeMode(e.target.value as YouTubeMode)}>
                <option value="compat">Compat (recommended)</option>
                <option value="strict">Strict (fewer requests)</option>
              </select>
            </label>
          </div>
          <div className="form-row">
            <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              YouTube client
              <select value={youtubeClient} onChange={(e) => setYoutubeClient(e.target.value as YouTubeClient)}>
                <option value="web">Web (default)</option>
                <option value="web_ios">Web + iOS</option>
                <option value="ios_web">iOS + Web</option>
                <option value="tv_web">TV + Web</option>
                <option value="android_web">Android + Web</option>
                <option value="android">Android</option>
              </select>
            </label>
          </div>
          <div className="form-row">
            <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={youtubeUseCookies}
                onChange={(e) => setYoutubeUseCookies(e.target.checked)}
              />
              Use cookies.txt (Advanced)
            </label>
          </div>
          {youtubeUseCookies ? (
            <>
              <div className="warning">
                Security warning: cookies may contain account session credentials. Use only throwaway or dedicated account
                cookies. We clear cookies after job completion.
              </div>
              <div className="form-row">
                <input
                  type="file"
                  accept=".txt,text/plain"
                  onChange={(e) => void onCookiesFileSelected(e.target.files?.[0] || null)}
                />
              </div>
              <div className="form-row">
                <textarea
                  value={youtubeCookiesTxt}
                  onChange={(e) => setYoutubeCookiesTxt(e.target.value)}
                  placeholder="Netscape cookies.txt content"
                  rows={8}
                />
              </div>
              <div className="form-row">
                <label className="muted" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={youtubeCookiesAcknowledged}
                    onChange={(e) => setYoutubeCookiesAcknowledged(e.target.checked)}
                  />
                  I understand the security and compliance risks of using cookies.
                </label>
              </div>
            </>
          ) : null}
        </section>

        <section className="card">
          <h2 className="section-title">Upload File</h2>
          <p className="muted">More stable path for long audio/video transcription. This flow prepares TXT export automatically.</p>
          <div className="form-row">
            <input
              type="file"
              accept="audio/*,video/*"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
            <button className="primary" onClick={runUploadToTranscriptFlow} disabled={loading}>
              Upload -&gt; Transcribe -&gt; Prepare TXT
            </button>
          </div>
        </section>
      </div>

      <section className="card">
        <div className="status">
          Status: {statusText}
          {errorMessage ? <span className="error"> | {errorMessage}</span> : null}
        </div>
        {job ? (
          <div className="progress-wrap" aria-live="polite">
            <div className="progress-meta">
              <span>{job.status}</span>
              <span>{jobProgress}%</span>
            </div>
            <div
              className="progress-track"
              role="progressbar"
              aria-label="Job progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={jobProgress}
            >
              <div className={`progress-fill ${progressTone}`} style={{ width: `${jobProgress}%` }} />
            </div>
          </div>
        ) : null}
        {cookiesHint ? <div className="cookie-tip">{cookiesHint}</div> : null}
        {submitHint ? <div className="cookie-tip">{submitHint}</div> : null}
        {backgroundJobHint ? <div className="cookie-tip">{backgroundJobHint}</div> : null}

        <div className="actions">
          <button className="ghost" onClick={() => void resumeCurrentJob()} disabled={loading || !job || !isActiveJob(job)}>
            Continue Monitoring Current Job
          </button>
        </div>

        <div className="export-bar">
          <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value as ExportFormat)}>
            <option value="md">Markdown (.md)</option>
            <option value="text">Plain Text (.txt)</option>
            <option value="txt">Timestamp Text (.txt)</option>
            <option value="srt">SubRip (.srt)</option>
            <option value="vtt">WebVTT (.vtt)</option>
          </select>
          <button className="ghost" onClick={() => void exportCurrentTranscript(exportFormat)} disabled={loading || !transcript}>
            Create Export
          </button>
          <button className="primary" onClick={() => void downloadCurrentExport()} disabled={!exportAsset}>
            Download Export
          </button>
        </div>

        <div className="result" style={{ marginTop: 12 }}>
          {transcript ? transcript.raw_text : "Run the flow to see a transcript sample."}
        </div>

        {usage ? (
          <div className="actions">
            <span className="muted">
              Usage: {usage.used.toFixed(2)} / {usage.quota.toFixed(2)} min, left {usage.remaining.toFixed(2)} min
            </span>
          </div>
        ) : null}
      </section>
    </main>
  );
}
