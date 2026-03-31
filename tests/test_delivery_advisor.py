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
