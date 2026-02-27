from pathlib import Path

from app.api.v2.schemas import TranscriptSegment
from app.core.config import Settings
from app.services.errors import SubtitleError


class UploadTranscriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise SubtitleError(
                "asr_engine_missing",
                "ASR engine is not installed. Please install faster-whisper dependencies.",
                str(exc),
            ) from exc

        self._model = WhisperModel(
            self.settings.asr_model_size,
            device=self.settings.asr_device,
            compute_type=self.settings.asr_compute_type,
        )
        return self._model

    def transcribe(
        self,
        media_path: Path,
        language_pref: str = "auto",
        with_timestamps: bool = True,
    ) -> tuple[str | None, str, list[TranscriptSegment], str]:
        if not media_path.exists():
            raise SubtitleError("upload_file_missing", "Uploaded file was not found on server.")

        model = self._get_model()
        language = None if language_pref == "auto" else language_pref
        try:
            chunks, info = model.transcribe(
                str(media_path),
                language=language,
                vad_filter=True,
            )
        except Exception as exc:
            raise SubtitleError("asr_transcribe_failed", "Failed to transcribe uploaded audio.", str(exc)) from exc

        segments: list[TranscriptSegment] = []
        for index, chunk in enumerate(chunks):
            text = (chunk.text or "").strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    index=index,
                    start_seconds=float(chunk.start),
                    end_seconds=float(chunk.end),
                    text=text,
                )
            )

        if not segments:
            raise SubtitleError("asr_no_speech", "No speech detected in uploaded media.")

        if with_timestamps:
            raw_text = "\n".join(
                f"[{segment.start_seconds:0.3f}-{segment.end_seconds:0.3f}] {segment.text}"
                for segment in segments
            )
        else:
            raw_text = "\n".join(segment.text for segment in segments)

        detected_language = getattr(info, "language", None)
        engine = f"faster-whisper:{self.settings.asr_model_size}"
        return detected_language, raw_text, segments, engine

