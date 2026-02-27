import time

from fastapi.testclient import TestClient

from app.main import create_app


def test_v2_basic_flow() -> None:
    with TestClient(create_app()) as client:
        workspace_resp = client.post("/v2/workspaces", json={"name": "Demo"})
        assert workspace_resp.status_code == 201
        workspace_id = workspace_resp.json()["id"]

        upload_init = client.post(
            "/v2/uploads/init",
            json={
                "workspace_id": workspace_id,
                "filename": "audio.mp3",
                "content_type": "audio/mpeg",
                "size_bytes": 12345,
            },
        )
        assert upload_init.status_code == 200
        upload_id = upload_init.json()["upload_id"]

        upload_content = client.post(
            f"/v2/uploads/{upload_id}/content",
            files={"file": ("sample.txt", b"not a real audio file", "text/plain")},
        )
        assert upload_content.status_code == 200

        upload_complete = client.post(f"/v2/uploads/{upload_id}/complete")
        assert upload_complete.status_code == 200
        source_asset_id = upload_complete.json()["source_asset_id"]

        job_resp = client.post(
            "/v2/jobs",
            json={
                "workspace_id": workspace_id,
                "source_type": "upload",
                "source_asset_id": source_asset_id,
                "language_pref": "auto",
                "with_timestamps": True,
            },
        )
        assert job_resp.status_code == 201
        job = job_resp.json()
        assert job["status"] == "queued"
        job_id = job["id"]

        terminal_job = None
        for _ in range(400):
            status_resp = client.get(f"/v2/jobs/{job_id}")
            assert status_resp.status_code == 200
            payload = status_resp.json()
            if payload["status"] in {"success", "failed", "canceled"}:
                terminal_job = payload
                break
            time.sleep(0.1)
        assert terminal_job is not None
        assert terminal_job["status"] in {"success", "failed"}
        if terminal_job["status"] == "failed":
            assert terminal_job["error_code"]
            return
        transcript_id = terminal_job["transcript_id"]
        assert transcript_id

        transcript_resp = client.get(f"/v2/transcripts/{transcript_id}")
        assert transcript_resp.status_code == 200
        transcript = transcript_resp.json()
        version_id = transcript["latest_version"]["id"]

        export_resp = client.post(
            "/v2/exports",
            json={
                "workspace_id": workspace_id,
                "transcript_version_id": version_id,
                "format": "txt",
            },
        )
        assert export_resp.status_code == 201
        export_id = export_resp.json()["id"]

        download_resp = client.get(f"/v2/exports/{export_id}/download")
        assert download_resp.status_code == 200
        assert "download_url" in download_resp.json()


def test_export_markdown_file_download() -> None:
    with TestClient(create_app()) as client:
        workspace_resp = client.post("/v2/workspaces", json={"name": "Demo"})
        assert workspace_resp.status_code == 201
        workspace_id = workspace_resp.json()["id"]

        upload_init = client.post(
            "/v2/uploads/init",
            json={
                "workspace_id": workspace_id,
                "filename": "audio.mp3",
                "content_type": "audio/mpeg",
                "size_bytes": 12345,
            },
        )
        upload_id = upload_init.json()["upload_id"]
        client.post(
            f"/v2/uploads/{upload_id}/content",
            files={"file": ("sample.txt", b"not a real audio file", "text/plain")},
        )
        upload_complete = client.post(f"/v2/uploads/{upload_id}/complete")
        source_asset_id = upload_complete.json()["source_asset_id"]

        job_resp = client.post(
            "/v2/jobs",
            json={
                "workspace_id": workspace_id,
                "source_type": "upload",
                "source_asset_id": source_asset_id,
                "language_pref": "auto",
                "with_timestamps": True,
            },
        )
        job_id = job_resp.json()["id"]

        transcript_id = None
        for _ in range(400):
            payload = client.get(f"/v2/jobs/{job_id}").json()
            if payload["status"] == "success":
                transcript_id = payload["transcript_id"]
                break
            if payload["status"] in {"failed", "canceled"}:
                break
            time.sleep(0.1)

        if transcript_id is None:
            return

        transcript = client.get(f"/v2/transcripts/{transcript_id}").json()
        version_id = transcript["latest_version"]["id"]
        export_resp = client.post(
            "/v2/exports",
            json={
                "workspace_id": workspace_id,
                "transcript_version_id": version_id,
                "format": "md",
            },
        )
        assert export_resp.status_code == 201
        export_id = export_resp.json()["id"]

        file_resp = client.get(f"/v2/exports/{export_id}/file")
        assert file_resp.status_code == 200
        assert "Transcript" in file_resp.text or "# " in file_resp.text
        content_disposition = file_resp.headers.get("content-disposition", "")
        assert "filename=" in content_disposition
        assert export_id not in content_disposition


def test_create_youtube_job_with_user_cookies_disabled_by_policy() -> None:
    with TestClient(create_app()) as client:
        workspace_resp = client.post("/v2/workspaces", json={"name": "Demo"})
        assert workspace_resp.status_code == 201
        workspace_id = workspace_resp.json()["id"]

        response = client.post(
            "/v2/jobs",
            json={
                "workspace_id": workspace_id,
                "source_type": "youtube_oauth",
                "youtube_video_id": "dQw4w9WgXcQ",
                "youtube_use_cookies": True,
                "youtube_cookies_txt": ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tvalue",
                "youtube_cookies_acknowledged": True,
            },
        )
        assert response.status_code == 403


def test_create_youtube_job_with_user_cookies_requires_ack() -> None:
    app = create_app()
    original = app.state.settings.allow_user_supplied_cookies
    app.state.settings.allow_user_supplied_cookies = True
    try:
        with TestClient(app) as client:
            workspace_resp = client.post("/v2/workspaces", json={"name": "Demo"})
            assert workspace_resp.status_code == 201
            workspace_id = workspace_resp.json()["id"]

            response = client.post(
                "/v2/jobs",
                json={
                    "workspace_id": workspace_id,
                    "source_type": "youtube_oauth",
                    "youtube_video_id": "dQw4w9WgXcQ",
                    "youtube_use_cookies": True,
                    "youtube_cookies_txt": ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tvalue",
                    "youtube_cookies_acknowledged": False,
                },
            )
            assert response.status_code == 400
    finally:
        app.state.settings.allow_user_supplied_cookies = original
