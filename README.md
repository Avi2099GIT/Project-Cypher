Project Cypher 🧠⚙️

An AI Operating System for Real-World Execution, Automation, and Intelligence

Project Cypher is a production-oriented AI Operating System (AI-OS) that bridges natural language, reasoning, and real-world execution across local systems, cloud services, browsers, CI/CD, and external AI models.

Unlike traditional chatbots, Cypher is designed as an execution-first, introspectable, multi-agent system with strong guarantees around safety, traceability, and extensibility.

🔥 Core Philosophy

Intent → Reasoning → Planning → Execution → Verification → Memory

Cypher is not a single agent.
It is a coordinated AI system with explicit control over:

what should be done

why it should be done

how it is executed

whether it succeeded

🚀 Features Overview (Phase 0 → Phase 4)
✅ Phase 0 — Edge Foundations

Low-level audio and signal processing pipeline.

Wake-word detection

Voice Activity Detection (VAD)

Audio normalization & trimming

Offline ASR support (Whisper.cpp compatible)

Modular edge runtime

✔️ Status: Completed

✅ Phase 1 — Core Intelligence Loop

Natural language understanding and system orchestration.

Reasoning agent (LLM-based + heuristic fallback)

Deterministic mode selection:

chat_only

auto_tools

force_tools

clarify_only

Safety-aware decision gating

Execution context propagation

✔️ Status: Completed

✅ Phase 2 — Planning & Execution Engine

From intent to real actions.

PlannerV2 (deterministic, hardened)

Multi-step execution plans

Local tool execution (OS, web, utilities)

Executor with strict failure semantics

Automatic fallback from MCP → local tools

Structured execution results

✔️ Status: Completed

✅ Phase 3 — Memory, Tracing & Observability

Full introspection into system behavior.

Episodic memory (per device / session)

Trace IDs for every request

Execution graphs with node status

Failure maps & slow-node detection

Debug endpoints for plans, memory, traces

✔️ Status: Completed

✅ Phase 4 — MCP Integration (Native)

Enterprise-grade extensibility via native MCP servers.

Native MCP client registry

Multiple MCP backends supported:

Shell

Docker

GitHub

Playwright (browser automation)

Claude / LLM MCP

Runtime MCP availability probing

Safe fallback to local tools if MCP unavailable

Unified metrics for MCP calls

✔️ Status: Completed
⚠️ Note: MCP is implemented using native MCP servers, not Docker-wrapped MCP.

🎙️ Voice System Status

Voice pipeline (wake, VAD, ASR, TTS hooks) is implemented

Voice is NOT wired into the current dev workflow

Development and testing are currently text-first

Voice will be re-enabled in a future phase once core automation stabilizes.

🧩 System Architecture
User Input
   ↓
ReasoningAgent
   ↓
Arbiter / Safety
   ↓
PlannerV2
   ↓
ExecutorAgent
   ├── Local Tools
   └── Native MCP Servers
   ↓
Verifier
   ↓
Memory + Tracing

🛠️ Tech Stack

Backend

Python 3.10+

FastAPI

AsyncIO

AI / LLM

OpenAI (optional)

Anthropic Claude (via native MCP)

Deterministic fallback logic (no LLM dependency for execution)

Automation

Native MCP servers

OS automation

Browser automation (Playwright MCP)

GitHub & CI integration

Observability

Custom tracer

Execution graphs

Metrics & diagnostics APIs

📁 Project Structure (Simplified)
cloud/
└── api/
    └── assistant/
        ├── agents_dir/
        │   ├── reasoning_agent.py
        │   ├── planner_agent_v2.py
        │   ├── executor_agent.py
        │   └── brain.py
        ├── orchestrator/
        │   ├── cypher_graph.py
        │   ├── tracer.py
        │   └── node.py
        ├── mcp/
        │   ├── registry.py
        │   ├── mcp_client_base.py
        │   └── errors.py
        ├── tools_registry.py
        ├── tools_base.py
        └── router.py

▶️ Getting Started
1️⃣ Prerequisites

Python 3.10+

Virtual environment recommended

API keys (optional but recommended):

OPENAI_API_KEY

ANTHROPIC_API_KEY

2️⃣ Install Dependencies
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows

pip install -r requirements.txt

3️⃣ Run the Server
uvicorn cloud.api.main:app --reload


Server runs at:

http://localhost:8000

🧪 Usage Examples
🔹 Basic Query
POST /v1/assistant/query

{
  "message": "what time is it"
}

🔹 Run a Shell Command (MCP)
{
  "message": "Run command dir"
}


Cypher will:

Detect execution intent

Plan an MCP shell call

Execute safely

Return structured output

🧪 Debug & Inspection Endpoints
Endpoint	Purpose
/v1/assistant/debug/trace	Execution timeline
/v1/assistant/debug/plan	Planner decisions
/v1/assistant/debug/memory	Episodic memory
/v1/assistant/debug/metrics	MCP metrics
/v1/assistant/debug/trace/heatmap	Performance analysis
🔐 Safety Guarantees

Explicit execution modes

No implicit command execution

MCP availability checks

Deterministic fallbacks

Full traceability of actions

🧭 Roadmap (Beyond Phase 4)

Offline-first mode

Multi-agent parallel execution

Enterprise tenancy

Persistent long-term memory

AR / hardware interfaces

Plugin marketplace

📜 License

MIT (or your preferred license)

⭐ Final Note

Project Cypher is not a chatbot.
It is an AI Operating System designed for real-world control, automation, and intelligence — with the rigor required for production systems.
