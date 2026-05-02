"""
Unit tests for the delivery_advisor module.

Tests cover input validation (no API call) and live Claude API tests
that verify the structure and biological plausibility of responses, plus
integration tests for the `construct` object path (upstream Construction
File Builder output).
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.delivery_advisor.tools.delivery_advisor import DeliveryAdvisor


@pytest.fixture(scope="module")
def advisor():
    """Create and initiate one DeliveryAdvisor instance shared across all tests."""
    instance = DeliveryAdvisor()
    instance.initiate()
    return instance


# --- Input validation tests (no API call) ---

def test_empty_cell_type_raises_value_error(advisor):
    with pytest.raises(ValueError, match="cell_type"):
        advisor.run(cell_type="", cas_variant="SpCas9")


def test_empty_cas_variant_raises_value_error(advisor):
    with pytest.raises(ValueError, match="cas_variant"):
        advisor.run(cell_type="HEK293", cas_variant="")


def test_whitespace_cell_type_raises_value_error(advisor):
    with pytest.raises(ValueError, match="cell_type"):
        advisor.run(cell_type="   ", cas_variant="SpCas9")


def test_construct_must_be_dict(advisor):
    with pytest.raises(ValueError, match="construct"):
        advisor.run(construct="not a dict")


def test_construct_missing_cell_type_raises(advisor):
    with pytest.raises(ValueError, match="cell_type"):
        advisor.run(construct={"cas_variant": "SpCas9"})


def test_construct_missing_cas_variant_raises(advisor):
    with pytest.raises(ValueError, match="cas_variant"):
        advisor.run(construct={"cell_type": "HEK293"})


# --- API tests ---

@pytest.fixture(scope="module")
def hek293_result(advisor):
    """Cache the HEK293 API call result for reuse across structure tests."""
    return advisor.run(cell_type="HEK293", cas_variant="SpCas9", edit_type="knockout")


def test_hek293_returns_valid_structure(hek293_result):
    assert "top_recommendation" in hek293_result
    assert "ranked_methods" in hek293_result
    assert "general_advice" in hek293_result
    assert isinstance(hek293_result["ranked_methods"], list)
    assert len(hek293_result["ranked_methods"]) >= 1


def test_ranked_methods_have_required_fields(hek293_result):
    for method in hek293_result["ranked_methods"]:
        assert "method" in method
        assert "suitability" in method
        assert "rationale" in method
        assert "key_considerations" in method
        assert "citations" in method


VALID_KB_KEYS = {
    "lipofection", "electroporation_nucleic_acid", "rnp_electroporation",
    "microinjection", "biolistics", "aav_single", "dual_aav", "lentivirus",
    "nilv", "adenovirus", "lnp", "evlp", "cpp", "exosome", "crispr_gold",
    "polymeric_np", "hydrodynamic_injection",
}


def test_citations_are_valid_kb_keys(hek293_result):
    for method in hek293_result["ranked_methods"]:
        for cite in method["citations"]:
            assert cite in VALID_KB_KEYS, f"Unknown KB key in citations: {cite}"
        assert len(method["citations"]) >= 1, (
            f"Method '{method['method']}' has no citations — "
            "every recommendation must trace to at least one KB key"
        )


def test_no_citation_warnings(hek293_result):
    for method in hek293_result["ranked_methods"]:
        assert "_citation_warnings" not in method, (
            f"Method '{method['method']}' has hallucinated KB keys: "
            f"{method.get('_citation_warnings')}"
        )


def test_suitability_values_are_valid(hek293_result):
    valid_values = {"high", "medium", "low"}
    for method in hek293_result["ranked_methods"]:
        assert method["suitability"].lower() in valid_values


def test_top_recommendation_is_nonempty_string(hek293_result):
    assert isinstance(hek293_result["top_recommendation"], str)
    assert len(hek293_result["top_recommendation"]) > 0


def test_general_advice_is_nonempty_string(hek293_result):
    assert isinstance(hek293_result["general_advice"], str)
    assert len(hek293_result["general_advice"]) > 0


def test_primary_t_cells_recommends_electroporation_or_rnp(advisor):
    result = advisor.run(cell_type="primary T cells", cas_variant="SpCas9", edit_type="knockout")
    top = result["top_recommendation"].lower()
    assert "electroporation" in top or "rnp" in top


def test_neuron_recommends_viral_delivery(advisor):
    result = advisor.run(cell_type="neurons", cas_variant="CBE4max", edit_type="base edit")
    top = result["top_recommendation"].lower()
    all_methods = " ".join(m["method"].lower() for m in result["ranked_methods"])
    combined = top + " " + all_methods
    assert "aav" in combined or "lentiviral" in combined or "viral" in combined


def test_default_edit_type(advisor):
    # Calling run() with only 2 args should not raise
    result = advisor.run(cell_type="HEK293", cas_variant="SpCas9")
    assert "top_recommendation" in result


# --- Edge-case tests (knowledge-base grounded) ---

def _combined_text(result):
    """Flatten a result into one lowercase string for keyword searches."""
    parts = [result["top_recommendation"], result["general_advice"]]
    for m in result["ranked_methods"]:
        parts.append(m["method"])
        parts.append(m["rationale"])
        parts.extend(m.get("key_considerations", []))
    return " ".join(parts).lower()


def test_large_base_editor_avoids_single_aav(advisor):
    """ABE8e (~5.5 kb) exceeds the ~4.7 kb AAV cargo limit. The top recommendation
    must not be single AAV — acceptable answers are dual-AAV, LNP, eVLP, or
    electroporation/RNP."""
    result = advisor.run(
        cell_type="hepatocytes", cas_variant="ABE8e", edit_type="base edit"
    )
    top = result["top_recommendation"].lower()
    # Single AAV should not be the top pick; dual-AAV / LNP / eVLP / RNP are acceptable
    is_single_aav = "aav" in top and "dual" not in top and "dual-aav" not in top
    assert not is_single_aav, f"Top rec is single AAV for large BE: {top}"
    # The combined response should mention at least one large-editor-compatible method
    combined = _combined_text(result)
    assert any(k in combined for k in ["dual-aav", "dual aav", "lnp", "evlp", "lipid nanoparticle"]), \
        f"No large-editor-compatible method mentioned: {combined[:400]}"


def test_plant_cells_recommend_biolistics(advisor):
    """Plant cells with walls — biolistics (gene gun) should appear prominently."""
    result = advisor.run(
        cell_type="Arabidopsis protoplasts and callus",
        cas_variant="SpCas9",
        edit_type="knockout",
    )
    combined = _combined_text(result)
    assert any(k in combined for k in ["biolistic", "gene gun", "particle bombardment", "agrobacterium"]), \
        f"No plant-appropriate method mentioned: {combined[:400]}"


def test_in_vivo_brain_recommends_cns_tropic_aav(advisor):
    """In vivo brain delivery of SaCas9 should surface AAV9 or AAV-PHP.eB (CNS tropism)."""
    result = advisor.run(
        cell_type="in vivo mouse brain (striatum)",
        cas_variant="SaCas9",
        edit_type="knockout",
    )
    combined = _combined_text(result)
    assert "aav" in combined, f"AAV not mentioned for in vivo brain: {combined[:400]}"
    # At least one CNS-tropic serotype should be mentioned
    assert any(k in combined for k in ["aav9", "php.eb", "php-eb", "phpeb", "cns"]), \
        f"No CNS tropism discussed: {combined[:400]}"


def test_ipsc_cardiomyocytes_handled(advisor):
    """iPSC-derived cardiomyocytes are post-mitotic and hard to transfect. The advisor
    should return a valid structured response and mention an appropriate method
    (AAV, lentivirus, RNP electroporation of iPSCs pre-differentiation, or eVLP)."""
    result = advisor.run(
        cell_type="iPSC-derived cardiomyocytes",
        cas_variant="SpCas9",
        edit_type="knock-in",
    )
    assert "top_recommendation" in result
    assert len(result["ranked_methods"]) >= 3
    combined = _combined_text(result)
    assert any(k in combined for k in ["aav", "lentivir", "electroporation", "rnp", "evlp"]), \
        f"No appropriate cardiomyocyte method mentioned: {combined[:400]}"


def test_clinical_context_favors_transient_delivery(advisor):
    """For therapeutic ex vivo T cell editing, transient delivery (RNP electroporation)
    should be the top pick — integrating lentivirus is not preferred for clinical
    therapeutic editing (though it is standard for CAR-T transgene delivery)."""
    result = advisor.run(
        cell_type="primary human T cells for clinical therapeutic editing",
        cas_variant="SpCas9",
        edit_type="knockout",
    )
    top = result["top_recommendation"].lower()
    assert "rnp" in top or "electroporation" in top, \
        f"Clinical T cell editing top rec is not RNP/electroporation: {top}"


# --- Pipeline integration tests (construct object from upstream builder) ---

YUSHAN_CONSTRUCT = {
    "construct_name": "TP53_SpCas9_lentiCRISPRv2_knockout",
    "target_gene": "TP53",
    "organism": "human",
    "cell_type": "HEK293",
    "cas_variant": "SpCas9",
    "guide_sequence": "AAAAAAAGGGGG",
    "edit_type": "knockout",
    "kit_choice": "lentiCRISPRv2",
    "vector_backbone": "lentiCRISPRv2",
    "cas_module": "SpCas9 expression cassette",
    "guide_module": {
        "promoter": "U6",
        "guide_sequence": "AAAAAAAGGGGG",
        "scaffold": "sgRNA scaffold",
    },
    "selection_marker": "Puromycin",
    "assembly_notes": [
        "Clone guide into BsmBI site",
        "Verify insertion via Sanger sequencing",
        "Lentiviral system for hard-to-transfect cells",
        "Requires virus production step",
    ],
    "status": "supported",
    "warnings": [],
    "off_target_risk_profile": {
        "total_off_targets": 2,
        "mismatch_distribution": {"0MM": 0, "1MM": 0, "2MM": 1, "3MM": 1},
    },
}


@pytest.fixture(scope="module")
def construct_result(advisor):
    """Cache a construct-path API call for reuse across integration tests."""
    return advisor.run(construct=YUSHAN_CONSTRUCT)


def test_construct_path_returns_valid_structure(construct_result):
    assert "top_recommendation" in construct_result
    assert "ranked_methods" in construct_result
    assert "general_advice" in construct_result
    assert "kit_choice_consistency" in construct_result
    assert len(construct_result["ranked_methods"]) >= 1


def test_construct_path_kit_choice_consistency_populated(construct_result):
    """When the construct carries a kit_choice, the advisor must populate
    kit_choice_consistency with the original kit and a boolean consistency flag."""
    kcc = construct_result["kit_choice_consistency"]
    assert kcc["kit_choice"] == "lentiCRISPRv2", (
        f"kit_choice not echoed back: {kcc}"
    )
    assert kcc["consistent"] in (True, False), (
        f"consistent flag must be a real bool, got: {kcc['consistent']!r}"
    )
    assert isinstance(kcc["note"], str) and len(kcc["note"]) > 0, (
        f"note must be a non-empty string, got: {kcc['note']!r}"
    )


def test_construct_path_hek293_prefers_transient(construct_result):
    """HEK293 SpCas9 knockout is a textbook transient-delivery case — the
    advisor should top-rank lipofection or RNP, NOT the upstream lentiviral kit."""
    top = construct_result["top_recommendation"].lower()
    assert "lipofection" in top or "rnp" in top or "electroporation" in top, (
        f"Top rec should be transient for HEK293 SpCas9 KO, got: {top}"
    )


def test_explicit_kwarg_overrides_construct(advisor):
    """If caller passes both construct and an explicit cell_type, the kwarg wins."""
    result = advisor.run(
        cell_type="primary T cells",
        construct=YUSHAN_CONSTRUCT,  # has cell_type=HEK293
    )
    # Top rec should reflect the override (primary T cells → RNP/electroporation)
    top = result["top_recommendation"].lower()
    assert "rnp" in top or "electroporation" in top, (
        f"Override failed — got HEK293-style answer: {top}"
    )


def test_no_kit_choice_leaves_consistency_null(advisor):
    """Legacy kwarg path (no construct) should return a null-filled
    kit_choice_consistency so the output schema stays stable."""
    result = advisor.run(cell_type="HEK293", cas_variant="SpCas9")
    kcc = result["kit_choice_consistency"]
    assert kcc == {"kit_choice": None, "consistent": None, "note": None}, (
        f"kit_choice_consistency not null-filled: {kcc}"
    )


# --- Off-target burden classifier tests (no API call) ---

def test_off_target_burden_perfect_match_is_high():
    from modules.delivery_advisor.tools.delivery_advisor import _classify_off_target_burden
    profile = {"total_off_targets": 1, "mismatch_distribution": {"0MM": 1, "1MM": 0}}
    assert _classify_off_target_burden(profile) == "high"


def test_off_target_burden_yushan_sample_is_medium():
    """Yushan's sample (total=2, 2MM=1, 3MM=1) is medium burden — no near-perfect hits."""
    from modules.delivery_advisor.tools.delivery_advisor import _classify_off_target_burden
    profile = {"total_off_targets": 2, "mismatch_distribution": {"0MM": 0, "1MM": 0, "2MM": 1, "3MM": 1}}
    assert _classify_off_target_burden(profile) == "medium"


def test_off_target_burden_string_passthrough():
    from modules.delivery_advisor.tools.delivery_advisor import _classify_off_target_burden
    assert _classify_off_target_burden("high") == "high"
    assert _classify_off_target_burden("low") == "low"
    assert _classify_off_target_burden(None) == "unknown"


# --- Upstream construct status / warnings surfacing ---

def test_unsupported_status_surfaces_warnings(advisor):
    """If upstream marks construct as unsupported or includes warnings, the advisor
    must propagate that signal in the result so callers can't silently miss it."""
    construct = {
        **YUSHAN_CONSTRUCT,
        "status": "unsupported",
        "warnings": ["Cas variant incompatible with kit"],
    }
    result = advisor.run(construct=construct)
    assert "upstream_construct_warnings" in result, (
        "Unsupported construct must surface upstream_construct_warnings"
    )
    ucw = result["upstream_construct_warnings"]
    assert ucw["status"] == "unsupported"
    assert "Cas variant incompatible with kit" in ucw["warnings"]


def test_supported_construct_does_not_add_warnings(construct_result):
    """A clean supported construct (Yushan's default sample) should NOT have
    upstream_construct_warnings — only present when there's actually a problem."""
    assert "upstream_construct_warnings" not in construct_result
