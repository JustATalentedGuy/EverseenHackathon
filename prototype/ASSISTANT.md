# Store assistant and hourly briefing

Two additive features on top of the existing prototype. Neither changes detection,
tracking, zone geometry or any metric definition: both only **read** the values the
dashboard already renders.

- **Ask the store** — text and voice Q&A over live zone status, dwell analytics,
  review cues, and the project documentation.
- **Hourly briefing** — a short WhatsApp-ready summary built from the same values and
  handed to each configured recipient through WhatsApp's official click-to-chat link.

## Why it is built this way

Metric questions are answered by **reading `live.stats()` and the observation log**, not by
asking a model to produce a number. A language model cannot sum, average or rank, so
letting it answer "how many people are in the checkout zone" would be guesswork wearing a
labelling. Only explanations ("what does *partial visible dwell* mean?") go through
retrieval, and only over the project's own documents.

The optional local model (`qwen3:1.7b`) is therefore reduced to rephrasing an answer that
was already composed from measured values. If it is missing, slow or wrong, the system
degrades to the deterministic answer instead of failing.

## What it will not tell you

The assistant refuses, using the same boundaries documented in `INTEGRATION.md`:
store-wide unique visitors, cross-camera deduplicated totals, completed checkout waits,
causal bottleneck attribution, revenue or conversion, staff-versus-shopper
classification, and anything that identifies a person. It also leads with the measurement
state when data is stale, warming up or below the target sample rate.

## Setup

### 1. Nothing is required

Open the dashboard. The assistant works in text mode, retrieval works, and the briefing
generates a message plus a WhatsApp link. Microphone capture uses the browser's own speech
recognition when present; replies are spoken with `speechSynthesis`, which is built into the
browser.

### 2. Optional: local model for smoother phrasing

Both runtimes execute the same GGUF weights. **llama.cpp is the lighter option**: one static
`llama-server` binary, an OpenAI-compatible endpoint, no bundled runtime and no daemon.

```bash
# llama.cpp (preferred: smallest footprint, no background service)
curl -L -o llama.zip https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-*-bin-ubuntu-x64.zip && unzip llama.zip
./llama-server -m qwen3-1.7b-q4_k_m.gguf --host 127.0.0.1 --port 8081 -c 4096 -t 4 &
export ASSISTANT_BACKEND=llamacpp
export ASSISTANT_GGUF=/path/to/qwen3-1.7b-q4_k_m.gguf

# or Ollama (one command, larger install)
ollama pull qwen3:1.7b
export ASSISTANT_BACKEND=ollama
```

`ASSISTANT_BACKEND=auto` (default) prefers llama.cpp when a GGUF is configured and the
server answers `/health`, otherwise Ollama, otherwise no model. Qwen3 thinking mode is
disabled in both paths so replies stay short.

### 3. Optional: microphone transcription

```bash
pip install -r requirements-assistant.txt   # faster-whisper
```

Without it the mic button stays hidden and text input is unaffected.

## WhatsApp delivery, at no cost

Delivery uses `https://wa.me/<number>?text=<message>` — WhatsApp's official click-to-chat
link. **No business account, no Meta verification, no approved template and no per-message
fee.** Each recipient receives the message pre-filled and presses send once, which also
keeps a human in the loop before an alert reaches a manager.

Add recipients in the dashboard (name + number in E.164 form; a bare
number such as `9191503949XX` is auto-normalised by prefixing `+`), pick a frequency (15/30/60/120/240 minutes or end of
day), pause or resume, or press **Send now**. Every attempt is written to
`runs/assistant/deliveries.jsonl` with the exact message and link.

The scheduler is one `asyncio` task inside the existing server, so there is no extra
process and no new dependency.

### If you later want fully automated pushes

The same code path can post to a transport instead of opening a link. The official route
needs a Meta Business portfolio, a WABA, a business number and an approved utility template
(utility templates are roughly ₹0.23 per message in India, so a demo costs almost nothing).
Unofficial bridges that reuse a personal WhatsApp session were deliberately not used: they
violate WhatsApp's terms and risk a permanent number ban.

## Files

| File | Purpose |
|---|---|
| `prototype/assistant.py` | guardrails, intent routing, metric tools, refusal rules |
| `prototype/assistant_docs.py` | dependency-free BM25 index over the project documents |
| `prototype/assistant_llm.py` | optional llama.cpp / Ollama phrasing adapter |
| `prototype/briefing.py` | summary builder, recipient config, scheduler, `wa.me` links |
| `prototype/assistant_config.json` | recipients and schedule (created on first save, Git-ignored) |
| `tests/test_assistant.py` | refusals, metric values, citations, briefing encoding, scheduler |

## Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `ASSISTANT_BACKEND` | `auto` | `auto`, `llamacpp`, `ollama`, `none` |
| `ASSISTANT_GGUF` | *(unset)* | path to the GGUF when using llama.cpp |
| `ASSISTANT_MODEL` | `qwen3:1.7b` | Ollama model tag |
| `ASSISTANT_LLM_TIMEOUT` | `12` | seconds before falling back to the deterministic answer |
| `LLAMACPP_URL` | `http://127.0.0.1:8081` | llama.cpp server |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama daemon |