# Stitch Prompt: hip-cargo Pipeline Monitor Dashboard

## What I'm Building

A real-time monitoring dashboard for scientific computing pipelines (radio astronomy imaging). Users run long-running data processing pipelines on high-performance computing clusters and need to check progress, inspect metrics, and control execution from their laptop or phone.

The dashboard is served by a FastAPI backend on the cluster head node. Users access it via SSH tunnel (localhost:8321 in browser) or, for cloud deployments, via a direct URL with bearer token auth. There is no login screen — authentication happens at the network layer.

## Tech Stack

- **Frontend**: React with Tailwind CSS, served as static files by FastAPI
- **Graph library**: React Flow (https://reactflow.dev) for the DAG flow diagram
- **Charts**: Recharts for metric time series
- **Backend API**: FastAPI with WebSocket support (already built)
- **Design tokens**: Dark theme, inspired by n8n's visual style

## Visual Style

- **Dark theme** throughout — dark background (#0f0f0f or similar), with subtle borders and card surfaces
- Inspired by n8n's node-based editor aesthetic: clean, minimal, professional
- Accent colour for active/running states: a warm blue or teal (not too bright)
- Status colours: green (completed), amber/yellow (running), red (failed), grey (pending/queued)
- Typography: system font stack or Inter, monospaced for logs and technical values
- The design should look like a scientific instrument control panel — functional, information-dense but not cluttered

## Screens (Priority Order)

### Screen 1: Pipeline DAG View (Primary Screen)

This is the main screen users see. It shows an n8n-style flow diagram of the currently running (or most recent) pipeline.

**Layout:**
- Top bar: project name, pipeline run ID, overall status badge, elapsed time, link to Ray Dashboard
- Centre: React Flow canvas showing the DAG as connected nodes
- Each node represents a pipeline step (e.g. "init", "grid", "sara", "restore", "degrid")
- Nodes show: step name, cab name, status icon/colour, and if running, a small progress indicator (e.g. "12/15 cycles")
- Edges show execution flow (left-to-right or top-to-bottom)
- Node states: pending (grey/dim), running (pulsing accent colour), completed (green checkmark), failed (red X)
- Clicking a node navigates to the Step Detail screen for that step

**Mobile adaptation:**
- DAG renders vertically (top-to-bottom) on narrow screens
- Nodes are full-width cards stacked vertically, connected by vertical lines
- Tap a card to expand or navigate to step detail

**Data sources:**
- DAG structure: `GET /api/recipes/{recipe_name}` (static, loaded once)
- Live status per step: `WS /ws/progress/{job_id}` (step_started, step_completed, step_failed events)
- Ignore `{"type": "heartbeat"}` messages from the WebSocket

### Screen 2: Step Detail View

When a user clicks/taps a node in the DAG, they see detailed information about that step. This is the "inner level" of the two-level monitoring interface.

**Layout:**
- Header: step name, cab name, status badge, duration
- Progress section: large progress bar (current_step / total_steps), percentage, ETA if calculable
- Metrics section: one or more Recharts line charts showing metric time series (e.g. "peak_residual" over major cycles, "objective" value convergence). Each metric gets its own small chart. The x-axis is the major cycle number, y-axis is the metric value. Use log scale for residuals.
- Image preview section: thumbnails of intermediate artifacts (e.g. residual images). Clicking a thumbnail shows a larger preview in a modal/overlay.
- Log tail: last N log messages from this step, monospaced, auto-scrolling
- Action bar: "Kill Step" button (red, with confirmation dialog), "Relaunch with Parameters" button (opens a parameter editing panel)

**Parameter editing panel (for relaunch):**
- Shows all parameters for this step's cab, pre-filled with current values
- Parameters come from the cab schema (`cab_schemas` in the recipe DAG response)
- Each parameter shows: name, current value (editable input field), type, help text
- Required parameters are marked
- "Relaunch" button submits the modified parameters

**Mobile adaptation:**
- Sections stack vertically: progress, metrics charts, image previews, logs, actions
- Charts are full-width
- Parameter panel is a bottom sheet / slide-up panel

**Data sources:**
- Progress + metrics: `WS /ws/progress/{job_id}` (filtered by worker_name matching the step)
- Metric history: `GET /api/progress/{job_id}/metrics/{metric_name}`
- Image artifacts: `GET /api/artifacts/{ref}` (from artifact events in the WebSocket stream)
- Cab parameter schema: from the recipe DAG response (`steps[n].cab_schema`)
- Kill: `POST /api/jobs/{job_id}/stop`
- Relaunch: `POST /api/pipelines/submit` (with modified params)

### Screen 3: Cluster Status

A simple informational panel, not a full cluster monitor (Ray Dashboard handles that).

**Layout:**
- Link to Ray Dashboard (opens in new tab): prominent button "Open Ray Dashboard"
- Summary cards: number of nodes, total CPUs, total GPUs, total memory (if available from Ray status)
- Active pipelines count
- Recent pipeline runs: a compact list of recent job submissions with status badges

**Mobile adaptation:**
- Summary cards in a 2-column grid
- Recent runs as a scrollable list

**Data sources:**
- Job list: `GET /api/jobs`
- Cluster info: link to Ray Dashboard URL from settings

## Navigation

- **Desktop**: Left sidebar with icons for DAG View, Cluster Status. The step detail is a slide-in panel from the right (or a full-screen overlay) rather than a separate page, so the DAG stays visible in the background.
- **Mobile**: Bottom tab bar with DAG and Cluster tabs. Step detail is a full-screen push navigation.
- The DAG view is the default/home screen.

## Component Inventory

1. **PipelineDAG** — React Flow canvas with custom node components
2. **StepNode** — Custom React Flow node: shows step name, status, mini progress
3. **StepDetailPanel** — Slide-in panel with metrics, logs, artifacts, actions
4. **MetricChart** — Recharts line chart for a single metric time series
5. **ImagePreview** — Thumbnail grid with lightbox/modal for full-size view
6. **LogViewer** — Monospaced auto-scrolling log viewer
7. **ParameterForm** — Auto-generated form from cab schema for relaunching steps
8. **StatusBadge** — Coloured badge/pill for pipeline and step status
9. **ProgressBar** — Animated progress bar with step count and percentage
10. **TopBar** — Project name, pipeline ID, status, elapsed time, Ray Dashboard link
11. **BottomTabBar** — Mobile navigation (DAG, Cluster)
12. **ConfirmDialog** — Confirmation modal for destructive actions (kill)

## Responsive Breakpoints

- Desktop: >= 1024px — sidebar nav, DAG canvas with slide-in step detail
- Tablet: 768px - 1023px — DAG canvas full-width, step detail as overlay
- Mobile: < 768px — vertical node list, bottom tabs, step detail as full-screen

## Design Requirements

- All data displays should have loading skeletons (not spinners)
- Empty states should have helpful messages ("No pipeline running. Launch one from...")
- Error states should show what went wrong and offer retry
- WebSocket reconnection: if the connection drops, show a banner and auto-reconnect
- The DAG should animate smoothly when step states change
- Metric charts should update in real-time as new data points arrive via WebSocket
- The entire UI should work without JavaScript-based authentication (no login screen, no auth cookies — the bearer token is passed in API calls if configured)

## What I Need from Stitch

1. A complete mobile-first responsive design for all three screens
2. Design tokens (colours, spacing, typography) documented in DESIGN.md format
3. The output should be in React/Tailwind so it can be directly implemented with Claude Code
4. Focus on the DAG view and step detail panel — these are the core of the experience
5. The design should feel like a professional monitoring tool, not a consumer app
