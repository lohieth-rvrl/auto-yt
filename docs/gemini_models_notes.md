# Gemini models: quick notes (for Tamil titles/tags)

Source: https://ai.google.dev/gemini-api/docs/models (page updated 2026-10-06)

## Text models to use (set in config.py -> GEMINI_MODEL)

| Model ID | Notes |
|---|---|
| `gemini-3.5-flash-lite` | Fastest, cheapest 3.5 model. Stable. **Best first choice for titles/tags.** |
| `gemini-3.1-flash-lite` | Older Lite model. Stable. Good backup. |
| `gemini-3.6-flash` | Stronger than Lite. Stable. Try if Tamil looks weak. |
| `gemini-3.7-flash` | Previous-generation Flash. Stable. |
| `gemini-3.8-flash` | Newest, strongest Flash. Probably busiest, so more 503 risk. |
| `gemini-3.5-flash` | Older Flash. Stable. |
| `gemini-3-flash-preview` | Preview: stricter limits, can be removed with short notice. |
| `gemini-3.1-pro-preview` | Pro: strongest but slower. Preview. Not needed for titles. |

## Aliases
- `gemini-flash-latest` = always the newest Flash. Google swaps what it points to,
  so behavior can change without warning. Busy = more 503 errors.

## Legacy / limited / gone
- `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`: only for people who already used them.
- `gemini-2.0-flash`, `gemini-2.0-flash-lite`: shut down (this is why the first run gave 404).
- `gemini-3.1-flash-lite-preview`, `gemini-3-pro-preview`: shut down.

## Not for titles (ignore these)
- Audio/voice: `gemini-3.8-live`, `*-tts`, `gemini-3.5-transcribe`
- Images: Nano Banana (`gemini-nano-banana-2.1`, `gemini-3.1-flash-image`, ...)
- Video: `veo-3.1-*`, `gemini-omni-1.1-flash`; Music: `lyria-*`
- Embeddings: `gemini-embedding-*`; Robotics; Deep Research / Antigravity agents

## Errors we hit
- 404 = wrong/shut-down model name
- 401 = key not accepted (check .env value / key sent in x-goog-api-key header)
- 503 = Google server busy; retry later or use a Lite model

## Our plan
1. `GEMINI_MODEL = "gemini-3.5-flash-lite"`
2. If Tamil quality is weak -> `gemini-3.6-flash`
3. Optional: script tries several models in order (not built yet)
