"""CRISPR Delivery Strategy Advisor.

Uses an internal Claude API call to recommend delivery methods
for a given cell type, Cas variant, and edit type."""

import json
import os
import urllib.request


SYSTEM_PROMPT = """You are an expert molecular biologist specializing in CRISPR delivery methods.
Given a cell type, Cas variant, and edit type, recommend the best delivery strategies.

Respond ONLY with a valid JSON object in this exact format, no other text:
{
  "top_recommendation": "<single best method as a short string>",
  "ranked_methods": [
    {
      "method": "<method name>",
      "suitability": "<high|medium|low>",
      "rationale": "<1-2 sentence explanation>",
      "key_considerations": ["<consideration 1>", "<consideration 2>"]
    }
  ],
  "general_advice": "<1-2 sentences of general advice for this specific combination>"
}

Include 3-5 methods in ranked_methods, ordered from most to least suitable.
Be specific to the cell type and Cas variant provided — do not give generic answers.
Consider: cargo size (plasmid vs RNP vs mRNA), cell division status, primary vs cell line,
immunogenicity, off-target integration risk, and edit type requirements."""


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
            "max_tokens": 1024,
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
