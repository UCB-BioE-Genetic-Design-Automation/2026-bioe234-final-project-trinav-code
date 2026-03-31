# delivery_advisor — Skill Guidance for Gemini

## What this module does

The `delivery_advisor` module helps researchers choose the optimal CRISPR delivery strategy for their specific experimental setup. CRISPR genome editing requires physically delivering editing components (Cas protein, guide RNA, and optionally a donor template) into target cells. The choice of delivery method — lipofection, electroporation, viral vectors, ribonucleoprotein (RNP) complexes, or lipid nanoparticles — depends critically on the cell type, the size of the editing cargo, and the type of edit being performed. This module uses an LLM-in-the-loop approach to reason over these factors and return a ranked set of recommendations with rationale.

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

**Output interpretation:**
- `top_recommendation`: The single best method — start here
- `ranked_methods`: 3-5 options ranked from best to worst, each with a suitability rating (high/medium/low), a rationale explaining why, and key considerations to watch for
- `general_advice`: Practical tips specific to this cell type + editor combination

---

## Delivery method quick reference

| Method | Cargo type | Best for | Limitations |
|--------|-----------|----------|-------------|
| Lipofection | Plasmid DNA, RNP, mRNA | Easy-to-transfect cell lines (HEK293, HeLa) | Poor efficiency in primary cells and suspension cells |
| Electroporation (plasmid) | Plasmid DNA | Broad range of cell types including primary cells | Can cause significant cell death; DNA toxicity in some primary cells |
| RNP electroporation | Protein + sgRNA | Primary cells, therapeutic applications, high-fidelity editing | Requires purified Cas protein; transient expression only |
| AAV | ssDNA (< ~4.7 kb) | In vivo delivery, post-mitotic cells (neurons, muscle), liver | Strict cargo size limit (~4.7 kb); SpCas9 too large for single AAV |
| Lentiviral | RNA → integrating DNA | Stable expression, difficult-to-transfect cells | Genomic integration risk; constitutive expression increases off-targets |
| LNP (lipid nanoparticle) | mRNA, RNP | In vivo liver targeting, therapeutic applications | Primarily liver-tropic; limited tissue targeting |
| Microinjection | Any | Zygotes, oocytes, single-cell applications | Low throughput; requires specialized equipment |

---

## Key biological considerations

- **Primary vs cell line**: Immortalized cell lines (HEK293, HeLa) are easy to transfect with lipids. Primary cells often require electroporation or viral delivery.
- **Post-mitotic cells**: Non-dividing cells (neurons, cardiomyocytes) cannot be transfected with plasmids efficiently. AAV or lentiviral vectors are preferred. HDR is extremely inefficient in non-dividing cells.
- **Cargo size constraints**: AAV has a strict ~4.7 kb packaging limit. SpCas9 (~4.2 kb coding sequence) barely fits alone; adding a guide expression cassette pushes it over. SaCas9 (~3.2 kb) fits more comfortably. Base editors and prime editors are larger and typically require dual-AAV or non-viral strategies.
- **Immunogenicity**: Viral vectors can trigger immune responses, especially in vivo. RNP delivery is least immunogenic. Repeated AAV dosing is limited by anti-AAV antibodies.
- **HDR requirement for knock-in**: Knock-in edits require homology-directed repair, which needs a donor template. This adds to cargo size and works best in dividing cells during S/G2 phase. Consider delivery of both the nuclease and the donor template.
- **Off-target integration risk**: Plasmid and lentiviral delivery carry risk of random genomic integration. RNP and mRNA delivery are transient and avoid this risk.
