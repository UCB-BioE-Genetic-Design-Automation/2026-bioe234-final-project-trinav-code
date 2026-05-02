# Delivery Advisor — Theory Docs

Companion to `README.md` §1–§7 and `modules/delivery_advisor/SKILL.md`. The README
covers what the tool does, how to run it, and the eval results. This file covers
the *why* — the biology behind the recommendations and the design choices behind
the three-stage hybrid pipeline.

---

## 1. The biology problem

CRISPR is two molecules (Cas protein + guide RNA), sometimes three (donor template
for HDR / knock-in). Getting them inside the right cells is a separate engineering
problem from designing the edit itself. The choice of delivery method is governed
by a small set of orthogonal physical and biological constraints:

- **Cargo size.** AAV has a hard ~4.7 kb single-vector limit. SpCas9 (~4.2 kb) just
  fits; CBE / ABE / PE editors (~5–6 kb) do not. Exceeding the limit forces dual-AAV
  (split-intein), LNP-mRNA, or eVLP delivery.
- **Cell division status.** Plasmid transfection and lipofection require active
  division to dilute episomal DNA into daughter cells; post-mitotic cells (neurons,
  cardiomyocytes) need viral integration or transient protein/mRNA delivery.
- **Primary vs immortalized.** HEK293, HeLa, K562 tolerate lipofection. Primary
  T cells, HSPCs, and iPSCs are refractory to lipofection but accept RNP
  electroporation (Lonza Nucleofector is the field standard).
- **Cell-wall barrier.** Plant cells have a wall that defeats lipid- and
  electroporation-based delivery. Biolistics, Agrobacterium, or protoplast PEG
  fusion are the available routes.
- **In-vivo tissue tropism.** AAV serotype dictates tissue: AAV8 → liver,
  AAV9 / AAV-PHP.eB → CNS, AAV9 → muscle/heart. LNPs are liver-tropic by default.
- **Integration risk.** Lentivirus integrates and is preferred for pooled
  screens and stable lines, but transient delivery (RNP, LNP, eVLP) is
  preferred for clinical / therapeutic editing to avoid insertional mutagenesis.
- **HDR requirement.** Knock-ins via HDR require S/G2 cell-cycle phase plus a
  donor template, narrowing options further (e.g., CRISPR-Gold, AAV donor + RNP).

The 17-method knowledge base in `data/methods.json` encodes each of these
constraints as structured fields (`cargo_limit_kb`, `compatible_cells`,
`incompatible_cells`, `in_vivo`, `integration_risk`, `clinical_stage`, etc.) so
reasoning is grounded, not free-floating.

---

## 2. Three-stage hybrid pipeline

A pure-LLM advisor would be unauditable: a single prompt-and-pray with no
reviewable artifacts. A pure-rules system would be brittle: every new editor or
cell type would require a code change. The advisor splits the work into three
stages so the hard biological constraints are non-negotiable while the soft
ranking benefits from LLM reasoning over the curated KB.

**Stage 1 — Deterministic pre-filter (`_prefilter`).**
Hard rules eliminate infeasible methods *before* the LLM sees them:

- AAV single-vector dropped when `cargo_kb > 4.7`.
- Hydrodynamic injection dropped for human / clinical contexts (rodent-only).
- Biolistics / Agrobacterium dropped for non-plant cells.
- Microinjection dropped outside zygote / oocyte / embryo contexts.

Excluded methods are passed to the LLM as a **"do NOT recommend"** block so the
model cannot re-introduce them.

**Stage 2 — KB-grounded LLM call.**
The system prompt is rendered at runtime from `data/methods.json`. Every entry
the LLM sees is curated; there is no free-form prose for the model to
hallucinate over. The KB lives as versioned JSON, so every edit shows up in
`git diff` and is reviewable.

**Stage 3 — Citation enforcement.**
The LLM must cite the exact KB `key` values (e.g. `rnp_electroporation`,
`dual_aav`) that justify each recommendation. After the call, the advisor
validates every citation against the KB's real key set and annotates
`_citation_warnings` if any are hallucinated. The eval suite asserts zero
hallucinations across all 22 canonical cases.

This design directly addresses the auditability question raised in the
mid-project check-in: every recommendation is traceable back to a specific
curated KB entry, and any deviation surfaces as a warning rather than passing
silently.

---

## 3. Pipeline integration

When the upstream Construction File Builder passes a `construct` dict, the
advisor reads `kit_choice`, `vector_backbone`, and `off_target_risk_profile`
in addition to the core triple (`cell_type`, `cas_variant`, `edit_type`). The
LLM is asked to populate a `kit_choice_consistency` block that flags whether
the upstream kit selection is consistent with the advisor's top recommendation.
Two pipeline cases in the eval suite cover both the agreement case
(primary T cells + Cas9 RNP kit) and the disagreement case (HEK293 +
lentiCRISPRv2, where transient lipofection is preferred over integration).

---

## 4. Limits and known scope

- The advisor does not currently parse structured `off_target_risk_profile`
  thresholds — it passes the dict to the LLM as JSON and asks for a soft
  preference for transient delivery if burden is high. A numeric threshold
  (e.g. `total_off_targets > 5` ⇒ require transient) is a candidate upgrade.
- The advisor does not check `status` or `warnings` fields on the upstream
  construct. If the upstream builder marks a construct as unsupported, the
  advisor will still produce a recommendation. Short-circuiting on
  `status != "supported"` is a candidate upgrade.
- The KB is curated to 17 methods; rare or novel delivery routes (e.g.
  exosomes, contact-dependent transfer) are out of scope.
