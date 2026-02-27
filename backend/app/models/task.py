from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


LanguagePref = Literal["auto", "zh", "en"]
DownloadFormat = Literal["txt"]


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TaskCreateRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2048)
    language_pref: LanguagePref = "auto"
    with_timestamps: bool = True


class TaskCreateResponse(BaseModel):
    task_id: str


class TaskResult(BaseModel):
    result_text: str
    segments: list[TranscriptSegment]
    source: str
    language: str | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    url: str
    language_pref: LanguagePref
    with_timestamps: bool = True
    status: TaskStatus = TaskStatus.queued
    progress: int = 0
    source: str | None = None
    language: str | None = None
    result_text: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


class TaskResponse(BaseModel):
    id: str
    status: TaskStatus
    progress: int
    source: str | None = None
    language: str | None = None
    result_text: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None

    @classmethod
    def from_task(cls, task: Task) -> "TaskResponse":
        return cls(
            id=task.id,
            status=task.status,
            progress=task.progress,
            source=task.source,
            language=task.language,
            result_text=task.result_text,
            segments=task.segments,
            error=task.error,
            created_at=task.created_at,
            finished_at=task.finished_at,
        )

