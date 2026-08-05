# agentz

## Setup

Install project dependencies:

```bash
uv sync
```

Install project-local Codex skills:

```bash
uvx library-skills --all
```

This command installs library-provided skills into the project's `.agents/` directory.

## Run

Start the CLI app with:

```bash
uv run main.py
# or bind a specific project directory to this session
uv run main.py --project-path /path/to/project
# or resume an existing session and restore its bound project directory
uv run main.py --resume <session_id>
```

Start the local Web UI:

```bash
uv run main.py web
# then open http://127.0.0.1:8000

# bind newly created Web sessions to a specific project directory
uv run main.py web --project-path /path/to/project --port 8080
```

The Web UI uses the same-origin SSE endpoint at
`POST /api/v1/sessions/{session_id}/messages`. The browser sends only a
session ID and prompt; history and the bound project directory remain on the
server.

Current runtime layout:

```text
main.py                 # CLI startup entry
core/                   # runtime orchestration
config/                 # settings loading
ui/cli/                 # terminal input/output
ui/web/                 # web UI placeholder
interfaces/http/        # HTTP interface placeholder
infra/                  # observability and infrastructure
scripts/run_tests.py    # test runner helper
```

Session data is stored under:

```text
${AGENTZ_HOME:-~/.agentz}/sessions/<session_id>/
```

By default `AGENTZ_HOME` resolves to `~/.agentz`. Select a different home with
`--agentz-home` or the process environment variable `AGENTZ_HOME` before
startup; it cannot be configured from the `.env` that lives inside the home.

The application loads its runtime environment from `$AGENTZ_HOME/.env`. When
`SKILLS_DIR` and `MCP_CONFIG_PATH` are omitted, it uses
`$AGENTZ_HOME/skills` and `$AGENTZ_HOME/mcp.json` respectively. Use
`--agentz-home` or the process environment variable `AGENTZ_HOME` to select a
different home before startup.

Telemetry is disabled unless `OBS_BACKEND` is explicitly set to `logfire` or
`langfuse`. The Langfuse backend additionally requires `LANGFUSE_PUBLIC_KEY`
and `LANGFUSE_SECRET_KEY`.

The bound project directory is stored in the current session metadata. If `--project-path` is omitted, the CLI defaults to the current working directory. When resuming with `--resume`, the stored project directory is restored and takes precedence over any new `--project-path` value.

## MCP config

The app loads MCP servers from `AGENTZ_HOME/mcp.json` by default.
You can override the location in `.env`:

```bash
MCP_CONFIG_PATH=/absolute/path/to/mcp.json
```

Example `mcp.json`:

```json
{
  "mcpServers": {
    "mysql": {
      "command": "${MYSQL_MCP_COMMAND}",
      "args": [],
      "env": {
        "MYSQL_HOST": "${MYSQL_HOST}",
        "MYSQL_PORT": "${MYSQL_PORT}",
        "MYSQL_USER": "${MYSQL_USER}",
        "MYSQL_PASS": "${MYSQL_PASS}",
        "MYSQL_DB": "${MYSQL_DB}",
        "ALLOW_INSERT_OPERATION": "${ALLOW_INSERT_OPERATION:-false}",
        "ALLOW_UPDATE_OPERATION": "${ALLOW_UPDATE_OPERATION:-false}",
        "ALLOW_DELETE_OPERATION": "${ALLOW_DELETE_OPERATION:-false}"
      }
    }
  }
}
```

## Skills config

The app uses the third-party `pydantic-ai-skills` package to load agent skills from a standard directory layout:

```bash
SKILLS_DIR=/custom/path/to/skills
```

Each skill should be stored as:

```text
$AGENTZ_HOME/skills/
  <skill_name>/
    SKILL.md
    REFERENCE.md        # optional
    resources/          # optional
    scripts/            # optional
```

At runtime the skills toolset exposes:

- `list_skills`
- `load_skill`
- `read_skill_resource`
- `run_skill_script`

The project wires this through `pydantic-ai-skills` `SkillsToolset`. The directory comes from `SKILLS_DIR`; when omitted, it defaults to `$AGENTZ_HOME/skills`.

## Build executable

Install development dependencies with `uv sync --group dev`, then use the Makefile:

```bash
make run             # uv run main.py --agentz-home .agentz
make build-onedir    # dist/onedir/agentz/
make build-onefile   # dist/onefile/agentz
```

The executable reads `.env`, optional `mcp.json`, optional `skills/`, and
session data from AgentZ Home at runtime. Do not package those user-owned files
into the build output.

Frozen builds disable Logfire's generic Pydantic plugin before importing
Pydantic AI, because that plugin requires Python source unavailable inside a
PyInstaller archive. AgentZ's explicit Pydantic AI tracing remains enabled.
The frozen entry point also adds PyInstaller's bundle directory to the metadata
search path for Pydantic AI's runtime package-version lookup.
For local macOS testing, leave `CODESIGN_IDENTITY` unset and let PyInstaller
use its default ad-hoc signing. For distribution, provide one real `Developer
ID Application` identity so all embedded binaries share the same Team ID, for
example:

```bash
make build-onedir CODESIGN_IDENTITY="Developer ID Application: Your Name"
```
## Web 服务后台管理

在项目目录使用以下脚本后台启动、停止或重启 Web 服务；服务输出不会保留日志：

```bash
./agentz-web.sh start
./agentz-web.sh status
./agentz-web.sh restart
./agentz-web.sh stop
```
