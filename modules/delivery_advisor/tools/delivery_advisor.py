"""CRISPR Delivery Strategy Advisor.

Uses an internal Claude API call to recommend delivery methods
for a given cell type, Cas variant, and edit type."""

import json
import os
import urllib.request


SYSTEM_PROMPT = """You are an expert molecular biologist specializing in CRISPR delivery methods.
Given a cell type, Cas variant, and edit type, recommend the best delivery strategies by
reasoning over the curated knowledge base below. Prefer methods from this reference set;
cite their tradeoffs explicitly in your rationale.

============================================================
DELIVERY METHOD KNOWLEDGE BASE (17 methods)
============================================================

Cargo-size reference: SpCas9 ~4.2 kb; SaCas9 ~3.2 kb; CjCas9 ~2.9 kb; Cas12a ~3.9 kb;
base editors (ABE/CBE) ~5.2–5.5 kb; prime editors (PE2/PE3) ~6.3 kb. AAV packaging
limit is ~4.7 kb — large editors exceed this and require dual-AAV, eVLPs, LNPs, or
non-viral delivery.

--- IN VITRO / EX VIVO METHODS ---

1. LIPOFECTION (cationic lipid, e.g. Lipofectamine)
   - Cargo: plasmid, mRNA, RNP
   - Best for: easy-to-transfect cell lines (HEK293, HeLa, U2OS, CHO)
   - Poor for: primary cells, suspension cells, neurons, hematopoietic cells
   - Pros: cheap, simple, high efficiency in dividing adherent lines
   - Cons: cytotoxic to sensitive cells, low efficiency in primaries

2. ELECTROPORATION — nucleic acid (plasmid/mRNA)
   - Cargo: plasmid DNA or in-vitro-transcribed mRNA
   - Best for: cell lines resistant to lipofection, iPSCs (with care)
   - Pros: works on most cell types, no viral components
   - Cons: cell death, requires optimization, integration risk with plasmid

3. RNP ELECTROPORATION (Cas9/gRNA ribonucleoprotein)
   - Cargo: pre-assembled Cas protein + sgRNA
   - Best for: primary T cells, HSPCs, NK cells, iPSCs, ex vivo therapeutics
   - Pros: transient (hours), low off-target, no integration, clinical-grade
   - Cons: expensive protein, size limits for large editors (PE less common as RNP)
   - Platforms: Lonza Nucleofector, MaxCyte (clinical scale), Neon

4. MICROINJECTION
   - Cargo: plasmid, mRNA, RNP
   - Best for: zygotes (mouse/rat/livestock), large oocytes, single-cell embryos
   - Pros: direct delivery, transgenic animal generation
   - Cons: extremely low throughput, technical skill required

5. BIOLISTICS (gene gun, DNA-coated gold/tungsten microparticles)
   - Cargo: plasmid DNA
   - Best for: plant cells (the dominant CRISPR delivery method in plants),
     also callus, pollen, chloroplast transformation
   - Pros: works through cell walls, no vectors needed
   - Cons: random integration, low efficiency, tissue damage

--- VIRAL VECTORS ---

6. AAV — single vector (AAV2, AAV6, AAV8, AAV9, etc.)
   - Cargo limit: ~4.7 kb — fits SaCas9/CjCas9 + sgRNA, NOT SpCas9 + sgRNA + promoter,
     NOT base editors, NOT prime editors
   - Best for: in vivo delivery (liver=AAV8, muscle=AAV9, CNS=AAV9/AAV-PHP.eB,
     retina=AAV2/AAV5), post-mitotic cells, long-term expression
   - Pros: low immunogenicity (vs adenovirus), broad tropism via serotypes,
     FDA-approved vectors (clinical use), persists as episome
   - Cons: size limit, pre-existing neutralizing antibodies in ~30-70% of humans,
     slow onset (2-4 weeks), sustained Cas9 expression → off-targets

7. DUAL-AAV (split-intein or trans-splicing)
   - Cargo: split across two AAV particles, reconstituted in cell by split inteins
   - Best for: SpCas9, base editors (ABE/CBE), prime editors in vivo
   - Pros: enables large editors via AAV, leverages established AAV infrastructure
   - Cons: co-infection required (reduces effective efficiency), complex design,
     higher viral dose needed

8. LENTIVIRUS (integrating, HIV-1-derived)
   - Cargo: up to ~8-10 kb — fits most editors including prime editors
   - Best for: stable cell line generation, CRISPR screens (pooled libraries),
     hard-to-transfect cells (T cells, HSPCs ex vivo)
   - Pros: integrates (stable expression), infects dividing AND non-dividing cells,
     large cargo, gold standard for CRISPR screens
   - Cons: semi-random integration → insertional mutagenesis risk,
     sustained Cas9 → off-targets, not ideal for therapeutic editing

9. NON-INTEGRATING LENTIVIRUS (NILV, integrase-deficient)
   - Cargo: same as lentivirus (~8-10 kb)
   - Best for: transient expression in non-dividing cells where AAV is size-limited
   - Pros: no integration, same broad tropism, accommodates large cargo
   - Cons: transient (diluted with division), lower titers than integrating LV

10. ADENOVIRUS (Ad5 and variants)
    - Cargo: up to ~8 kb (gutless/HD-Ad up to ~36 kb)
    - Best for: transient high-level expression, liver delivery, vaccines
    - Pros: very high expression, large cargo, infects non-dividing cells
    - Cons: HIGH immunogenicity (Jesse Gelsinger, 1999), pre-existing immunity common,
      rarely used therapeutically for CRISPR

--- NEXT-GENERATION / IN VIVO NON-VIRAL ---

11. LIPID NANOPARTICLES (LNPs, ionizable lipid, same chemistry as mRNA vaccines)
    - Cargo: mRNA (Cas9 mRNA + sgRNA), or Cas9 mRNA alone
    - Best for: in vivo liver delivery (dominant tropism via ApoE/LDLR), also
      lung (via charge modulation), and emerging CNS/bone marrow targeting
    - Pros: transient (hours), non-integrating, scalable GMP manufacturing,
      no viral immunity issue, repeat dosing possible
    - Cons: strong liver tropism limits other tissues without targeting ligands,
      mRNA cold chain
    - Clinical: Intellia NTLA-2001 (TTR), NTLA-2002 (HAE) — first systemic in vivo
      CRISPR therapies in humans

12. ENGINEERED VIRUS-LIKE PARTICLES (eVLPs)
    - Cargo: packaged Cas9/base editor/prime editor protein + gRNA (NOT DNA)
    - Best for: in vivo delivery of large editors (base, prime) without genome integration,
      retina, liver, CNS (with tropism engineering)
    - Pros: transient (protein payload, degraded in hours), no DNA → no integration,
      accommodates large editors that exceed AAV, low off-target vs AAV
    - Cons: newer technology, manufacturing still maturing, lower titers than AAV
    - Key refs: Banskota et al. Cell 2022 (eVLP base editing in vivo)

13. CELL-PENETRATING PEPTIDES (CPPs, e.g. TAT, penetratin, Endo-Porter)
    - Cargo: Cas9 RNP conjugated or complexed to CPP
    - Best for: ex vivo delivery to hard-to-transfect cells, topical/local delivery
    - Pros: simple, non-viral, transient
    - Cons: endosomal escape bottleneck, lower efficiency than electroporation,
      limited in vivo biodistribution

14. EXOSOMES / EXTRACELLULAR VESICLES
    - Cargo: Cas9 mRNA, RNP, or sgRNA loaded into native or engineered EVs
    - Best for: in vivo delivery with tissue tropism (engineerable), BBB crossing
      (with RVG or brain-homing peptides), low immunogenicity
    - Pros: endogenous origin → low immunity, tunable tropism, BBB-permeable variants
    - Cons: loading efficiency low, scalable manufacturing unsolved, heterogeneous

15. CRISPR-GOLD (gold nanoparticle + Cas9 RNP + donor DNA + polymer coating)
    - Cargo: Cas9 RNP + ssDNA donor in a single particle
    - Best for: in vivo HDR editing in muscle (DMD models), brain injection
    - Pros: enables HDR in vivo (rare), non-viral, transient
    - Cons: research-stage, not clinical, biodistribution limited to injection site

16. POLYMERIC NANOPARTICLES (PBAEs, PEI, chitosan, PLGA)
    - Cargo: plasmid, mRNA, or RNP
    - Best for: tunable in vivo delivery, lung (inhaled), tumor targeting
    - Pros: highly customizable chemistry, scalable synthesis, non-viral
    - Cons: toxicity varies with polymer, efficiency typically lower than LNPs,
      less clinically mature

17. HYDRODYNAMIC INJECTION (tail-vein rapid large-volume injection)
    - Cargo: naked plasmid DNA
    - Best for: mouse liver (very high hepatocyte transfection), proof-of-concept
      in vivo studies, NOT translatable to humans
    - Pros: cheap, simple, high liver efficiency in rodents
    - Cons: rodent-only (volume scales with body weight), transient, not clinical

============================================================
DECISION HEURISTICS
============================================================

- Ex vivo therapeutic editing (T cells, HSPCs, iPSCs) → RNP electroporation (gold standard)
- In vivo liver, small Cas → AAV8 or LNP (LNP preferred for transient, AAV for durable)
- In vivo liver, large editor (BE/PE) → LNP (mRNA) or dual-AAV or eVLP
- In vivo CNS, small Cas → AAV9/AAV-PHP.eB
- In vivo CNS, large editor → dual-AAV, eVLP, or exosomes with brain-targeting
- In vivo muscle → AAV9 (small Cas) or dual-AAV (large editors)
- Plant cells → biolistics or Agrobacterium (not listed above; mention if relevant)
- Zygote/transgenic animals → microinjection of RNP
- CRISPR screens → lentivirus (integrating, pooled library)
- Easy cell lines (HEK293, HeLa) → lipofection
- Hard cell lines / primaries → electroporation (nucleic acid or RNP)
- HDR in vivo → CRISPR-Gold or LNPs with ssODN
- Clinical/therapeutic priority → transient delivery (RNP, LNP, eVLP) over
  integrating/sustained (lentivirus, plasmid)

============================================================
OUTPUT FORMAT
============================================================

Respond ONLY with a valid JSON object in this exact format, no other text:
{
  "top_recommendation": "<single best method as a short string>",
  "ranked_methods": [
    {
      "method": "<method name>",
      "suitability": "<high|medium|low>",
      "rationale": "<1-2 sentence explanation referencing cargo size, tropism, or other specific tradeoffs>",
      "key_considerations": ["<consideration 1>", "<consideration 2>"]
    }
  ],
  "general_advice": "<1-2 sentences of general advice for this specific combination>"
}

Include 3-5 methods in ranked_methods, ordered from most to least suitable.
Be specific to the cell type and Cas variant provided — do not give generic answers.
Explicitly consider: cargo size vs AAV limit, cell division status, primary vs cell line,
in vivo vs ex vivo, immunogenicity, integration risk, and edit type requirements.
If the editor exceeds the AAV cargo limit, DO NOT recommend single AAV — use dual-AAV,
LNP, eVLP, or electroporation instead."""


class DeliveryAdvisor:
    """
    Description:
        Recommends and ranks CRISPR delivery methods for a given cell type and
        Cas variant, using an internal Gemini API call to reason over the options.
        Returns a structured JSON object with a top recommendation, ranked methods
        with suitability ratings and rationale, and general advice.

    Input:
        cell_type (str): The target cell type (e.g. 'HEK293', 'primary T cells',
                         'neurons', 'iPSCs').
        cas_variant (str): The CRISPR-Cas variant being used (e.g. 'SpCas9',
                           'SaCas9', 'CBE4max', 'PE2').
        edit_type (str): The type of genome edit. Defaults to 'knockout'.
                         Other values: 'knock-in', 'base edit', 'prime edit'.

    Output:
        dict: A dictionary containing:
            - top_recommendation (str): The single best delivery method.
            - ranked_methods (list): 3-5 methods ranked by suitability, each with
              method name, suitability rating, rationale, and key considerations.
            - general_advice (str): General guidance for this specific combination.

    Tests:
        - Case:
            Input: cell_type="HEK293", cas_variant="SpCas9", edit_type="knockout"
            Expected Output: A dict with top_recommendation, ranked_methods, general_advice
            Description: Standard cell line knockout — should return lipofection or electroporation.
        - Case:
            Input: cell_type="primary T cells", cas_variant="SpCas9", edit_type="knockout"
            Expected Output: A dict with electroporation/RNP as top recommendation
            Description: Primary immune cells require electroporation or RNP delivery.
        - Case:
            Input: cell_type="", cas_variant="SpCas9"
            Expected Exception: ValueError
            Description: Empty cell_type raises ValueError.
        - Case:
            Input: cell_type="HEK293", cas_variant=""
            Expected Exception: ValueError
            Description: Empty cas_variant raises ValueError.
    """

    api_key: str

    def initiate(self) -> None:
        """One-time setup: load the Anthropic API key from environment or .env file."""
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not self.api_key:
            # Fallback: manually parse .env at the repo root
            # Walk up from __file__ four levels: tools/ -> delivery_advisor/ -> modules/ -> repo root
            env_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", ".env"
            )
            env_path = os.path.normpath(env_path)
            if os.path.isfile(env_path):
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("ANTHROPIC_API_KEY"):
                            _, _, value = line.partition("=")
                            self.api_key = value.strip().strip('"').strip("'")
                            break

    def run(self, cell_type: str, cas_variant: str, edit_type: str = "knockout") -> dict:
        """Recommend CRISPR delivery strategies for the given parameters."""
        # --- Input validation ---
        if not cell_type or not cell_type.strip():
            raise ValueError("cell_type must not be empty")
        if not cas_variant or not cas_variant.strip():
            raise ValueError("cas_variant must not be empty")
        if not edit_type or not edit_type.strip():
            edit_type = "knockout"

        # --- Build user message ---
        user_message = (
            f"Cell type: {cell_type.strip()}\n"
            f"Cas variant: {cas_variant.strip()}\n"
            f"Edit type: {edit_type.strip()}"
        )

        # --- Call Claude API ---
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
        }).encode("utf-8")

        url = "https://api.anthropic.com/v1/messages"

        req = urllib.request.Request(
            url,
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

        # --- Parse response ---
        text = response_data["content"][0]["text"]

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            # Remove opening fence (e.g. ```json or ```)
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        # --- Validate required keys ---
        required_keys = ["top_recommendation", "ranked_methods", "general_advice"]
        missing = [k for k in required_keys if k not in result]
        if missing:
            raise RuntimeError(
                f"LLM response missing required keys: {', '.join(missing)}"
            )

        return result


# ---------------------------------------------------------------------------
# Module-level alias so pytest and direct imports work.
#
#   from modules.delivery_advisor.tools.delivery_advisor import delivery_advisor
#
# ---------------------------------------------------------------------------
_instance = DeliveryAdvisor()
_instance.initiate()
delivery_advisor = _instance.run
