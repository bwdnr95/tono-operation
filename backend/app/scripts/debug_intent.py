from __future__ import annotations

import argparse

from app.services.airbnb_intent_classifier import AirbnbIntentClassifier
from app.services.llm_intent_classifier import FineGrainedIntentResult


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug Airbnb Intent Classifier")
    parser.add_argument(
        "--text",
        type=str,
        required=True,
        help="pure guest message text",
    )
    args = parser.parse_args()

    classifier = AirbnbIntentClassifier()

    hybrid = classifier.classify_airbnb_guest_intent(
        pure_guest_message=args.text,
        subject=None,
        snippet=None,
    )

    print("==== HybridIntentResult ====")
    print(f"primary_intent     : {hybrid.message_result.intent.name}")
    print(f"primary_confidence : {hybrid.message_result.confidence:.3f}")
    print(f"is_ambiguous       : {hybrid.message_result.is_ambiguous}")
    print(f"reasons            : {hybrid.message_result.reasons}")

    if hybrid.rule_fine_result:
        r = hybrid.rule_fine_result
        print("\n---- Rule Result ----")
        print(f"rule_fine_intent   : {r.fine_intent.name}")
        print(f"rule_primary_intent: {r.primary_intent.name}")
        print(f"rule_confidence    : {r.confidence:.3f}")
        print(f"rule_reasons       : {r.reasons}")

    if hybrid.llm_fine_result:
        l: FineGrainedIntentResult = hybrid.llm_fine_result
        print("\n---- LLM Result ----")
        print(f"llm_fine_intent    : {l.fine_intent.name}")
        print(f"llm_primary_intent : {l.primary_intent.name}")
        print(f"llm_confidence     : {l.confidence:.3f}")
        print(f"llm_reasons        : {l.reasons}")


if __name__ == "__main__":
    main()
