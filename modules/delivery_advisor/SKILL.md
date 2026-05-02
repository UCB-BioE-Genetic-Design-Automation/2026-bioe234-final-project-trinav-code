# delivery_advisor — Skill Guidance

## What this module does

The `delivery_advisor` module helps researchers choose the optimal CRISPR delivery strategy for their specific experimental setup. CRISPR genome editing requires physically delivering editing components (Cas protein, guide RNA, and optionally a donor template) into target cells. The choice of delivery method depends critically on the cell type, the size of the editing cargo, in vivo vs ex vivo context, and the type of edit being performed. This module uses an LLM-in-the-loop approach with an embedded knowledge base of 17 delivery methods spanning classical, viral, and next-generation non-viral approaches, returning a ranked set of recommendations with rationale grounded in curated method profiles.

---

## Tools and when to use them

### `crispr_delivery_advisor`

Recommends and ranks CRISPR delivery methods for a given cell type, Cas variant, and edit type.

**Use when the user asks:**
- "What delivery method should I use for CRISPR in X cells?"
- "How should I deliver Cas9 to T cells?"
- "Best transfection method for neurons"
- "Should I use electroporation or lipofection for my experiment?"
- "How do I deliver a base editor to iPSCs?"
- Any question about CRISPR delivery, transfection, or getting editing reagents into cells

**Parameter notes:**
- `cell_type`: The target cell — be specific (e.g. "primary T cells" not just "T cells", "HEK293" not just "human cells")
- `cas_variant`: The CRISPR editor being used. Common values: SpCas9, SaCas9, Cas12a/Cpf1, CBE4max, ABE8e, PE2, PE3
- `edit_type`: What kind of edit — "knockout" (default), "knock-in" (requires HDR template), "base edit", "prime edit"
- `construct` (object, optional): Upstream Construction File Builder output. If provided, the advisor extracts `cell_type`, `cas_variant`, and `edit_type` from it — you do NOT need to pass those separately. The advisor also reads `kit_choice` (or `vector_backbone`), `organism`, `off_target_risk_profile`, `status`, and `warnings` from the construct. The off-target profile may be a structured dict (`{total_off_targets, mismatch_distribution}`) or a free-form string; the advisor classifies it as low/medium/high before passing it to the LLM. Pass the construct whenever the user is chaining this tool after the Construction File Builder.

**When to use `construct` vs explicit kwargs:**
- User asks a standalone delivery question → use explicit `cell_type` + `cas_variant` + `edit_type`.
- User pastes or references a construct JSON from the Construction File Builder → pass the whole thing as `construct`. Don't re-extract fields manually.
- If both are provided, explicit kwargs override construct fields (useful for "what if we used neurons instead?" follow-ups).

**Output interpretation:**
- `top_recommendation`: The single best method — start here
- `ranked_methods`: 3-5 options ranked from best to worst, each with a suitability rating (high/medium/low), a rationale explaining why, key considerations to watch for, and `citations` (KB method keys that justified the recommendation — traceable back to the knowledge base)
- `general_advice`: Practical tips specific to this cell type + editor combination
- `kit_choice_consistency`: Sanity-check on the upstream kit. When a `kit_choice` was provided, this block is `{kit_choice, consistent: bool, note: str}`. If `consistent: false`, explain the disagreement to the user — the advisor thinks the builder's kit is suboptimal for this edit. If no kit_choice was provided, all three fields are `null`.
- `excluded_by_prefilter` (optional): methods that were deterministically ruled out (e.g. single AAV for editors exceeding the ~4.7 kb cargo limit). Mention these when relevant — they explain why an "obvious" method is missing from the ranking.
- `upstream_construct_warnings` (optional): only present when the upstream construct's `status != "supported"` or `warnings` is non-empty. Surface this to the user before discussing the recommendation — the upstream pipeline flagged a problem that should be resolved before acting on the delivery choice.

---

## Delivery method quick reference (17 methods)

### In vitro / ex vivo

| Method | Cargo | Best for | Limitations |
|--------|-------|----------|-------------|
| Lipofection | Plasmid, mRNA, RNP | Easy cell lines (HEK293, HeLa, U2OS, CHO) | Poor in primary, suspension, neurons |
| Electroporation (nucleic acid) | Plasmid, mRNA | Cell lines resistant to lipofection, iPSCs | Cell death; integration risk with plasmid |
| RNP electroporation | Cas protein + sgRNA | Primary T cells, HSPCs, iPSCs, clinical ex vivo | Expensive protein; size limits for large editors |
| Microinjection | Plasmid, mRNA, RNP | Zygotes, oocytes, transgenic animals | Extremely low throughput |
| Biolistics (gene gun) | Plasmid DNA | Plant cells, callus, chloroplasts | Random integration; tissue damage |

### Viral vectors

| Method | Cargo | Best for | Limitations |
|--------|-------|----------|-------------|
| AAV (single) | ≤ ~4.7 kb | In vivo (liver, CNS, muscle, retina); post-mitotic | Cargo limit excludes SpCas9, BE, PE; pre-existing antibodies |
| Dual-AAV (split-intein) | Split across 2 AAVs | Large editors (SpCas9, BE, PE) in vivo | Co-infection inefficiency; higher viral dose |
| Lentivirus (integrating) | Up to ~8–10 kb | Stable lines, CRISPR screens, ex vivo T cells/HSPCs | Insertional mutagenesis; sustained Cas9 → off-targets |
| Non-integrating lentivirus (NILV) | Up to ~8–10 kb | Transient expression in non-dividing cells | Lower titers; transient |
| Adenovirus (Ad5) | Up to ~8 kb (HD-Ad ~36 kb) | Transient high expression, liver | Highly immunogenic; rarely used clinically |

### Next-generation / in vivo non-viral

| Method | Cargo | Best for | Limitations |
|--------|-------|----------|-------------|
| LNP (lipid nanoparticle) | mRNA (Cas9 mRNA + sgRNA) | In vivo liver (Intellia NTLA-2001/2002), repeat dosing | Strong liver tropism; limited other tissues |
| eVLP (engineered VLP) | Cas/BE/PE protein + gRNA | In vivo large editors without integration | Newer; manufacturing maturing |
| CPP (cell-penetrating peptide) | Cas9 RNP | Hard ex vivo cells, topical | Endosomal escape bottleneck |
| Exosome / EV | mRNA, RNP, sgRNA | BBB-crossing CNS delivery, low immunogenicity | Loading inefficient; manufacturing unsolved |
| CRISPR-Gold | Cas9 RNP + ssDNA donor | In vivo HDR (muscle, brain) | Research-stage; injection-site limited |
| Polymeric nanoparticle (PBAE, PEI) | Plasmid, mRNA, RNP | Tunable in vivo, lung, tumor | Toxicity varies; less mature than LNPs |
| Hydrodynamic injection | Naked plasmid | Mouse liver proof-of-concept | Rodent-only; not translatable |

---

## Key biological considerations

- **Primary vs cell line**: Immortalized cell lines (HEK293, HeLa) are easy to transfect with lipids. Primary cells often require electroporation or viral delivery.
- **Post-mitotic cells**: Non-dividing cells (neurons, cardiomyocytes) cannot be transfected with plasmids efficiently. AAV or lentiviral vectors are preferred. HDR is extremely inefficient in non-dividing cells.
- **Cargo size constraints**: AAV has a strict ~4.7 kb packaging limit. SpCas9 (~4.2 kb coding sequence) barely fits alone; adding a guide expression cassette pushes it over. SaCas9 (~3.2 kb) fits more comfortably. Base editors and prime editors are larger and typically require dual-AAV or non-viral strategies.
- **Immunogenicity**: Viral vectors can trigger immune responses, especially in vivo. RNP delivery is least immunogenic. Repeated AAV dosing is limited by anti-AAV antibodies.
- **HDR requirement for knock-in**: Knock-in edits require homology-directed repair, which needs a donor template. This adds to cargo size and works best in dividing cells during S/G2 phase. Consider delivery of both the nuclease and the donor template.
- **Off-target integration risk**: Plasmid and lentiviral delivery carry risk of random genomic integration. RNP and mRNA delivery are transient and avoid this risk.

---

## Quick decision heuristics

- Ex vivo therapeutic editing (T cells, HSPCs, iPSCs) → RNP electroporation
- In vivo liver, small Cas → AAV8 or LNP (LNP for transient, AAV for durable)
- In vivo liver, large editor (BE/PE) → LNP (mRNA), dual-AAV, or eVLP
- In vivo CNS, small Cas → AAV9 or AAV-PHP.eB
- In vivo CNS, large editor → dual-AAV, eVLP, or brain-targeted exosomes
- In vivo muscle → AAV9 (small) or dual-AAV (large)
- Plant cells → biolistics or Agrobacterium
- Zygotes / transgenic animals → microinjection of RNP
- CRISPR screens → integrating lentivirus (pooled library)
- Easy cell lines → lipofection; hard lines / primaries → electroporation
- HDR in vivo → CRISPR-Gold or LNP with ssODN
- Clinical / therapeutic → transient (RNP, LNP, eVLP) over integrating
