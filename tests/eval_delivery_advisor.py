"""Correctness eval harness for crispr_delivery_advisor.

Runs 20 canonical (cell_type, cas_variant, edit_type) cases against the
advisor and scores whether the top_recommendation lands in the expected
set. Produces a reportable accuracy number.

Usage:
    python tests/eval_delivery_advisor.py          # run all, print report
    python tests/eval_delivery_advisor.py --verbose # show per-case detail
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.delivery_advisor.tools.delivery_advisor import DeliveryAdvisor


EVAL_CASES = [
    # --- Easy cell lines ---
    {
        "cell_type": "HEK293",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["lipofection", "lipofectamine", "lipid"],
        "tag": "easy-line-lipofection",
    },
    {
        "cell_type": "HeLa",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["lipofection", "lipofectamine", "lipid", "electroporation"],
        "tag": "easy-line-hela",
    },
    # --- Primary / ex vivo ---
    {
        "cell_type": "primary T cells",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["rnp", "electroporation"],
        "tag": "primary-t-cells",
    },
    {
        "cell_type": "primary human HSPCs (CD34+)",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["rnp", "electroporation"],
        "tag": "hspc-rnp",
    },
    {
        "cell_type": "primary human T cells for clinical therapeutic editing",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["rnp", "electroporation"],
        "tag": "clinical-t-cells",
    },
    {
        "cell_type": "human iPSCs",
        "cas_variant": "SpCas9",
        "edit_type": "knock-in",
        "expected_top_contains_any": ["rnp", "electroporation", "nucleofection"],
        "tag": "ipsc-knockin",
    },
    # --- Cargo size constraint (large editors must NOT be single AAV) ---
    {
        "cell_type": "hepatocytes (in vivo, liver)",
        "cas_variant": "ABE8e",
        "edit_type": "base edit",
        "expected_top_contains_any": ["lnp", "lipid nanoparticle", "dual-aav", "dual aav", "evlp"],
        "tag": "liver-large-editor",
    },
    {
        "cell_type": "hepatocytes (in vivo, liver)",
        "cas_variant": "PE2",
        "edit_type": "prime edit",
        "expected_top_contains_any": ["lnp", "lipid nanoparticle", "dual-aav", "dual aav", "evlp"],
        "tag": "liver-prime-editor",
    },
    {
        "cell_type": "in vivo mouse retina",
        "cas_variant": "CBE4max",
        "edit_type": "base edit",
        "expected_top_contains_any": ["evlp", "dual-aav", "dual aav", "aav"],
        "tag": "retina-large-editor",
    },
    # --- In vivo liver, small Cas ---
    {
        "cell_type": "in vivo mouse liver",
        "cas_variant": "SaCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["aav", "lnp", "lipid nanoparticle"],
        "tag": "liver-small-cas",
    },
    # --- In vivo CNS ---
    {
        "cell_type": "in vivo mouse brain (striatum)",
        "cas_variant": "SaCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["aav"],
        "tag": "brain-small-cas",
    },
    {
        "cell_type": "in vivo mouse brain (cortex)",
        "cas_variant": "ABE8e",
        "edit_type": "base edit",
        "expected_top_contains_any": ["dual-aav", "dual aav", "evlp", "exosome"],
        "tag": "brain-large-editor",
    },
    # --- Neurons (post-mitotic) ---
    {
        "cell_type": "primary cortical neurons (in culture, post-mitotic)",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["aav", "lentivir", "viral", "rnp", "electroporation"],
        "tag": "neurons-postmitotic",
    },
    # --- Plant cells ---
    {
        "cell_type": "Arabidopsis protoplasts and callus",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["biolistic", "gene gun", "particle bombardment", "agrobacterium"],
        "tag": "plant-cells",
    },
    {
        "cell_type": "rice callus",
        "cas_variant": "Cas12a",
        "edit_type": "knockout",
        "expected_top_contains_any": ["biolistic", "gene gun", "agrobacterium", "particle"],
        "tag": "rice-callus",
    },
    # --- Zygotes ---
    {
        "cell_type": "mouse zygotes",
        "cas_variant": "SpCas9",
        "edit_type": "knock-in",
        "expected_top_contains_any": ["microinjection"],
        "tag": "zygote-knockin",
    },
    # --- iPSC-derived cardiomyocytes (post-mitotic, hard) ---
    {
        "cell_type": "iPSC-derived cardiomyocytes",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["aav", "lentivir", "rnp", "electroporation", "evlp"],
        "tag": "ipsc-cm",
    },
    # --- CRISPR screen ---
    {
        "cell_type": "K562 cell line (pooled CRISPR screen)",
        "cas_variant": "SpCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["lentivir"],
        "tag": "crispr-screen",
    },
    # --- In vivo muscle ---
    {
        "cell_type": "in vivo mouse skeletal muscle",
        "cas_variant": "SaCas9",
        "edit_type": "knockout",
        "expected_top_contains_any": ["aav"],
        "tag": "muscle-small-cas",
    },
    # --- In vivo HDR ---
    {
        "cell_type": "in vivo mouse muscle (DMD model, HDR required)",
        "cas_variant": "SpCas9",
        "edit_type": "knock-in",
        "expected_top_contains_any": ["gold", "crispr-gold", "lnp", "aav", "dual"],
        "tag": "in-vivo-hdr",
    },
    # --- Pipeline integration: upstream construct with mismatched kit ---
    # Upstream builder picked lentiCRISPRv2 (integrating), but HEK293 SpCas9 KO is a
    # textbook transient-delivery case. Advisor should top-rank lipofection/RNP and
    # populate kit_choice_consistency with consistent=False.
    {
        "construct": {
            "construct_name": "TP53_SpCas9_lentiCRISPRv2_knockout",
            "cell_type": "HEK293",
            "cas_variant": "SpCas9",
            "edit_type": "knockout",
            "kit_choice": "lentiCRISPRv2",
            "off_target_risk_profile": {
                "total_off_targets": 2,
                "mismatch_distribution": {"0MM": 0, "1MM": 0, "2MM": 1, "3MM": 1},
            },
        },
        "expected_top_contains_any": ["lipofection", "rnp", "electroporation"],
        "expected_kit_consistent": False,
        "tag": "pipeline-kit-mismatch",
    },
    # --- Pipeline integration: upstream construct with sensible kit ---
    # Primary T cells + SpCas9 KO + RNP kit — advisor and builder should agree.
    {
        "construct": {
            "construct_name": "TRAC_SpCas9_RNP_knockout",
            "cell_type": "primary T cells",
            "cas_variant": "SpCas9",
            "edit_type": "knockout",
            "kit_choice": "Cas9 RNP (Lonza Nucleofector)",
        },
        "expected_top_contains_any": ["rnp", "electroporation"],
        "expected_kit_consistent": True,
        "tag": "pipeline-kit-match",
    },
]


def run_eval(verbose=False):
    advisor = DeliveryAdvisor()
    advisor.initiate()

    results = []
    for i, case in enumerate(EVAL_CASES):
        tag = case["tag"]
        expected = case["expected_top_contains_any"]
        expected_kit_consistent = case.get("expected_kit_consistent")  # None / True / False

        if verbose:
            if "construct" in case:
                summary = f"construct[cell_type={case['construct'].get('cell_type')}, kit={case['construct'].get('kit_choice')}]"
            else:
                summary = f"{case['cell_type']} / {case['cas_variant']} / {case['edit_type']}"
            print(f"[{i+1}/{len(EVAL_CASES)}] {tag}: {summary} ... ", end="", flush=True)

        t0 = time.time()
        try:
            if "construct" in case:
                result = advisor.run(construct=case["construct"])
            else:
                result = advisor.run(
                    cell_type=case["cell_type"],
                    cas_variant=case["cas_variant"],
                    edit_type=case["edit_type"],
                )
            top = result["top_recommendation"].lower()
            passed = any(kw in top for kw in expected)
            elapsed = time.time() - t0

            citations_valid = True
            for m in result.get("ranked_methods", []):
                if "_citation_warnings" in m:
                    citations_valid = False
                if not m.get("citations"):
                    citations_valid = False

            # Kit-consistency check (only for pipeline-integration cases)
            kit_consistent_pass = None
            kcc = result.get("kit_choice_consistency") or {}
            if expected_kit_consistent is not None:
                kit_consistent_pass = (kcc.get("consistent") == expected_kit_consistent)
                if not kit_consistent_pass:
                    passed = False  # kit disagreement counts as a case failure

            results.append({
                "tag": tag,
                "passed": passed,
                "citations_valid": citations_valid,
                "kit_consistent_pass": kit_consistent_pass,
                "top_recommendation": result["top_recommendation"],
                "expected_any": expected,
                "expected_kit_consistent": expected_kit_consistent,
                "actual_kit_consistent": kcc.get("consistent"),
                "elapsed_s": round(elapsed, 1),
                "error": None,
            })

            if verbose:
                status = "PASS" if passed else "FAIL"
                cite_status = "ok" if citations_valid else "MISSING"
                extra = ""
                if expected_kit_consistent is not None:
                    extra = f" (kit: {'ok' if kit_consistent_pass else 'MISMATCH'})"
                print(f"{status} (citations: {cite_status}){extra} [{elapsed:.1f}s] "
                      f"got '{result['top_recommendation']}'")

        except Exception as e:
            elapsed = time.time() - t0
            results.append({
                "tag": tag,
                "passed": False,
                "citations_valid": False,
                "top_recommendation": None,
                "expected_any": expected,
                "elapsed_s": round(elapsed, 1),
                "error": str(e),
            })
            if verbose:
                print(f"ERROR [{elapsed:.1f}s] {e}")

    # --- Report ---
    total = len(results)
    correct = sum(1 for r in results if r["passed"])
    cite_ok = sum(1 for r in results if r["citations_valid"])
    errors = sum(1 for r in results if r["error"])
    total_time = sum(r["elapsed_s"] for r in results)

    print()
    print("=" * 60)
    print("DELIVERY ADVISOR EVAL REPORT")
    print("=" * 60)
    print(f"Top-recommendation accuracy: {correct}/{total} ({100*correct/total:.0f}%)")
    print(f"Citations valid:             {cite_ok}/{total} ({100*cite_ok/total:.0f}%)")
    print(f"Errors:                      {errors}/{total}")
    print(f"Total time:                  {total_time:.0f}s")
    print()

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("FAILURES:")
        for r in failures:
            if r["error"]:
                print(f"  {r['tag']}: ERROR — {r['error']}")
            else:
                print(f"  {r['tag']}: got '{r['top_recommendation']}', "
                      f"expected any of {r['expected_any']}")
        print()

    cite_failures = [r for r in results if not r["citations_valid"] and not r["error"]]
    if cite_failures:
        print("CITATION ISSUES:")
        for r in cite_failures:
            print(f"  {r['tag']}: '{r['top_recommendation']}'")
        print()

    return correct, total, results


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    correct, total, _ = run_eval(verbose=verbose)
    sys.exit(0 if correct == total else 1)
