"""CRISPR Delivery Strategy Advisor.

Uses an internal Claude API call to recommend delivery methods
for a given cell type, Cas variant, and edit type.

The knowledge base is loaded at initiate() time from
modules/delivery_advisor/data/methods.json and rendered into the system
prompt. This makes the input to the LLM a reviewable, versioned artifact
(auditability) rather than prose embedded in source.
"""

import json
import os
import urllib.request


SYSTEM_PROMPT_HEADER = """You are an expert molecular biologist specializing in CRISPR delivery methods.
Given a cell type, Cas variant, and edit type, recommend the best delivery strategies by
reasoning over the curated knowledge base below. Prefer methods from this reference set;
cite their tradeoffs explicitly in your rationale and list the exact method `key` values
you relied on in the `citations` field of each recommendation."""


SYSTEM_PROMPT_FOOTER = """============================================================
OUTPUT FORMAT
============================================================

Respond ONLY with a valid JSON object in this exact format, no other text:
{
  "top_recommendation": "<single best method name as a short string>",
  "ranked_methods": [
    {
      "method": "<method name>",
      "suitability": "<high|medium|low>",
      "rationale": "<1-2 sentence explanation referencing cargo size, tropism, or other specific tradeoffs from the KB>",
      "key_considerations": ["<consideration 1>", "<consideration 2>"],
      "citations": ["<kb_method_key_1>", "<kb_method_key_2>"]
    }
  ],
  "general_advice": "<1-2 sentences of general advice for this specific combination>",
  "kit_choice_consistency": {
    "kit_choice": "<the kit_choice passed in, or null if none>",
    "consistent": <true|false|null>,
    "note": "<1 sentence: does the kit_choice match top_recommendation? if not, why the advisor disagrees. null if no kit_choice was provided>"
  }
}

Include 3-5 methods in ranked_methods, ordered from most to least suitable.
The `citations` field MUST contain the exact `key` values (e.g. "rnp_electroporation",
"dual_aav") from the knowledge base whose facts justified the rationale. Every
recommendation must be traceable back to at least one KB key.
Be specific to the cell type and Cas variant provided — do not give generic answers.
Explicitly consider: cargo size vs AAV limit, cell division status, primary vs cell line,
in vivo vs ex vivo, immunogenicity, integration risk, and edit type requirements.
If the editor exceeds the AAV cargo limit, DO NOT recommend single AAV — use dual-AAV,
LNP, eVLP, or electroporation instead.
If an upstream `kit_choice` is provided (e.g. from a Construction File Builder), populate
`kit_choice_consistency` to flag agreement or disagreement with your top recommendation —
this is a sanity-check for the pipeline. If no kit_choice is given, set all three fields to null.
If an `off_target_risk_profile` is provided and shows a high off-target burden, prefer
transient delivery (RNP, LNP, eVLP) over sustained-expression methods to limit exposure."""


def _render_kb(kb: dict) -> str:
    """Render the structured KB JSON into a text block for the system prompt."""
    lines = []
    lines.append("=" * 60)
    lines.append("DELIVERY METHOD KNOWLEDGE BASE")
    lines.append("=" * 60)
    lines.append("")

    # Cargo size reference
    cargo_ref = kb.get("cargo_size_reference_kb", {})
    if cargo_ref:
        lines.append("Cargo-size reference (kb):")
        for editor, size in cargo_ref.items():
            lines.append(f"  - {editor}: ~{size} kb")
        lines.append(f"AAV packaging limit: ~{kb.get('aav_cargo_limit_kb', 4.7)} kb")
        lines.append("")

    # Methods
    lines.append(f"Methods ({len(kb.get('methods', []))} total):")
    lines.append("")
    for m in kb.get("methods", []):
        lines.append(f"[key: {m['key']}] {m['name']}  (category: {m['category']})")
        if m.get("cargo_types"):
            lines.append(f"  cargo_types: {', '.join(m['cargo_types'])}")
        if m.get("cargo_limit_kb") is not None:
            lines.append(f"  cargo_limit_kb: {m['cargo_limit_kb']}")
        if m.get("compatible_cells"):
            lines.append(f"  compatible_cells: {', '.join(m['compatible_cells'])}")
        if m.get("incompatible_cells"):
            lines.append(f"  incompatible_cells: {', '.join(m['incompatible_cells'])}")
        lines.append(f"  in_vivo: {m.get('in_vivo')}  integration_risk: {m.get('integration_risk')}  immunogenicity: {m.get('immunogenicity')}  clinical_stage: {m.get('clinical_stage')}")
        if m.get("pros"):
            lines.append(f"  pros: {'; '.join(m['pros'])}")
        if m.get("cons"):
            lines.append(f"  cons: {'; '.join(m['cons'])}")
        if m.get("references"):
            lines.append(f"  references: {'; '.join(m['references'])}")
        lines.append("")

    # Heuristics
    heuristics = kb.get("decision_heuristics", [])
    if heuristics:
        lines.append("=" * 60)
        lines.append("DECISION HEURISTICS")
        lines.append("=" * 60)
        for h in heuristics:
            lines.append(f"- {h}")
        lines.append("")

    return "\n".join(lines)


def _estimate_cargo_kb(cas_variant: str, kb: dict) -> float | None:
    """Look up the approximate cargo size (kb) for a Cas variant.

    Tries exact match first, then prefix match (e.g. "ABE8e" -> "ABE").
    Returns None if no match is found — the LLM will handle unknowns.
    """
    ref = kb.get("cargo_size_reference_kb", {})
    variant = cas_variant.strip()

    # Exact match
    if variant in ref:
        return ref[variant]

    # Prefix match: ABE8e -> ABE, CBE4max -> CBE, PE3 -> PE3 or PE2
    for prefix in sorted(ref.keys(), key=len, reverse=True):
        if variant.upper().startswith(prefix.upper()):
            return ref[prefix]

    return None


def _classify_off_target_burden(profile: dict | str | None) -> str:
    """Classify an upstream off_target_risk_profile as low/medium/high.

    Accepts either a structured dict (Yushan's output:
    {"total_off_targets": N, "mismatch_distribution": {"0MM": ..., ...}})
    or a free-form string ("low", "medium", "high"). Falls back to "unknown".

    Heuristic: any 0MM or 1MM hit ⇒ HIGH (perfect/near-perfect off-target);
    total_off_targets >= 5 ⇒ HIGH; total_off_targets >= 2 ⇒ MEDIUM;
    otherwise LOW.
    """
    if profile is None:
        return "unknown"
    if isinstance(profile, str):
        s = profile.strip().lower()
        return s if s in ("low", "medium", "high") else "unknown"
    if not isinstance(profile, dict):
        return "unknown"

    mm = profile.get("mismatch_distribution") or {}
    perfect_or_near = (mm.get("0MM", 0) or 0) + (mm.get("1MM", 0) or 0)
    if perfect_or_near > 0:
        return "high"

    total = profile.get("total_off_targets")
    if isinstance(total, int):
        if total >= 5:
            return "high"
        if total >= 2:
            return "medium"
        return "low"

    return "unknown"


def _prefilter(cell_type: str, cas_variant: str, edit_type: str,
               kb: dict) -> tuple[list[dict], list[str]]:
    """Deterministic pre-filter: eliminate methods that violate hard constraints.

    Returns (eligible_methods, exclusion_notes). exclusion_notes is a list of
    human-readable strings like "aav_single excluded: cargo ~5.5 kb > AAV limit 4.7 kb".
    """
    methods = kb.get("methods", [])
    aav_limit = kb.get("aav_cargo_limit_kb", 4.7)
    cargo_kb = _estimate_cargo_kb(cas_variant, kb)
    ct_lower = cell_type.lower()

    eligible = []
    notes = []

    for m in methods:
        key = m["key"]

        # Rule 1: single AAV cargo limit
        if key == "aav_single" and cargo_kb is not None and cargo_kb > aav_limit:
            notes.append(
                f"{key} excluded: {cas_variant} cargo ~{cargo_kb} kb "
                f"> AAV packaging limit {aav_limit} kb"
            )
            continue

        # Rule 2: hydrodynamic injection is rodent-only
        if key == "hydrodynamic_injection" and (
            "human" in ct_lower or "clinical" in ct_lower or "patient" in ct_lower
        ):
            notes.append(f"{key} excluded: rodent-only method, not applicable to human/clinical context")
            continue

        # Rule 3: biolistics is plant-specific — exclude for mammalian
        if key == "biolistics":
            plant_keywords = ["plant", "arabidopsis", "rice", "tobacco", "maize",
                              "wheat", "callus", "protoplast", "chloroplast", "pollen"]
            if not any(pk in ct_lower for pk in plant_keywords):
                notes.append(f"{key} excluded: plant-specific method, cell type appears non-plant")
                continue

        # Rule 4: microinjection is only for zygotes/oocytes/embryos
        if key == "microinjection":
            zygote_keywords = ["zygote", "oocyte", "embryo", "egg"]
            if not any(zk in ct_lower for zk in zygote_keywords):
                notes.append(f"{key} excluded: only applicable to zygotes/oocytes/embryos")
                continue

        eligible.append(m)

    return eligible, notes


class DeliveryAdvisor:
    """
    Description:
        Recommends and ranks CRISPR delivery methods for a given cell type and
        Cas variant, using an internal Claude API call to reason over a curated
        knowledge base loaded from data/methods.json. Returns a structured JSON
        object with a top recommendation, ranked methods with suitability ratings,
        rationale, KB citations, and general advice.

        Also accepts a `construct` object (the upstream Construction File Builder
        output) and extracts cell_type/cas_variant/edit_type from it. When the
        construct carries a `kit_choice` or `off_target_risk_profile`, those are
        surfaced to the LLM so it can flag kit/delivery inconsistencies and bias
        toward transient delivery under high off-target burden.

    Input:
        cell_type (str, optional): The target cell type (e.g. 'HEK293',
                                   'primary T cells', 'neurons', 'iPSCs').
        cas_variant (str, optional): The CRISPR-Cas variant (e.g. 'SpCas9',
                                     'SaCas9', 'CBE4max', 'PE2').
        edit_type (str, optional): The type of genome edit. Defaults to
                                   'knockout'. Other: 'knock-in', 'base edit',
                                   'prime edit'.
        construct (dict, optional): Upstream Construction File Builder output.
                                    Must carry cell_type and cas_variant. Optional
                                    fields read from construct: edit_type,
                                    kit_choice (or vector_backbone), organism,
                                    off_target_risk_profile (string or
                                    {total_off_targets, mismatch_distribution} dict),
                                    status, warnings. Explicit kwargs override
                                    construct fields when both are given.

        At least one of {cell_type+cas_variant, construct} must be provided.

    Output:
        dict: A dictionary containing:
            - top_recommendation (str)
            - ranked_methods (list): 3-5 methods, each with method,
              suitability, rationale, key_considerations, citations
            - general_advice (str)
            - kit_choice_consistency (dict): {kit_choice, consistent, note},
              populated when a kit_choice was passed in via construct
            - excluded_by_prefilter (list): methods dropped by deterministic
              pre-filter (only present if any were excluded)
            - upstream_construct_warnings (dict): only present when the
              upstream construct's status != 'supported' or warnings is
              non-empty. Echoes upstream status and warnings so callers
              cannot silently miss an unsupported construct.

    Tests:
        - Case:
            Input: cell_type="HEK293", cas_variant="SpCas9", edit_type="knockout"
            Expected Output: dict with top_recommendation containing
                "lipofection" or "electroporation"; ranked_methods length 3-5;
                each method carries citations resolving to real KB keys.
            Description: Canonical easy-line knockout — the textbook lipofection case.
        - Case:
            Input: cell_type="primary T cells", cas_variant="SpCas9",
                   edit_type="knockout"
            Expected Output: top_recommendation contains "rnp" or "electroporation"
                (gold standard for primary immune cells).
            Description: Refractory primary cells — must NOT recommend lipofection.
        - Case:
            Input: cell_type="hepatocytes (in vivo, liver)", cas_variant="ABE8e",
                   edit_type="base edit"
            Expected Output: top_recommendation in {LNP, dual-AAV, eVLP};
                excluded_by_prefilter contains "aav_single excluded ... > 4.7 kb"
                (ABE8e ~5.5 kb exceeds the AAV cargo limit).
            Description: Cargo-size hard constraint — pre-filter must drop single AAV.
        - Case:
            Input: construct={"cell_type": "HEK293", "cas_variant": "SpCas9",
                              "edit_type": "knockout", "kit_choice": "lentiCRISPRv2",
                              "organism": "human", "status": "supported",
                              "off_target_risk_profile": {...}}
            Expected Output: kit_choice_consistency.consistent == False with a note
                explaining lentivirus is suboptimal for HEK293 SpCas9 KO; no
                upstream_construct_warnings (status is "supported").
            Description: Pipeline integration — upstream Construction File Builder
                output consumed verbatim, kit_choice cross-checked against advisor.
        - Case:
            Input: cell_type="" (or whitespace-only)
            Expected Exception: ValueError mentioning "cell_type"
            Description: Empty / whitespace input is rejected at the boundary.
        - Case:
            Input: cell_type="HEK293", cas_variant=""
            Expected Exception: ValueError mentioning "cas_variant"
            Description: Empty Cas variant is rejected at the boundary.
    """

    api_key: str
    system_prompt: str
    kb: dict
    valid_kb_keys: set

    def initiate(self) -> None:
        """One-time setup: load API key and knowledge base, build system prompt."""
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not self.api_key:
            env_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
            )
            if os.path.isfile(env_path):
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("ANTHROPIC_API_KEY"):
                            _, _, value = line.partition("=")
                            self.api_key = value.strip().strip('"').strip("'")
                            break

        kb_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "methods.json")
        )
        with open(kb_path, "r") as f:
            self.kb = json.load(f)

        self.valid_kb_keys = {m["key"] for m in self.kb.get("methods", [])}
        self.system_prompt = (
            SYSTEM_PROMPT_HEADER
            + "\n\n"
            + _render_kb(self.kb)
            + "\n"
            + SYSTEM_PROMPT_FOOTER
        )

    def run(
        self,
        cell_type: str | None = None,
        cas_variant: str | None = None,
        edit_type: str | None = None,
        construct: dict | None = None,
    ) -> dict:
        """Recommend CRISPR delivery strategies for the given parameters.

        Accepts explicit kwargs or a `construct` dict (upstream builder output).
        Explicit kwargs override construct fields.
        """
        # Merge construct + explicit kwargs (explicit wins)
        kit_choice = None
        off_target_profile = None
        organism = None
        upstream_status = None
        upstream_warnings = []
        if construct is not None:
            if not isinstance(construct, dict):
                raise ValueError("construct must be a dict")
            cell_type = cell_type if cell_type else construct.get("cell_type")
            cas_variant = cas_variant if cas_variant else construct.get("cas_variant")
            edit_type = edit_type if edit_type else construct.get("edit_type")
            kit_choice = construct.get("kit_choice") or construct.get("vector_backbone")
            off_target_profile = construct.get("off_target_risk_profile")
            organism = construct.get("organism")
            upstream_status = construct.get("status")
            upstream_warnings = construct.get("warnings") or []

        if not cell_type or not cell_type.strip():
            raise ValueError("cell_type must not be empty")
        if not cas_variant or not cas_variant.strip():
            raise ValueError("cas_variant must not be empty")
        if not edit_type or not edit_type.strip():
            edit_type = "knockout"

        # --- Deterministic pre-filter ---
        eligible, exclusion_notes = _prefilter(
            cell_type, cas_variant, edit_type, self.kb
        )

        # Build a per-call KB with only eligible methods
        filtered_kb = dict(self.kb, methods=eligible)
        system_prompt = (
            SYSTEM_PROMPT_HEADER
            + "\n\n"
            + _render_kb(filtered_kb)
            + "\n"
            + SYSTEM_PROMPT_FOOTER
        )

        # Tell the LLM what was excluded deterministically so it doesn't
        # re-introduce those methods
        exclusion_block = ""
        if exclusion_notes:
            exclusion_block = (
                "\n\nThe following methods were EXCLUDED by hard-constraint "
                "pre-filtering. Do NOT recommend these:\n"
                + "\n".join(f"- {n}" for n in exclusion_notes)
            )

        upstream_block = ""
        if organism:
            upstream_block += f"\n\nOrganism: {organism}."
        if kit_choice:
            upstream_block += (
                f"\n\nUpstream Construction File Builder chose kit_choice: "
                f"{kit_choice}. Evaluate whether your top_recommendation is "
                f"consistent with this kit and populate kit_choice_consistency."
            )
        if off_target_profile:
            burden_label = _classify_off_target_burden(off_target_profile)
            upstream_block += (
                f"\n\nOff-target risk profile from upstream analyzer: "
                f"{json.dumps(off_target_profile)}. Burden classified as "
                f"{burden_label.upper()}. If HIGH, you MUST prefer transient "
                f"delivery (RNP, LNP, eVLP) over sustained-expression methods."
            )

        user_message = (
            f"Cell type: {cell_type.strip()}\n"
            f"Cas variant: {cas_variant.strip()}\n"
            f"Edit type: {edit_type.strip()}"
            + upstream_block
            + exclusion_block
        )

        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 2048,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))

        text = response_data["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        required_keys = ["top_recommendation", "ranked_methods", "general_advice"]
        missing = [k for k in required_keys if k not in result]
        if missing:
            raise RuntimeError(
                f"LLM response missing required keys: {', '.join(missing)}"
            )

        for method in result["ranked_methods"]:
            cites = method.get("citations", [])
            method["citations"] = cites
            unknown = [c for c in cites if c not in self.valid_kb_keys]
            if unknown:
                method["_citation_warnings"] = (
                    f"unknown KB keys: {', '.join(unknown)}"
                )

        # Normalize kit_choice_consistency: always present, null-filled when absent
        kcc = result.get("kit_choice_consistency") or {}
        result["kit_choice_consistency"] = {
            "kit_choice": kcc.get("kit_choice") if kit_choice else None,
            "consistent": kcc.get("consistent") if kit_choice else None,
            "note": kcc.get("note") if kit_choice else None,
        }

        if exclusion_notes:
            result["excluded_by_prefilter"] = exclusion_notes

        # Surface upstream construct status / warnings so callers can't miss them.
        # An unsupported construct or non-empty warning list still gets a
        # recommendation, but the upstream signal is propagated to the output.
        if construct is not None and (
            (upstream_status and upstream_status != "supported")
            or upstream_warnings
        ):
            result["upstream_construct_warnings"] = {
                "status": upstream_status,
                "warnings": list(upstream_warnings),
                "note": (
                    "Upstream Construction File Builder flagged this construct. "
                    "Recommendation produced anyway — review upstream issues "
                    "before acting on it."
                ),
            }

        return result


_instance = DeliveryAdvisor()
_instance.initiate()
delivery_advisor = _instance.run
