# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vrabby is a Next.js-based web app builder that integrates AI coding agents (Claude Code, Cursor CLI, Codex CLI, Gemini CLI, Qwen Code) with live preview functionality. Users describe their app idea, and Vrabby generates code with instant preview, deployment to Vercel, and Supabase database integration.

## Development Commands

### Primary Development
```bash
# Start both frontend and backend servers (recommended)
npm run dev

# Start API server only (Python FastAPI)
npm run dev:api

# Start web frontend only (Next.js)
npm run dev:web

# Initial setup (installs all dependencies and creates Python venv)
npm install
```

### Database Management
```bash
# Create database backup before major changes
npm run db:backup

# Reset database to initial state (WARNING: deletes all data)
npm run db:reset
```

### Maintenance
```bash
# Clean all dependencies and start fresh
npm run clean
# Then reinstall: npm install
```

### Default Ports
- Frontend: http://localhost:3000
- Backend API: http://localhost:8080
- API Documentation: http://localhost:8080/docs
- Auto-assigned preview ports: 3100-3999

Note: Ports are auto-detected. Check `.env` files if defaults are unavailable.

## Architecture

### Monorepo Structure
- **apps/web/**: Next.js 14 frontend with TypeScript, Tailwind CSS, shadcn/ui
- **apps/api/**: Python FastAPI backend with SQLAlchemy, WebSocket support
- **data/**: SQLite database (`cc.db`) and user projects storage
- **scripts/**: Setup and maintenance automation scripts

### Backend Architecture (apps/api/)

#### Core Components
- **main.py**: FastAPI app initialization with CORS, routers, database setup
- **core/config.py**: Central configuration using environment variables, auto-detects project root
- **db/session.py**: SQLAlchemy database session management
- **db/migrations.py**: Lightweight SQLite schema migrations

#### CLI Adapters System (app/services/cli/)
The system uses a **unified adapter pattern** to support multiple AI coding agents:

- **base.py**: `BaseCLI` abstract class defining the adapter contract
  - Defines `CLIType` enum (CLAUDE, CURSOR, CODEX, QWEN, GEMINI)
  - `MODEL_MAPPING`: Maps unified model names to CLI-specific names
  - Core methods: `execute_instruction()`, `check_availability()`, `initialize_session()`

- **adapters/**: Concrete CLI implementations
  - `claude_code.py`: Claude Code integration (uses `claude-code-sdk`)
  - `cursor_agent.py`: Cursor CLI agent integration
  - `codex_cli.py`: OpenAI Codex CLI integration
  - `qwen_cli.py`: Qwen Code integration
  - `gemini_cli.py`: Google Gemini CLI integration

- **manager.py**: `UnifiedCLIManager` orchestrates CLI execution
  - Manages session lifecycle per project
  - Handles fallback to Claude Code if primary CLI fails
  - Streams responses via WebSocket to frontend

#### API Routes
- **/api/projects**: Project CRUD operations
- **/api/chat**: Chat messages, WebSocket connections for real-time updates
- **/api/github**: GitHub repository integration
- **/api/vercel**: Vercel deployment management
- **/api/tokens**: Service token management (GitHub, Vercel, Supabase)
- **/api/env**: Environment variable management

#### Key Services
- **services/cli_session_manager.py**: Manages CLI session state and conversation history
- **services/git_ops.py**: Git operations (init, commit, push)
- **services/github_service.py**: GitHub API integration
- **services/vercel_service.py**: Vercel deployment API
- **services/local_runtime.py**: Docker-based local preview runtime
- **services/project/initializer.py**: Scaffolds new Next.js projects with `create-next-app`

#### WebSocket Flow
1. Client connects to `/api/chat/{project_id}` WebSocket
2. User sends message with instruction and selected CLI type
3. `UnifiedCLIManager` routes to appropriate CLI adapter
4. CLI adapter executes instruction and streams tokens back
5. WebSocket broadcasts updates to connected clients
6. Messages persisted to SQLite database

### Frontend Architecture (apps/web/)

#### Page Routes
- **app/page.tsx**: Project list homepage
- **app/[project_id]/chat/page.tsx**: Chat interface with live preview iframe

#### Key Components
- **components/chat/ChatInterface.tsx**: Main chat UI with message list and input
- **components/chat/CLISelector.tsx**: Dropdown to select AI coding agent
- **components/settings/**: Settings modals for services (GitHub, Vercel, Supabase)
- **components/project/wizard/**: Multi-step project creation wizard

#### State Management
- React Context API for auth and global state (`contexts/AuthContext.tsx`)
- WebSocket client connects to backend for real-time message streaming
- Local state for UI interactions

### Project Workflow
1. **Create Project**: Frontend calls `/api/projects` → Backend scaffolds Next.js app in `data/projects/{project_id}/repo/`
2. **User Instruction**: User sends message via WebSocket with selected CLI type (e.g., Claude Code)
3. **CLI Execution**: Backend routes to CLI adapter → CLI modifies files in project directory
4. **Live Preview**: Frontend iframe reloads to show changes at `http://localhost:{preview_port}`
5. **Deployment**: User connects Vercel → Backend pushes to GitHub → Vercel auto-deploys

## System Prompt Integration

The backend uses `apps/api/app/prompt/system-prompt.md` as the base instruction set when initializing CLI sessions. This prompt:
- Defines identity as "Vrabby" assistant
- Specifies Next.js 15 + App Router best practices
- Emphasizes Supabase integration patterns
- Enforces MVP principles (implement only requested features)
- Includes critical Next.js path conventions (no leading slashes)
- Guides beautiful UI creation with Tailwind CSS

## Database Schema

SQLite database at `data/cc.db` with tables:
- **projects**: Project metadata (id, name, path, creation date)
- **sessions**: CLI sessions linked to projects
- **messages**: Chat message history with tool calls
- **tokens**: Encrypted service tokens (GitHub, Vercel, Supabase)
- **env_vars**: Project environment variables
- **commits**: Git commit tracking
- **project_services**: Service connection status

## Adding a New CLI Adapter

1. Create `apps/api/app/services/cli/adapters/new_cli.py`
2. Inherit from `BaseCLI` and implement required methods:
   - `execute_instruction()`: Execute user instruction with streaming
   - `check_availability()`: Verify CLI is installed and configured
   - `initialize_session()`: Setup session with system prompt
3. Add CLI type to `CLIType` enum in `base.py`
4. Add model mappings to `MODEL_MAPPING` in `base.py`
5. Register adapter in `UnifiedCLIManager.__init__()` in `manager.py`
6. Update frontend `CLISelector.tsx` to include new CLI option

## Important Notes

- **Project Isolation**: Each project gets its own git repository in `data/projects/{project_id}/repo/`
- **Path Conventions**: Backend uses absolute paths; CLI adapters receive project-relative paths
- **Environment Variables**: Auto-generated `.env` files in root and `apps/web/.env.local`
- **Python Virtual Environment**: Created at `apps/api/.venv/` during `npm install`
- **Security**: Service tokens encrypted using `cryptography` library before database storage
- **Error Handling**: CLI failures automatically fallback to Claude Code adapter
- **WebSocket**: Single persistent connection per project for real-time updates

## Common Development Patterns

### Testing API Endpoints
Visit http://localhost:8080/docs for interactive Swagger documentation.

### Adding a New API Route
1. Create router file in `apps/api/app/api/`
2. Define FastAPI router with endpoints
3. Import and register in `apps/api/app/main.py`

### Database Schema Changes
1. Modify model in `apps/api/app/models/`
2. Add migration to `apps/api/app/db/migrations.py`
3. Migrations run automatically on server startup

### Frontend Component Creation
Follow Next.js 14 conventions:
- Server components by default (no "use client")
- Add "use client" only when using hooks or event handlers
- Place reusable components in `apps/web/components/`
- Use TypeScript for all new components
