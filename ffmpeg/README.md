# mcp-ffmpeg

Structured ffmpeg operations, not a shell. An [MCP](https://modelcontextprotocol.io) server speaking Streamable
HTTP: run it in a container, point your agent at `http://localhost:8094/mcp`.

ffmpeg/ffprobe exposed as typed operations instead of a command line: probe media, extract audio, clip, transcode, scale, pull frames and make thumbnails. The agent picks an operation and arguments; it never composes an ffmpeg invocation.

## Quickstart

```bash
docker compose up          # builds the image the first time
```

Then register it with your agent. Claude Code:

```bash
claude mcp add --transport http ffmpeg http://localhost:8094/mcp
```

…or in a client config:

```json
{"mcpServers": {"ffmpeg": {"type": "http", "url": "http://localhost:8094/mcp"}}}
```

## How files reach the tools

These tools take **paths, not uploads** — the agent names a file, the server
opens it in place and writes results back. Nothing but the path and the verdict
crosses the MCP wire, so a 200 MB file costs no tokens.

That means the container has to be able to see your files. `docker compose up`
mounts the directory you ran it from at `/work`, so tell the agent about
`/work/drawing.dxf`, not `~/drawing.dxf`. Mount somewhere else with
`WORKDIR=/path/to/project docker compose up`.

Files the tools create are written as your host user, not root:

```bash
MCP_UID=$(id -u) MCP_GID=$(id -g) docker compose up   # if your uid is not 1000
```

## Tools

- `get_media_info`
- `extract_audio`
- `clip`
- `transcode`
- `scale`
- `extract_frames`
- `thumbnail`

Each tool's own description and typed signature — what the agent actually reads
to decide when to call it — is in `src/server.py`.

## Requirements

ffmpeg, installed in the image.

## Contributing

Issues and PRs are welcome and read directly.

One thing to know before you send a PR: this repository is a **one-way mirror**
of a directory in a private monorepo, which stays canonical. Contributions are
applied there and reappear here on the next sync, so your change lands with your
authorship upstream but arrives in this repo's history inside a sync commit.
Nothing here is force-pushed away, but don't expect your PR to be merged with a
green button.

## License

Apache-2.0 — see [LICENSE](LICENSE).
