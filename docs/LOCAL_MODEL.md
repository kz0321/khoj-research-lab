# Optional local inference engine

The research application uses the configured DeepSeek service by default. The
optional local engine was prepared independently and stopped after validation;
neither `.env` nor the application on port 8778 was switched to it.

## Start, test, stop

Run these commands from the project root in PowerShell:

```powershell
# Required only on a new machine or if the portable files are absent.
.\.venv\Scripts\python.exe scripts\setup_local_model.py --backend both

# Vulkan0 was the NVIDIA RTX 5060 Laptop GPU on the tested machine.
.\scripts\start_local_model.ps1 -Backend vulkan -ContextSize 16384 -Threads 8

# One small local JSON-output test, independent of the application.
.\.venv\Scripts\python.exe scripts\probe_local_model.py

.\scripts\stop_local_model.ps1
```

The API address is `http://127.0.0.1:8999/v1`; the model alias is
`qwen2.5-1.5b-instruct`. On a machine without a suitable Vulkan GPU, stop the
existing engine and start with `-Backend cpu`. The CPU binary was downloaded and
verified, but CPU inference was not measured in this session. Before using Vulkan
on another machine, inspect `llama-server.exe --list-devices`; `Vulkan0` may refer
to a different adapter.

If deliberately switching the research application later, its supported settings
are `LLM_BASE_URL=http://127.0.0.1:8999/v1`,
`LLM_MODEL=qwen2.5-1.5b-instruct`, and a nonempty local placeholder for
`LLM_API_KEY`. Restart the application to load changed settings. Keep the existing
DeepSeek credential private and retain it for switching back. These settings have
not been applied to the delivered default application.

## What was actually tested

- Runtime: llama.cpp release **b12428**, pinned commit and published binary
  checksums recorded in `local-model-manifest.json`.
- Weights: official **Qwen2.5-1.5B-Instruct-GGUF**, **Q4_K_M**, 1,117,320,736
  bytes, pinned revision and official LFS SHA-256 verified.
- Final local test: OpenAI-compatible chat completion returned HTTP 200, parsed
  JSON, and the requested string evidence IDs `E1` and `E2`.
- Final measured call: **122 input tokens**, **70 output tokens**, **0.469 s**
  wall time, **149.25 output tokens/s including request overhead**, and
  **181.83 decode tokens/s** reported by the engine. These are one-call
  observations with already initialized GPU shaders, not a latency benchmark.
- The first cold test took 9.453 s and returned numeric evidence IDs. Its raw
  result is preserved in `local-model-probe-history.jsonl`. The final test used
  an explicit string-ID instruction and selected the discrete GPU only.
- Safe stop/restart and repeated-start detection were exercised.

This validates the optional inference engine and structured JSON transport. It
does **not** establish that the small local model completes the research
controller, passes verification, or reaches the proposal's benchmark targets.
The main project evaluation must state the model actually used.

## Sources and licenses

The local engine is MIT licensed; the model is Apache-2.0 licensed. Original
license text and model card are retained under `runtime/local-model/` and
`models/generative/`. The manifest records the exact upstream URLs and hashes;
setup can reproduce the downloads without distributing credentials.

Local artifacts use roughly 1.4 GB of disk. The optional server is bound to
loopback and is started only by its explicit script; it is not installed as an
automatically starting Windows service.
