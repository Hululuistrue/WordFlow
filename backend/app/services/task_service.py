import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from app.models.task import (
    LanguagePref,
    Task,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskResponse,
    TaskStatus,
)
from app.services.errors import SubtitleError
from app.services.youtube import FetchResult, YtDlpSubtitleFetcher
from app.utils.url_validator import normalize_youtube_url


logger = logging.getLogger(__name__)


class TaskStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, Task] = {}

    def insert(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            return task.model_copy(deep=True)

    def update(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task


@dataclass
class CreateTaskInput:
    url: str
    language_pref: LanguagePref
    with_timestamps: bool


class TaskService:
    def __init__(self, fetcher: YtDlpSubtitleFetcher):
        self.store = TaskStore()
        self.fetcher = fetcher

    def create_task(self, payload: TaskCreateRequest) -> TaskCreateResponse:
        normalized_url = normalize_youtube_url(payload.url)
        task = Task(
            url=normalized_url,
            language_pref=payload.language_pref,
            with_timestamps=payload.with_timestamps,
            status=TaskStatus.queued,
            progress=0,
        )
        self.store.insert(task)
        loop = asyncio.get_running_loop()
        loop.create_task(self._run_task(task.id))
        return TaskCreateResponse(task_id=task.id)

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = self.store.get(task_id)
        if not task:
            return None
        return TaskResponse.from_task(task)

    def get_task_text(self, task_id: str) -> str | None:
        task = self.store.get(task_id)
        if not task:
            return None
        return task.result_text

    async def _run_task(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if not task:
            return

        started = datetime.now(timezone.utc)
        task.status = TaskStatus.running
        task.progress = 10
        self.store.update(task)

        try:
            result: FetchResult = await asyncio.to_thread(
                self.fetcher.fetch_subtitles,
                task.url,
                task.language_pref,
                task.with_timestamps,
            )
            latest = self.store.get(task_id)
            if not latest:
                return
            latest.status = TaskStatus.success
            latest.progress = 100
            latest.source = result.source
            latest.language = result.language
            latest.result_text = result.result_text
            latest.segments = result.segments
            latest.error = None
            latest.finished_at = datetime.now(timezone.utc)
            self.store.update(latest)
        except SubtitleError as exc:
            latest = self.store.get(task_id)
            if not latest:
                return
            latest.status = TaskStatus.failed
            latest.progress = 100
            latest.error = exc.user_message
            latest.finished_at = datetime.now(timezone.utc)
            self.store.update(latest)
            logger.warning(
                "task_failed task_id=%s code=%s message=%s raw=%s",
                task_id,
                exc.code,
                exc.user_message,
                exc.raw_message,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            latest = self.store.get(task_id)
            if not latest:
                return
            latest.status = TaskStatus.failed
            latest.progress = 100
            latest.error = "Unexpected error while processing subtitles."
            latest.finished_at = datetime.now(timezone.utc)
            self.store.update(latest)
            logger.exception("task_unexpected_failure task_id=%s error=%s", task_id, exc)
        finally:
            duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            logger.info("task_completed task_id=%s duration_ms=%s", task_id, duration_ms)
