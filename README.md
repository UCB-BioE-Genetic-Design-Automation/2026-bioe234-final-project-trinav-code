# BioE234 Final Project — CRISPR Delivery Strategy Advisor

**Student:** Trinav (GitHub: `trinav-code`, trinav@berkeley.edu)
**Team theme:** CRISPR experiment design pipeline
**Individual scope:** the *Delivery Strategy Advisor* MCP tool (`modules/delivery_advisor/`)

> The starter-guide content for running the MCP harness itself is preserved further down
> this README. This top section is the individual-contribution write-up for grading.

---

## 1. Problem & scope

CRISPR editing requires physically getting Cas protein + guide RNA (and sometimes a donor
template) into target cells. Picking the right delivery method is non-trivial:
- Easy cell lines → lipofection, but primary T cells / HSPCs → RNP electroporation.
- In-vivo liver, small Cas → AAV8 or LNP; large editors (BE / PE) exceed the AAV cargo
  limit and need dual-AAV, LNP (mRNA), or eVLP.
- Clinical / therapeutic contexts prefer transient delivery (RNP, LNP) over integrating
  lentivirus.

Researchers consult review articles or ask a colleague. My tool replaces that step with a
single MCP call.

**Tool:** `crispr_delivery_advisor` — takes cell type + Cas variant + edit type (or a full
upstream Construction File object) and returns a ranked list of delivery methods with
rationale, knowledge-base citations, general advice, and a kit-choice sanity-check
against the upstream builder.

## 2. Where it fits in the team pipeline

```
Guide RNA Designer ─► Off-Target Analyzer ─► Construction File Builder ─► [Delivery Advisor] ─► Validation Planner
                                                        │                       │
                                                        ▼                       ▼
                                                 construct object         ranked methods
                                                 (cell_type, cas_variant,  + kit_choice_consistency
                                                  edit_type, kit_choice,   (audits the builder's kit)
                                                  off_target_profile)
```

The advisor consumes the Construction File Builder's JSON output verbatim via its
`construct` input — no adapter, no field renaming. It also cross-checks the builder's
`kit_choice` against its own top recommendation and surfaces agreement or disagreement in
the output.

## 3. What makes the implementation unique

Most LLM-backed recommendation tools are "prompt the model and hope". This one is a
three-stage hybrid:

1. **Deterministic pre-filter** (`_prefilter` in `delivery_advisor.py`) — hard rules
   eliminate infeasible methods before the LLM ever sees them: AAV single vectors are
   dropped when the Cas variant's cargo exceeds 4.7 kb; hydrodynamic injection is dropped
   for human / clinical contexts (rodent-only); biolistics is dropped for non-plant cells;
   microinjection is dropped outside zygote / oocyte / embryo contexts. Excluded methods
   are passed to the LLM as a "do NOT recommend" block so the model can't re-introduce them.

2. **Knowledge-base-grounded LLM call** — the system prompt is rendered at runtime from
   `data/methods.json` (17 curated delivery methods + cargo-size table + decision
   heuristics). The KB lives as versioned JSON, not buried prose in the source — every
   edit shows up in `git diff`.

3. **Citation enforcement** — the LLM must cite the exact KB `key` values (e.g.
   `rnp_electroporation`, `dual_aav`) that justified each recommendation. Post-call, the
   advisor validates every citation against the KB's real keys and annotates
   `_citation_warnings` if any are hallucinated. A pytest asserts there are zero
   hallucinations on the reference HEK293 case.

This means a reviewer (or grader) can trace any recommendation back to a specific KB
entry, and the system can't silently invent a method.

**Pipeline integration layer:** when a `construct` object is passed, the advisor surfaces
`kit_choice` and `off_target_risk_profile` to the LLM, which fills a
`kit_choice_consistency` block in the output — a sanity-check for the upstream kit
selection.

## 4. Inputs / outputs

**Inputs** (either of):
- Explicit: `cell_type: str`, `cas_variant: str`, `edit_type: str = "knockout"`
- Pipeline: `construct: dict` (upstream Construction File Builder output)

**Output:** structured JSON
```jsonc
{
  "top_recommendation": "Lipofection",
  "ranked_methods": [
    { "method": "...", "suitability": "high|medium|low",
      "rationale": "...", "key_considerations": [...],
      "citations": ["lipofection", "rnp_electroporation"] }
  ],
  "general_advice": "...",
  "kit_choice_consistency": {           // null-filled if no kit_choice given
    "kit_choice": "lentiCRISPRv2",
    "consistent": false,
    "note": "Upstream chose lentiCRISPRv2 (integrating), but for HEK293 SpCas9 KO, transient lipofection is preferred — integration is unnecessary and adds off-target risk."
  },
  "excluded_by_prefilter": ["aav_single excluded: ABE8e cargo ~5.5 kb > AAV limit 4.7 kb"]
}
```

## 5. Files for this contribution

| File | Rubric component |
|------|------------------|
| `modules/delivery_advisor/tools/delivery_advisor.py` | Function Code |
| `modules/delivery_advisor/tools/delivery_advisor.json` | MCP Wrapper |
| `modules/delivery_advisor/tools/prompts.json` | Test Prompts (11 prompts) |
| `modules/delivery_advisor/data/methods.json` | Knowledge base (17 methods) |
| `modules/delivery_advisor/SKILL.md` | AI guidance |
| `tests/test_delivery_advisor.py` | Pytest (26 tests) |
| `tests/eval_delivery_advisor.py` | Accuracy eval harness (22 cases) |
| `tests/eval_results.json` | Last eval run summary (22/22 = 100%) |
| `delivery_advisor_theory.md` | Theory docs (biology rationale + 3-stage hybrid) |

## 6. Running it

```bash
source .venv/bin/activate
pip install -r requirements.txt
# Create .env with ANTHROPIC_API_KEY (advisor uses Claude Haiku 4.5 internally)

# Unit + integration tests (input validation + live API)
pytest tests/test_delivery_advisor.py -v

# Accuracy eval (22 canonical cases — takes ~4 minutes)
# Last run: 22/22 top-recommendation accuracy, 22/22 citations valid (see tests/eval_results.json)
python tests/eval_delivery_advisor.py --verbose

# Full MCP pipeline (uses Gemini as the outer LLM, per course setup)
python client_gemini.py
```

Try a prompt like *"What delivery method should I use for a SpCas9 knockout in HEK293 cells?"*

## 7. Latest eval results

| Metric | Result |
|---|---|
| Top-recommendation accuracy | **22/22 (100%)** |
| Citations resolve to real KB keys | 22/22 (100%) |
| Errors / API failures | 0/22 |
| Total runtime | 255 s (Claude Haiku 4.5) |

Cases cover easy cell lines, primary/ex vivo (T cells, HSPCs, iPSCs), cargo-size constraints (large editors → no single AAV), in-vivo small-Cas (AAV serotype tropism), post-mitotic neurons, plant cell walls (biolistics / Agrobacterium), zygote microinjection, pooled CRISPR screens, in-vivo HDR, and two pipeline-construct cases (kit agreement + kit disagreement). Full machine-readable summary in `tests/eval_results.json`.

---

## 1. What is this starter?

This repository is a framework for building **bioengineering automation tools** that an AI assistant can call via **MCP (Model Context Protocol)**.

The framework handles connecting your Python codes to the AI.

### Four design principles

1. **You write pure Python** — biology logic only, no networking or MCP code required.  
2. **Convention over configuration** — the framework auto-discovers your files by name.  
3. **No plumbing in your tool files** — you never import MCP or registration code.  
4. **Copy >> modify >> extend** — start from the examples and edit them.

---

## 2. Project structure

```
.
├── server.py                      # MCP server — do not edit
├── client_gemini.py               # Gemini CLI client — do not edit
├── requirements.txt
│
├── tests/
│   └── test_tools.py
│
└── modules/
    ├── __init__.py                # Scans all sub-modules — do not edit
    │
    └── seq_basics/                # EXAMPLE MODULE (copy this for your project)
        ├── __init__.py
        ├── SKILL.md               # AI guidance for this module (optional)
        ├── _utils.py              # Shared constants (codon table, etc.)
        ├── _plumbing/             # Auto-registration internals — do not edit
        │   ├── __init__.py
        │   ├── register.py
        │   └── resolve.py
        ├── data/
        │   └── pBR322.gb          # Sequence data files go here
        └── tools/
            ├── reverse_complement.py    # Example: Python implementation
            ├── reverse_complement.json  # Example: C9 JSON wrapper
            ├── translate.py
            ├── translate.json
            └── prompts.json             # Example test prompts
```

> **Where you spend your time:** `modules/<your_module>/tools/` and `modules/<your_module>/data/`.

---

## 3. How the pipeline works

```
python client_gemini.py
        │
        ├─► launches server.py as a subprocess
        │         │
        │         └─► scans modules/  (one folder per project)
        │                   └─► for each folder: reads .py + .json pairs, registers tools
        │                                         reads .gb / .fasta files, registers resources
        │
        ├─► connects to server, lists tools and resources
        │
You:    └─► type a request
                │
                ▼
            Gemini decides which tool to call and with what arguments
                │
                ▼
            server calls your Python function
                │
                ▼
            result returned to Gemini, which explains it to you
```

---

## 4. Quick start

### Step 0 — Prerequisites
- Python 3.10 or newer
- Visual Studio Code — [code.visualstudio.com](https://code.visualstudio.com)

### Step 1 — Create a virtual environment

Open a terminal in VS Code (`Terminal >> New Terminal`):

```bash
python -m venv .venv
source .venv/bin/activate        # Mac / Linux
# .venv\Scripts\activate         # Windows
```

You should see `(.venv)` at the start of your terminal line. Then install dependencies:

```bash
pip install -r requirements.txt
```

### Step 2 — Get your Gemini API key

1. Go to **[https://aistudio.google.com/api-keys](https://aistudio.google.com/api-keys)**
2. Sign in with your **UC Berkeley Google account** (free access is included).
3. Click **"Create API Key"** and copy the key.
4. In the project root folder, create a file named exactly **`.env`** containing:

```
GEMINI_API_KEY="paste_your_key_here"
```

> 🔴 **Security warning:** Never upload `.env` to GitHub. Ensure `.env` is listed in `.gitignore`. 
Run this in your project folder: 
> echo ".env" >> .gitignore

### Step 3 — Run the client

```bash
python client_gemini.py
```

Expected output:
```
[server] Starting BioE234 MCP server...
[register] ✓ Tool registered:    dna_reverse_complement
[register] ✓ Tool registered:    dna_translate
[register] ✓ Resource registered: pBR322  (...)
[server] All modules registered. Server ready.

Connected to MCP server.
Discovered tools:
  - dna_reverse_complement: Return the reverse complement of a DNA sequence...
  - dna_translate: Translate DNA to protein...
```

Try typing:
```
Translate the first 60bp of pBR322 in frame 1
```

Then you should get:
```
Gemini: The first 60bp of pBR322 translated in frame 1 is FSCLTAYHR*ALMR*FITVK.
```

---

## 5. Each tool is TWO files

For every tool you build you create **two files with the same stem name** in your `tools/` folder:

```
gc_content.py     ← Python implementation (the biology logic)
gc_content.json   ← C9 JSON wrapper      (the metadata / schema)
```

**There is no third "wrapper" file.** The `.json` file *is* your C9 wrapper. It is what the grading rubric means when it says "C9 Wrapper". The Python file holds only biology code — no MCP-specific code at all.

---

## 6. The Python file - Function Object Pattern

Your Python file must follow the **Function Object Pattern**: a class with `initiate()` and `run()` methods, and a structured docstring. This is the same pattern used throughout the course.

- **`initiate()`** — one-time setup (build lookup tables, load config, etc.)
- **`run()`** — the actual computation; called once per tool invocation

### Template

```python
class GcContent:
    """
    Description:
        Computes the fraction of G and C bases in a DNA sequence.

    Input:
        seq (str): DNA sequence (resource name or raw string).

    Output:
        float: GC fraction between 0.0 and 1.0.

    Tests:
        - Case:
            Input: seq="ATGCATGC"
            Expected Output: 0.5
            Description: Balanced sequence, 50% GC.
        - Case:
            Input: seq="AAAA"
            Expected Output: 0.0
            Description: All A bases, 0% GC.
        - Case:
            Input: seq=""
            Expected Output: 0.0
            Description: Edge case — empty sequence returns 0.
    """

    def initiate(self) -> None:
        pass   # nothing to set up for this tool

    def run(self, seq: str) -> float:
        """Return GC fraction between 0 and 1."""
        seq = seq.upper()
        gc = sum(1 for b in seq if b in "GC")
        return gc / len(seq) if seq else 0.0


# Optional: module-level alias so pytest can import the function directly.
_instance = GcContent()
_instance.initiate()
gc_content = _instance.run   # gc_content("ATGC") → 0.5
```

### Naming rule — critical

> ⚠️ **Name your file after what it does, not `bio_functions.py`.**  
> If every student uses `bio_functions.py`, files will conflict.

Good names: `gc_content.py`, `find_pam_sites.py`, `design_primers.py`, `codon_count.py`

The **class name** can be anything descriptive. The **file name** is what you use in the JSON wrapper's `execution_details.source`.

### Rules
- Always add type hints: `seq: str`, `frame: int`, `pam: str = "NGG"`, etc.
- Return JSON-serialisable values: `str`, `int`, `float`, `list`, `dict`.
- Raise `ValueError` with clear messages for invalid inputs.
- Never `print()` inside a tool — return values instead.

---

## 7. The JSON file — C9 wrapper

The `.json` file formally describes your tool. It follows the schema in [`Function_Development_Specification.md`](Function_Development_Specification.md) and is what the grader evaluates as the "C9 Wrapper" component.

### Template

```json
{
  "id": "org.bioe234.function.seq.gc_content.v1",
  "name": "DNA GC Content",
  "description": "Compute the GC content (fraction of G and C bases) of a DNA sequence.",
  "type": "function",
  "keywords": ["DNA", "GC content", "sequence analysis"],
  "date_created": null,
  "date_last_modified": null,

  "inputs": [
    {
      "name": "seq",
      "type": "string",
      "description": "DNA sequence. Accepts a resource name (e.g. 'pBR322') or a raw sequence string."
    }
  ],

  "outputs": [
    {
      "type": "number",
      "description": "GC fraction between 0.0 (no GC) and 1.0 (all GC)."
    }
  ],

  "examples": [
    {
      "input":  { "seq": "ATGCATGC" },
      "output": { "result": 0.5 }
    },
    {
      "input":  { "seq": "AAAA" },
      "output": { "result": 0.0 }
    }
  ],

  "execution_details": {
    "language": "Python",
    "source": "modules/seq_basics/tools/gc_content.py",
    "initialization": "initiate",
    "execution": "run",
    "disposal": null,

    "mcp_name": "dna_gc_content",
    "seq_params": ["seq"]
  }
}
```

### Required fields

| Field | Notes |
|-------|-------|
| `id` | Unique ID in the format `org.bioe234.function.<domain>.<name>.v1` |
| `name` | Human-readable display name |
| `description` | One clear sentence describing what the tool does |
| `type` | Always `"function"` |
| `keywords` | List of relevant terms |
| `inputs` | Array — each entry needs `name`, `type`, `description` |
| `outputs` | Array — each entry needs `type`, `description` |
| `examples` | Array — at least one `{input, output}` pair |
| `execution_details.language` | `"Python"` |
| `execution_details.source` | Path to your `.py` file |
| `execution_details.execution` | `"run"` |
| `execution_details.mcp_name` | The tool identifier Gemini will use (snake_case) |

`execution_details.mcp_name` and `execution_details.seq_params` are framework-specific extensions — they exist inside `execution_details` because they are about how your code runs, not what it does biologically.

### Supported input/output types
`string`, `integer`, `number`, `boolean`, `array`, `object`

---

## 8. Tools with multiple input parameters

```python
# hamming_distance.py
class HammingDistance:
    def initiate(self): pass
    def run(self, seq1: str, seq2: str) -> int:
        if len(seq1) != len(seq2):
            raise ValueError("Sequences must have equal length.")
        return sum(a != b for a, b in zip(seq1, seq2))
```

In your JSON, list both names under `seq_params`:

```json
"execution_details": {
  ...,
  "mcp_name": "dna_hamming_distance",
  "seq_params": ["seq1", "seq2"]
}
```

Both `seq1` and `seq2` can be resource names or raw sequences.

---

## 9. Non-sequence tools

If your tool does not take a DNA/RNA sequence, **omit `seq_params`** entirely:

```python
# restriction_site_count.py
class RestrictionSiteCount:
    def initiate(self): pass
    def run(self, dna: str, site: str) -> int:
        return dna.upper().count(site.upper())
```

```json
"execution_details": {
  "language": "Python",
  "source": "modules/seq_basics/tools/restriction_site_count.py",
  "initialization": "initiate",
  "execution": "run",
  "mcp_name": "dna_restriction_site_count"
}
```

---

## 10. How sequences are resolved automatically

When a parameter is listed in `seq_params`, the framework automatically converts it before your `run()` is called:

| What you pass | What `run()` receives |
|---|---|
| `"pBR322"` | Full 4361bp sequence string |
| `">seq1\nATGC..."` | `"ATGC"` |
| `"LOCUS pBR322 ..."` | Full sequence string |
| `"ATGCGATCG"` | `"ATGCGATCG"` |
| `"ATG CGA\n1 TCG"` | `"ATGCGATCG"` (whitespace/numbers stripped) |

Your function always receives a clean uppercase string. No file parsing needed.

---

## 11. Adding sequence data files

Drop `.gb` or `.fasta` files into `modules/<your_module>/data/`. Restart the server and they are immediately available as resources.

```
data/
  pBR322.gb       →  resource name "pBR322"
  mg1655.fasta    →  resource name "mg1655"
```

---

## 12. Test prompts — prompts.json

You must submit a `prompts.json` file alongside your tool. Each entry is a natural-language prompt a user might type, paired with the expected tool call. See `modules/seq_basics/tools/prompts.json` for the exact format.

```json
[
  {
    "prompt": "What is the GC content of ATGCATGC?",
    "expected_tool": "dna_gc_content",
    "expected_args": { "seq": "ATGCATGC" },
    "notes": "Basic raw sequence input."
  }
]
```

---
## 13. SKILL.md — Guiding the AI

Each module can contain a `SKILL.md` file. When found, its contents are automatically
injected into Gemini's system prompt at startup, giving the AI background knowledge
it needs to use your tools correctly.

**Is it required?** No. The system works without it. But without it, Gemini has only the
short `description` fields from your `.json` wrappers to go on. A good `SKILL.md`
meaningfully improves the quality of Gemini's responses — it knows what your resources
contain, how to interpret results, and what edge cases to watch for.

**What to put in it:**
- What the module does in one paragraph
- A table of your resources and what they contain
- For each tool: when to use it, what the parameters mean, how to interpret the output
- Any domain vocabulary or biological context Gemini needs

**Template** — create `modules/<your_module>/SKILL.md`:

```markdown
# <your_module> — Skill Guidance for Gemini

## What this module does
One paragraph describing the biological domain and purpose of this module.

## Available resources
| Resource name | Description |
|---------------|-------------|
| `my_genome`   | E. coli K-12 MG1655 complete genome, 4.6 Mbp. |

## Tools and when to use them

### `my_tool_mcp_name`
What it computes and when Gemini should call it.
- Trigger phrases: "find X", "scan for Y", "does this sequence contain Z"
- Parameter notes: what each parameter means in plain language
- Output notes: how to interpret the result

## Interpreting results
Any domain knowledge that helps Gemini explain results correctly.
```

**See `modules/seq_basics/SKILL.md` for a complete working example.**

> **Token budget:** SKILL.md is included in every request. Keep it under ~300 lines.
> Long files increase cost and can push other context out of Gemini's window.

---



## 14. Creating your own module

```
modules/
  <your_module>/
    __init__.py          ← copy from seq_basics/ (can be empty)
    SKILL.md             ← describe what this module does for the AI
    data/
      my_genome.gb       ← example data
    tools/
      find_pam.py        ← example tool 1
      find_pam.json      ← example json file for tool 1
      prompts.json       ← example tool 2
      test_find_pam.py   ← example json file for tool 2
```

`modules/__init__.py` auto-discovers new folders — you do not need to edit it.

---

## 15. Running tests

```bash
pytest -vv -l
```

Write tests that cover both typical inputs and edge cases. See `tests/test_tools.py` for examples — it shows how to test both the class directly and via the module-level alias.

---

## 16. What to submit

| File | Grading component |
|------|------------------|
| `<tool_name>.py` | Function Code |
| `<tool_name>.json` | C9 Wrapper |
| `prompts.json` | Test Prompts |
| `test_<tool_name>.py` | Pytest |
| `README.md` | Documentation |
| `<your_functions_docs>.md` | Theory Docs |

Submit your GitHub repo URL on bCourses. The repo should reflect your **individual** contribution, not the whole team's work.

---

## 17. Troubleshooting

**Tool doesn't appear after startup**  
Look for `[register] WARNING` lines in the terminal. The message will say exactly what is missing — usually a `.json` wrapper file, a missing `run()` method, or a malformed JSON.

**API key error**  
Ensure `.env` is in the project root (not a subfolder) and contains `GEMINI_API_KEY="..."`. Restart the terminal after creating the file.

**Gemini 503**  
Server busy. Wait 30 seconds — the client retries automatically.

**`python` not found**  
Use `python3` on Mac/Linux.

**`ModuleNotFoundError`**  
Activate your virtual environment first: `source .venv/bin/activate`.

---

## Still stuck?

Email your TA: **javadamn@berkeley.edu**
