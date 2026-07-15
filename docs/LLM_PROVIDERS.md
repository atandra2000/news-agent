# LLM Providers

> How newsagent wires LLM providers, role routing, model catalogs, tiers, and the
> reasoning-token starvation pitfall.

---

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          LLMRouter                                    │
│  complete(role, prompt) → walks role.chain → provider.complete()      │
│  ┌─ token budget guard                                                │
│  ├─ fallback chain (first success wins)                              │
│  ├─ empty-text-as-failure detection                                   │
│  ├─ heuristic fallback (if allowed_heuristic_fallback=True)           │
│  └─ accounting (prompt_tokens, completion_tokens, cost)               │
└────────────────┬─────────────────────────────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │     ModelRegistry       │
    │  provider_for(model)    │
    │  model_name(model)      │
    └────┬───────────┬────────┘
         │           │
┌────────┴──┐  ┌────┴──────┐  ┌───────────────┐
│  Ollama   │  │OpenCodeGo │  │OpenAICompatible│
│  Provider │  │  Provider │  │   Provider     │
│ /api/chat │  │/chat/comp │  │ /chat/completions│
└───────────┘  └───────────┘  └───────────────┘
```

---

## 2. Roles → tiers → models

The router uses a **three-level indirection** so the whole fleet can be
repointed in one place:

```
role (label, write, research, ...)
  → tier (cheap, writer, critic, plan)
    → model chain (deepseek-v4-flash, kimi-k2.6, deepseek-v4-pro, ...)
```

### 2.1 Roles (`newsagent/llm/roles.py`)

Each role has: a `chain` (ordered fallback), `temperature`, `max_tokens`,
`num_ctx`, `keep_alive`.

| Role | Tier | Temperature | max_tokens | Used by |
|------|------|-------------|------------|---------|
| `research` | writer | 0.2 | 3000 | Pipeline analyzer |
| `reason` | critic | 0.2 | 2500 | Verification, comparison |
| `summarize` | cheap | 0.2 | 1200 | Summarization |
| `compare` | critic | 0.2 | 2000 | Comparison |
| `markdown` | cheap | 0.2 | 2500 | Markdown formatting |
| `proofread` | cheap | 0.1 | 1500 | Proofreading |
| `critic` | critic | 0.1 | 2000 | Self-critique loop |
| `plan` | plan | 0.2 | 1500 | Query planning |
| `verify` | critic | 0.1 | 1500 | Claim verification |
| `label` | cheap | 0.2 | 64 | Cluster labels |
| `write` | writer | 0.3 | 4000 | Report section writing |
| `brief_write` | writer | 0.3 | 5000 | Brief pipeline section writing |
| `brief_plan` | plan | 0.2 | 1500 | Brief query planning |

### 2.2 Tiers (`newsagent/llm/catalog.py`)

Each provider has an ordered fallback chain per tier. First success wins.

**Ollama catalog** (verified live on `https://api.ollama.com/api/tags`):

| Tier | Chain (primary first) |
|------|----------------------|
| `writer` | `deepseek-v4-pro` → `kimi-k2.6` → `glm-5.2` |
| `critic` | `kimi-k2.6` → `deepseek-v4-pro` → `glm-5.2` |
| `plan` | `kimi-k2.6` → `deepseek-v4-flash` → `deepseek-v4-pro` |
| `cheap` | `deepseek-v4-flash` → `kimi-k2.6` → `gemma3:4b` |

**OpenCode Go catalog** (verified live on `https://opencode.ai/zen/go/v1/models`):

| Tier | Chain (primary first) |
|------|----------------------|
| `writer` | `deepseek-v4-pro` → `kimi-k2.6` → `glm-5.2` |
| `critic` | `kimi-k2.6` → `deepseek-v4-pro` → `glm-5.2` |
| `plan` | `kimi-k2.6` → `deepseek-v4-flash` → `deepseek-v4-pro` |
| `cheap` | `deepseek-v4-flash` → `kimi-k2.6` → `qwen3.7-plus` |

---

## 3. Providers

### 3.1 OllamaProvider (`newsagent/llm/providers/ollama.py`)

- **Endpoints:** `/api/chat` (primary) with fallback to `/api/generate`.
- **Auth:** `Authorization: Bearer <key>` when `api_key` is set.
- **Format:** Supports `format: "json"` for JSON-mode output.
- **Options:** `num_ctx`, `keep_alive` (model residency between calls).
- **Model list:** `GET /api/tags` → used by `newsagent models`.

### 3.2 OpenCodeGoProvider (`newsagent/llm/providers/opencode_go.py`)

- **Endpoint:** `/chat/completions` (OpenAI-compatible).
- **Auth:** `Authorization: Bearer <key>` (required).
- **Format:** `response_format: {"type": "json_object"}` for JSON mode.
- **Model list:** `GET /models` → used by `newsagent models`.

### 3.3 OpenAICompatibleProvider (`newsagent/llm/providers/openai_compatible.py`)

- **Endpoint:** `/chat/completions` (any OpenAI-compatible).
- **Auth:** `Authorization: Bearer <key>` when `api_key` is set.
- **Format:** `response_format: {"type": "json_object"}` for JSON mode.
- **Model list:** No list endpoint — set model id in `NEWSAGENT_LLM_OPENAI_MODEL`.

---

## 4. Provider routing

`build_registry()` in `newsagent/llm/providers/registry.py` constructs the
provider set based on `NEWSAGENT_LLM_BACKEND`:

| Backend | Default provider | `default_model` | Behavior |
|---------|-----------------|-----------------|----------|
| `ollama` | OllamaProvider | None | Role chains route via `OLLAMA_CATALOG` |
| `opencode_go` | OpenCodeGoProvider | None or set | Blank → per-tier catalog routing; set → all roles use one model |
| `openai` | OpenAICompatibleProvider | set (required) | All roles use `OPENAI_MODEL` |

### `model_name()` resolution

```python
def model_name(self, model: str) -> str:
    # 1. Strip "provider:" prefix (ollama:llama3 → llama3)
    # 2. If opencode_go/openai and default_model is set → return default_model
    # 3. If opencode_go and default_model is None → return chain model (catalog routing)
    # 4. Otherwise → return model as-is
```

---

## 5. The reasoning-token starvation pitfall

**Problem:** Reasoning models (e.g. `glm-5.2`, `glm-5.1`, `qwen3.7-max`) write
to `reasoning_content` and only populate `content` **after** reasoning finishes.
If `max_tokens` is too small, all tokens go to reasoning and `content` is empty.

**Impact on newsagent:** The `label` role uses `max_tokens=64`. If `glm-5.1` is
the default model, `label` calls return empty `content` → the router treats
this as a failure → falls back to heuristics → cluster labels degrade.

**Solution:** Per-tier catalog routing. The `cheap` tier uses
`deepseek-v4-flash` (returns content at `max_tokens=64`, ~25 completion tokens).
Reasoning-heavy models are only in the `writer` tier where `max_tokens>=3000`.

**Verified working models** (tested at `max_tokens=64/200/1200`):

| Model | mt=64 | mt=200 | Completion tokens |
|-------|-------|--------|-------------------|
| `deepseek-v4-flash` | OK | OK | 25 (fastest) |
| `kimi-k2.6` | OK | OK | 36 |
| `deepseek-v4-pro` | OK | OK | ~35-45 |
| `qwen3.7-plus` | OK | OK | ~220 |
| `glm-5.2` | empty | OK | ~140 (too heavy for cheap) |
| `glm-5.1` | empty | — | reasoning-heavy |

---

## 6. Router behavior

### 6.1 Fallback chain

```
for model in role.chain:
    provider = registry.provider_for(model)
    result = await provider.complete(real_model, prompt, ...)
    if result.text.strip():
        return result  # success
    # empty text → treated as failure, try next
if allow_heuristic_fallback:
    return ProviderResult(text="", model="heuristic", provider="heuristic")
raise LLMError("All providers failed")
```

### 6.2 Token budget guard

```python
if self.stats.total_tokens > self.token_budget:
    raise LLMError(f"Token budget {self.token_budget} exceeded")
```

### 6.3 JSON completion

`json_complete()` calls `complete()` with `format="json"`, then:
1. Strips markdown code fences if present.
2. Parses JSON.
3. If parse fails, tries to find the first `{...}` span.
4. Returns `{}` on failure or heuristic fallback.

### 6.4 Accounting

`RouterStats` tracks: `prompt_tokens`, `completion_tokens`, `calls`,
`failures`, `by_provider` (dict), `cost_per_1k_tokens`.

---

## 7. Verifying your provider

```bash
# List all models on the live endpoint + check catalog alignment.
newsagent models
```

Output:

```
OpenCode Go endpoint: https://opencode.ai/zen/go/v1
Available on endpoint: 20 models

  - deepseek-v4-flash
  - deepseek-v4-pro
  - glm-5.2
  - kimi-k2.6
  ...

Curated catalog tiers (newsagent/llm/catalog.py):
  [writer] deepseek-v4-pro > kimi-k2.6 > glm-5.2   (✓ ✓ ✓)
  [critic] kimi-k2.6 > deepseek-v4-pro > glm-5.2   (✓ ✓ ✓)
  [plan] kimi-k2.6 > deepseek-v4-flash > deepseek-v4-pro   (✓ ✓ ✓)
  [cheap] deepseek-v4-flash > kimi-k2.6 > qwen3.7-plus   (✓ ✓ ✓)

✓ = present on endpoint · = not found (will 404 / fall back).
```

---

## 8. Adding a new provider

1. Create `newsagent/llm/providers/<name>.py` with a class subclassing
   `BaseProvider`:
   ```python
   class MyProvider(BaseProvider):
       name = "my_provider"

       async def complete(self, model, prompt, *, system=None, temperature=0.2,
                          max_tokens=2048, timeout=120.0, num_ctx=None,
                          keep_alive=None, format=None) -> ProviderResult:
           # ... HTTP call ...
           return ProviderResult(text=..., model=model, provider=self.name,
                                 prompt_tokens=..., completion_tokens=...)
   ```
2. Register it in `newsagent/llm/providers/registry.py: build_registry()`.
3. Add a catalog entry in `newsagent/llm/catalog.py` if it has tier-specific
   models.
4. Add a `NEWSAGENT_LLM_<NAME>_*` settings group in `newsagent/config.py: LLMConfig`.
5. Add a `newsagent models` branch in `cli.py: _cmd_models()` to list its models.