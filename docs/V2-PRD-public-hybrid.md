# Transcript Pro V2 PRD (Public Launch, Hybrid Route)

## 1. Product
- Product name: `Transcript Pro`
- Positioning: Public SaaS for subtitle extraction/transcription/export.
- Route: `Hybrid`
1. `YouTube OAuth` for user-owned/authorized videos.
2. `File Upload + ASR` for direct audio/video transcription.

## 2. Goals
- `G1` Compliance-first public launch.
- `G2` High success rate with actionable failures.
- `G3` Monetizable with quota + billing.
- `G4` Unified workflow across source types.

## 3. Compliance Boundaries
- Process only content user is authorized to process.
- No default support for arbitrary third-party YouTube scraping.
- Mandatory rights declaration before task submission.
- DMCA/complaint workflow with takedown SLA.
- Data retention + deletion policy with auditability.

## 4. Target Users
- Creators and media teams
- Education/training organizations
- Researchers and knowledge workers
- SMB teams with collaboration needs

## 5. Core User Flows
1. Sign up / sign in.
2. Choose source: `Connect YouTube` or `Upload file`.
3. Submit job with language/timestamp/output options.
4. Async processing with status updates.
5. Edit transcript and export (`txt/srt/vtt`).
6. Save/share in workspace.

## 6. V2 Scope
- Auth, workspace, project, membership
- YouTube OAuth integration
- Upload pipeline (`mp3/mp4/m4a/wav`)
- ASR worker pipeline
- Transcript editor with versioning
- Export pipeline (`txt/srt/vtt`)
- Job center and retries
- Quota, subscription, usage metering
- Admin and abuse/complaint handling

## 7. Out of Scope (V2)
- Arbitrary public video scraping as primary path
- Video redistribution
- Full non-linear video editor
- On-prem deployment

## 8. Functional Requirements
- `FR1` OAuth-linked extraction only for authorized resources.
- `FR2` Upload transcription with structured segments.
- `FR3` Standard job states: `queued/running/success/failed/retrying/canceled`.
- `FR4` Failure must expose actionable reason and hint.
- `FR5` Transcript editing + saved versions.
- `FR6` Export in txt/srt/vtt.
- `FR7` Quota and billing enforcement.

## 9. Non-Functional Requirements
- Availability: `>= 99.9%`
- Queue admission latency (P95): `<= 10s`
- Processing success rate (excluding unauthorized input): `>= 98%`
- Security: encrypted transport/storage, least-privilege access
- Observability: logs, metrics, tracing, alerts

## 10. Risks
- YouTube anti-abuse and policy changes
- GPU cost volatility for ASR workloads
- Abuse content and legal complaints
- Multilingual accuracy variance

## 11. Milestones
1. `M1 (2-3 weeks)`: auth/workspace/upload/asr/export baseline
2. `M2 (2-3 weeks)`: YouTube OAuth + unified jobs
3. `M3 (2 weeks)`: billing/quota/rate-limit/audit
4. `M4 (2 weeks)`: beta launch + ops hardening

## 12. V2 Exit Criteria
- Both routes complete E2E with export.
- Clear typed errors and retry guidance.
- Monitoring dashboard covers queue/success/error/cost.
- Complaint/takedown process operational.
- Public beta can sustain target concurrency.

