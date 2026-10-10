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

### 2. Optional: a model for conversational phrasing

The answers are already composed from measured values; a model only rewrites them into
something a manager wants to listen to. There are three ways, and you can mix them.

#### Option A — local model, fully offline (nothing leaves the machine)

```bash
# llama.cpp (preferred: one static binary, no daemon, ~1 GB with the model)
git clone --depth 1 https://github.com/ggml-org/llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF
cmake --build build --target llama-server -j2        # -j2 on an 8 GB machine; -j8 gets OOM-killed
curl -L -o qwen3-1.7b-q4_k_m.gguf https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf
./build/bin/llama-server -m qwen3-1.7b-q4_k_m.gguf --host 127.0.0.1 --port 8081 -c 4096 -t 4 &
export ASSISTANT_BACKEND=llamacpp
export ASSISTANT_GGUF=$PWD/qwen3-1.7b-q4_k_m.gguf
```

or Ollama, which is one command but a ~1.5 GB runtime and a background daemon:

```bash
ollama pull qwen3:1.7b && export ASSISTANT_BACKEND=ollama
```

`ASSISTANT_BACKEND=auto` (default) prefers llama.cpp when a GGUF is configured and its
`/health` answers, then Ollama, then the cloud option below, then no model at all.

#### Option B — a free API key (Groq and friends)

Any OpenAI-compatible endpoint works, so Groq, OpenRouter or a self-hosted gateway all
use the same code path. No SDK and no new dependency — it is one HTTPS call.

```bash
export ASSISTANT_CLOUD_API_KEY=...            # or GROQ_API_KEY
export ASSISTANT_BACKEND=cloud                # optional; 'auto' also finds it
export ASSISTANT_CLOUD_MODEL=llama-3.1-8b-instant
```

Groq's free tier is genuinely free and fast, and `llama-3.1-8b-instant` is more than
capable of this job: the model is rewriting one already-correct paragraph into two spoken
sentences. It never sees the video, never sees the observation log, and is told never to
alter a figure.

**What leaves the machine:** the composed answer and the handful of numbers in it — zone
labels, occupancy, dwell. That is store performance data, so treat it the same way you
would treat any other data leaving the site. Option A is the one to choose if that matters
or if the store runs without internet.

**What either option can and cannot change:** phrasing, warmth and ordering only. If a
model is unavailable, slow or returns something unusable, the answer is discarded and the
deterministic text is served instead, so the assistant never degrades to a wrong figure.

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
| `ASSISTANT_BACKEND` | `auto` | `auto`, `llamacpp`, `ollama`, `cloud`, `none` |
| `ASSISTANT_GGUF` | *(unset)* | path to the GGUF when using llama.cpp |
| `ASSISTANT_MODEL` | `qwen3:1.7b` | Ollama model tag |
| `ASSISTANT_LLM_TIMEOUT` | `12` | seconds before falling back to the deterministic answer |
| `LLAMACPP_URL` | `http://127.0.0.1:8081` | llama.cpp server |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama daemon |
| `ASSISTANT_CLOUD_API_KEY` | *(unset)* | Key for the cloud fallback; never logged or written to disk |
| `ASSISTANT_CLOUD_URL` | Groq | Any OpenAI-compatible base URL |
| `ASSISTANT_CLOUD_MODEL` | `llama-3.1-8b-instant` | Cloud model used for phrasing only |