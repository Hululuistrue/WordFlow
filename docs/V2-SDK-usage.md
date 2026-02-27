# V2 SDK Usage

```ts
import { TranscriptProV2Client } from "../frontend/lib/api/v2";

const client = new TranscriptProV2Client({
  baseUrl: "http://localhost:8000",
  getAccessToken: () => localStorage.getItem("access_token")
});

const ws = await client.createWorkspace("My Workspace");
const upload = await client.initUpload({
  workspace_id: ws.id,
  filename: "audio.mp3",
  content_type: "audio/mpeg",
  size_bytes: 1000000
});
```

Main SDK files:
- `frontend/lib/api/v2/types.ts`
- `frontend/lib/api/v2/client.ts`

