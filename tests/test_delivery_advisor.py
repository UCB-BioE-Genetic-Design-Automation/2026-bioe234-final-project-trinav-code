"""
Unit tests for the delivery_advisor module.

Tests cover input validation (no API call) and live Gemini API tests
that verify the structure and biological plausibility of responses.
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
