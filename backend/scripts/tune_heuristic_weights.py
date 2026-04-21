from __future__ import annotations

import json
import random
import urllib.error
import urllib.request

API_URL = "http://127.0.0.1:8000/api/translate"

WEIGHT_KEYS = [
    "entities",
    "length",
    "target_script",
    "tonality",
    "semantic",
    "fluency",
    "confidence",
]

BASELINE_WEIGHTS = {
    "entities": 0.20,
    "length": 0.08,
    "target_script": 0.17,
    "tonality": 0.15,
    "semantic": 0.27,
    "fluency": 0.09,
    "confidence": 0.04,
}

# Oracle utility emphasizes meaning preservation first, then correctness and readability.
ORACLE_WEIGHTS = {
    "entities": 0.18,
    "length": 0.05,
    "target_script": 0.18,
    "tonality": 0.17,
    "semantic": 0.31,
    "fluency": 0.08,
    "confidence": 0.03,
}

EVAL_CASES = [
    {
        "text": "Please send the report by 5 PM. Thanks!",
        "source_language": "en",
        "target_language": "hi",
    },
    {
        "text": "Meeting shifted to Tuesday, 10:30 AM. Please confirm.",
        "source_language": "en",
        "target_language": "ta",
    },
    {
        "text": "Our website is https://example.com and support email is help@example.com",
        "source_language": "en",
        "target_language": "kn",
    },
    {
        "text": "Can you review this urgently? I am worried about delays.",
        "source_language": "en",
        "target_language": "ml",
    },
    {
        "text": "The budget is 12,500 INR for phase 1 and 18,000 INR for phase 2.",
        "source_language": "en",
        "target_language": "te",
    },
    {
        "text": "దయచేసి ఈ అప్‌డేట్‌ను ఈ సాయంత్రం లోపు పంపండి.",
        "source_language": "te",
        "target_language": "en",
    },
    {
        "text": "कृपया इसे विनम्र और स्पष्ट भाषा में लिखिए।",
        "source_language": "hi",
        "target_language": "en",
    },
    {
        "text": "மீட்டிங் நாளை இல்லை, வெள்ளிக்கிழமைக்கு மாற்றப்பட்டுள்ளது.",
        "source_language": "ta",
        "target_language": "en",
    },
]


def post_translate(payload: dict[str, object]) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc


def weighted_score(breakdown: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights[key] * float(breakdown.get(key, 0.0)) for key in WEIGHT_KEYS)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return {key: 1.0 / len(WEIGHT_KEYS) for key in WEIGHT_KEYS}
    return {key: value / total for key, value in weights.items()}


def random_weight_vector() -> dict[str, float]:
    raw = {key: random.random() for key in WEIGHT_KEYS}
    return normalize_weights(raw)


def collect_candidate_breakdowns(cases: list[dict[str, object]]) -> list[list[dict[str, float]]]:
    collected: list[list[dict[str, float]]] = []

    for case in cases:
        response = post_translate(
            {
                **case,
                "max_candidates": 3,
            }
        )

        candidates = response.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            continue

        rows: list[dict[str, float]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            breakdown = candidate.get("breakdown", {})
            if not isinstance(breakdown, dict):
                continue
            rows.append({key: float(breakdown.get(key, 0.0)) for key in WEIGHT_KEYS})

        if rows:
            collected.append(rows)

    return collected


def evaluate_dataset(weights: dict[str, float], collected: list[list[dict[str, float]]]) -> tuple[float, float]:
    selected_oracle_values: list[float] = []
    oracle_matches = 0

    for candidates in collected:
        if not candidates:
            continue

        oracle_index = 0
        oracle_best = -1.0
        selected_index = 0
        selected_best = -1.0

        for idx, candidate in enumerate(candidates):
            oracle_value = weighted_score(candidate, ORACLE_WEIGHTS)
            if oracle_value > oracle_best:
                oracle_best = oracle_value
                oracle_index = idx

            selected_value = weighted_score(candidate, weights)
            if selected_value > selected_best:
                selected_best = selected_value
                selected_index = idx

        if oracle_best >= 0.0:
            selected_oracle_values.append(weighted_score(candidates[selected_index], ORACLE_WEIGHTS))
            if selected_index == oracle_index:
                oracle_matches += 1

    if not selected_oracle_values:
        return 0.0, 0.0

    mean_oracle_utility = sum(selected_oracle_values) / len(selected_oracle_values)
    agreement = oracle_matches / len(selected_oracle_values)
    return mean_oracle_utility, agreement


def main() -> None:
    print("starting_weight_tuning")

    collected = collect_candidate_breakdowns(EVAL_CASES)
    print(json.dumps({"evaluated_case_count": len(collected)}))

    baseline_utility, baseline_agreement = evaluate_dataset(BASELINE_WEIGHTS, collected)
    print(
        json.dumps(
            {
                "baseline_weights": BASELINE_WEIGHTS,
                "baseline_mean_oracle_utility": round(baseline_utility, 5),
                "baseline_oracle_agreement": round(baseline_agreement, 5),
            },
            ensure_ascii=False,
        )
    )

    best_weights = BASELINE_WEIGHTS.copy()
    best_utility = baseline_utility
    best_agreement = baseline_agreement

    for _ in range(7000):
        candidate_weights = random_weight_vector()
        utility, agreement = evaluate_dataset(candidate_weights, collected)

        # Primary target: maximize oracle utility. Secondary: maximize agreement.
        if utility > best_utility + 1e-9 or (
            abs(utility - best_utility) <= 1e-9 and agreement > best_agreement
        ):
            best_weights = candidate_weights
            best_utility = utility
            best_agreement = agreement

    print(
        json.dumps(
            {
                "best_weights": {k: round(v, 4) for k, v in best_weights.items()},
                "best_mean_oracle_utility": round(best_utility, 5),
                "best_oracle_agreement": round(best_agreement, 5),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
