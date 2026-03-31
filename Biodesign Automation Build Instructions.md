# Build Instructions — CRISPR Delivery Strategy Advisor

You are building a single MCP tool module called `delivery_advisor` into this repo. Read this entire document before writing any files.

---

## Context

This is a BioE 234 final project repo built on the MCP-Gemini starter framework. The framework auto-discovers tools by scanning `modules/`. Each tool is two files: a Python class and a JSON wrapper. You do not need to touch `server.py`, `client_gemini.py`, or `modules/__init__.py`.

Study the existing example module before writing anything:
- `modules/seq_basics/tools/reverse_complement.py` — see the class pattern
- `modules/seq_basics/tools/reverse_complement.json` — see the JSON wrapper pattern
- `modules/seq_basics/tools/prompts.json` — see the prompt format
- `modules/seq_basics/SKILL.md` — see the SKILL.md format

---

## What to build

A module that recommends CRISPR delivery methods given a cell type and Cas variant, using an **internal Gemini API call** (LLM-in-the-loop) to reason over the options.

---

## Step 1 — Create the folder structure

From the repo root:

```
modules/
  delivery_advisor/
    __init__.py             ← copy exactly from modules/seq_basics/__init__.py
    SKILL.md                ← create (spec below)
    tools/
      delivery_advisor.py   ← create (spec below)
      delivery_advisor.json ← create (spec below)
      prompts.json          ← create (spec below)
tests/
  test_delivery_advisor.py  ← create (spec below)
```

Copy `__init__.py` from seq_basics — do not write a new one.

---

## Step 2 — delivery_advisor.py

**File location:** `modules/delivery_advisor/tools/delivery_advisor.py`

**Pattern:** Follow the Function Object Pattern exactly as in `reverse_complement.py`. Class with `initiate()` and `run()` methods. No MCP imports. No `print()` statements. Return JSON-serialisable values only.

**Class name:** `DeliveryAdvisor`

**`run()` signature:**
```python
def run(self, cell_type: str, cas_variant: str, edit_type: str = "knockout") -> dict:
```

**What `initiate()` does:**
- Reads `GEMINI_API_KEY` from environment via `os.environ.get()`
- If not found, manually parses `.env` file at the repo root as a fallback (walk up from `__file__` four levels to find `.env`)

**What `run()` does:**
1. Validates inputs — raise `ValueError` with the parameter name in the message if `cell_type` or `cas_variant` is empty or whitespace-only. Default `edit_type` to `"knockout"` if empty.
2. Builds a user message string from the three inputs.
3. Makes a POST request to the Gemini API (`gemini-1.5-flash:generateContent`) using only `urllib.request` and `json` — no `requests` library, no `google.generativeai` SDK.
4. Parses the response and strips markdown code fences if present.
5. Parses the cleaned text as JSON.
6. Validates that the parsed result contains `top_recommendation`, `ranked_methods`, and `general_advice` keys — raise `RuntimeError` if any are missing.
7. Returns the parsed dict.

**System prompt to send to Gemini (use this exactly):**
```
You are an expert molecular biologist specializing in CRISPR delivery methods.
Given a cell type, Cas variant, and edit type, recommend the best delivery strategies.

Respond ONLY with a valid JSON object in this exact format, no other text:
{
  "top_recommendation": "<single best method as a short string>",
  "ranked_methods": [
    {
      "method": "<method name>",
      "suitability": "<high|medium|low>",
      "rationale": "<1-2 sentence explanation>",
      "key_considerations": ["<consideration 1>", "<consideration 2>"]
    }
  ],
  "general_advice": "<1-2 sentences of general advice for this specific combination>"
}

Include 3-5 methods in ranked_methods, ordered from most to least suitable.
Be specific to the cell type and Cas variant provided — do not give generic answers.
Consider: cargo size (plasmid vs RNP vs mRNA), cell division status, primary vs cell line,
immunogenicity, off-target integration risk, and edit type requirements.
```

**Gemini API call structure:**
```python
payload = json.dumps({
    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    "contents": [{"parts": [{"text": user_message}]}],
    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}
}).encode("utf-8")

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
```

**Docstring:** Include a full docstring following the pattern in `reverse_complement.py` — Description, Input, Output, and at least 4 test cases (including the empty input edge cases).

**Module-level alias at the bottom:**
```python
_instance = DeliveryAdvisor()
_instance.initiate()
delivery_advisor = _instance.run
```

---

## Step 3 — delivery_advisor.json

**File location:** `modules/delivery_advisor/tools/delivery_advisor.json`

Follow the exact schema from `reverse_complement.json`. Required fields:

```json
{
  "id": "org.bioe234.function.crispr.delivery_advisor.v1",
  "name": "CRISPR Delivery Strategy Advisor",
  "description": "Recommends and ranks CRISPR delivery methods (lipofection, electroporation, RNP, AAV, lentiviral, etc.) for a given cell type and Cas variant, with rationale and key considerations for each.",
  "type": "function",
  "keywords": ["CRISPR", "delivery", "transfection", "electroporation", "AAV", "RNP", "lipofection", "lentiviral", "Cas9"],
  "inputs": [
    { "name": "cell_type", "type": "string", "description": "..." },
    { "name": "cas_variant", "type": "string", "description": "..." },
    { "name": "edit_type", "type": "string", "description": "... Defaults to 'knockout' if not provided." }
  ],
  "outputs": [
    { "type": "object", "description": "A ranked list of delivery methods with suitability ratings, rationale, and key considerations, plus a top recommendation and general advice." }
  ],
  "examples": [ ... at least 2 examples ... ],
  "execution_details": {
    "language": "Python",
    "source": "modules/delivery_advisor/tools/delivery_advisor.py",
    "initialization": "initiate",
    "execution": "run",
    "disposal": null,
    "mcp_name": "crispr_delivery_advisor"
  }
}
```

Write realistic examples for HEK293+SpCas9+knockout and primary T cells+SpCas9+knockout.

---

## Step 4 — prompts.json

**File location:** `modules/delivery_advisor/tools/prompts.json`

An array of 5 objects. Each has `prompt`, `expected_tool`, `expected_args`, and `notes`. Follow the format in `modules/seq_basics/tools/prompts.json`.

Use `"expected_tool": "crispr_delivery_advisor"` for all entries.

Cover these 5 scenarios:
1. HEK293 + SpCas9 + knockout
2. Primary T cells + SpCas9 + knockout
3. Neuron + CBE4max base editor + base edit
4. iPSC + PE2 + prime edit
5. Hepatocyte + SaCas9 + knock-in

Write natural, realistic user prompts — the kind a researcher would actually type.

---

## Step 5 — SKILL.md

**File location:** `modules/delivery_advisor/SKILL.md`

Keep it under 200 lines. Include:

**Sections:**
1. What this module does (one paragraph on CRISPR delivery biology)
2. Tools and when to use them — describe `crispr_delivery_advisor`, its trigger phrases, parameter notes, output interpretation
3. Delivery method quick reference — a markdown table with columns: Method | Cargo type | Best for | Limitations. Cover: Lipofection, Electroporation (plasmid), RNP electroporation, AAV, Lentiviral, LNP (lipid nanoparticle), Microinjection
4. Key biological considerations — bullet points on: primary vs cell line, post-mitotic cells, cargo size constraints (plasmid ~5kb limit for AAV), immunogenicity, HDR requirement for knock-in

---

## Step 6 — test_delivery_advisor.py

**File location:** `tests/test_delivery_advisor.py`

Import pattern (match the existing test file in `tests/`):
```python
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.delivery_advisor.tools.delivery_advisor import DeliveryAdvisor
```

Use a `@pytest.fixture(scope="module")` that creates and initiates one `DeliveryAdvisor` instance shared across all tests.

**Write these 11 tests:**

| Test name | What it checks | Makes API call? |
|---|---|---|
| `test_hek293_returns_valid_structure` | All three top-level keys present, ranked_methods is a list with ≥1 item | Yes |
| `test_ranked_methods_have_required_fields` | Each method has method, suitability, rationale, key_considerations | Yes |
| `test_suitability_values_are_valid` | suitability is only "high", "medium", or "low" | Yes |
| `test_primary_t_cells_recommends_electroporation_or_rnp` | top_recommendation contains "electroporation" or "rnp" (case-insensitive) | Yes |
| `test_neuron_recommends_viral_delivery` | top_recommendation or any ranked method contains "aav" or "lentiviral" or "viral" | Yes |
| `test_default_edit_type` | Calling run() with only 2 args doesn't raise | Yes |
| `test_top_recommendation_is_nonempty_string` | isinstance str, len > 0 | Yes |
| `test_general_advice_is_nonempty_string` | isinstance str, len > 0 | Yes |
| `test_empty_cell_type_raises_value_error` | `pytest.raises(ValueError)` | No |
| `test_empty_cas_variant_raises_value_error` | `pytest.raises(ValueError)` | No |
| `test_whitespace_cell_type_raises_value_error` | `pytest.raises(ValueError)` with whitespace-only input | No |

---

## Step 7 — Verify it works

Run:
```bash
python client_gemini.py
```

Confirm you see:
```
[register] ✓ Tool registered: crispr_delivery_advisor
```

Then test with:
```
What delivery method should I use for a SpCas9 knockout in primary T cells?
```

If the tool registers but Gemini returns `[No text response]`, that is a known client quirk — the tool ran correctly.

Then run the tests:
```bash
pytest tests/test_delivery_advisor.py -vv
```

All 11 tests should pass. The 3 input-validation tests (no API call) should pass immediately. The 8 API tests depend on the Gemini key being set in `.env`.

---

## What NOT to do

- Do not edit `server.py`, `client_gemini.py`, or `modules/__init__.py`
- Do not import `mcp`, `fastmcp`, or any MCP-specific library in `delivery_advisor.py`
- Do not use `print()` inside the tool — return values only
- Do not use the `requests` library or `google.generativeai` SDK — use `urllib.request` only
- Do not commit `.env`
