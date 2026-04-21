from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from rapidfuzz import fuzz

from ..core.schemas import CandidateScore
from ..core.settings import settings


@dataclass(frozen=True)
class ScoredText:
    candidate_id: str
    strategy: str
    text: str
    confidence: float
    score: CandidateScore
    notes: list[str]


class SemanticSimilarityScorer:
    def __init__(self) -> None:
        self._bundle: dict[str, Any] | None = None
        self._disabled = False

    def score(self, source_text: str, candidate_text: str) -> float:
        if not source_text.strip() or not candidate_text.strip():
            return 0.0

        if not settings.enable_semantic_similarity:
            return 0.5

        bundle = self._load_bundle()
        if bundle is None:
            return 0.5

        try:
            source_embedding = self._encode(bundle, source_text)
            candidate_embedding = self._encode(bundle, candidate_text)
            similarity = float((source_embedding * candidate_embedding).sum().item())
            return max(0.0, min(1.0, (similarity + 1.0) / 2.0))
        except Exception:  # noqa: BLE001
            return 0.5

    def _load_bundle(self) -> dict[str, Any] | None:
        if self._bundle is not None:
            return self._bundle
        if self._disabled:
            return None

        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                settings.semantic_model_id,
                cache_dir=settings.hf_cache_dir,
            )
            model = AutoModel.from_pretrained(
                settings.semantic_model_id,
                cache_dir=settings.hf_cache_dir,
            )
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = model.to(device)
            model.eval()
            self._bundle = {
                "tokenizer": tokenizer,
                "model": model,
                "device": device,
                "torch": torch,
            }
            return self._bundle
        except Exception:  # noqa: BLE001
            self._disabled = True
            return None

    def _encode(self, bundle: dict[str, Any], text: str) -> Any:
        tokenizer = bundle["tokenizer"]
        model = bundle["model"]
        torch = bundle["torch"]
        device = bundle["device"]

        encoded = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}

        with torch.no_grad():
            output = model(**encoded)
            token_embeddings = output.last_hidden_state
            attention_mask = encoded["attention_mask"].unsqueeze(-1)
            pooled = (token_embeddings * attention_mask).sum(dim=1) / attention_mask.sum(dim=1).clamp(min=1)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            return pooled[0]


class TonalityModelScorer:
    def __init__(self) -> None:
        self._bundle: dict[str, Any] | None = None
        self._disabled = False

    def score(self, source_text: str, candidate_text: str) -> float:
        if not source_text.strip() or not candidate_text.strip():
            return 0.0

        if not settings.enable_model_tonality:
            return 0.5

        bundle = self._load_bundle()
        if bundle is None:
            return 0.5

        try:
            source_dist = self._distribution(bundle, source_text)
            candidate_dist = self._distribution(bundle, candidate_text)
            distance = float((source_dist - candidate_dist).abs().sum().item())
            similarity = 1.0 - 0.5 * distance
            return max(0.0, min(1.0, similarity))
        except Exception:  # noqa: BLE001
            return 0.5

    def _load_bundle(self) -> dict[str, Any] | None:
        if self._bundle is not None:
            return self._bundle
        if self._disabled:
            return None

        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                settings.tonality_model_id,
                cache_dir=settings.hf_cache_dir,
                use_fast=False,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                settings.tonality_model_id,
                cache_dir=settings.hf_cache_dir,
            )
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = model.to(device)
            model.eval()
            self._bundle = {
                "tokenizer": tokenizer,
                "model": model,
                "device": device,
                "torch": torch,
            }
            return self._bundle
        except Exception:  # noqa: BLE001
            self._disabled = True
            return None

    def _distribution(self, bundle: dict[str, Any], text: str) -> Any:
        tokenizer = bundle["tokenizer"]
        model = bundle["model"]
        torch = bundle["torch"]
        device = bundle["device"]

        encoded = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}

        with torch.no_grad():
            logits = model(**encoded).logits[0]
            return torch.softmax(logits, dim=-1)


class HeuristicScorer:
    def __init__(self) -> None:
        self._semantic_scorer = SemanticSimilarityScorer()
        self._tonality_scorer = TonalityModelScorer()
        self._weights = {
            "entities": 0.20,
            "length": 0.08,
            "target_script": 0.17,
            "tonality": 0.15,
            "semantic": 0.27,
            "fluency": 0.09,
            "confidence": 0.04,
        }

    def score(self, source_text: str, candidate_text: str, source_language: str, target_language: str, confidence: float) -> CandidateScore:
        entities = self._entity_score(source_text, candidate_text)
        length = self._length_score(source_text, candidate_text)
        target_script = self._script_score(candidate_text, target_language)
        tonality = self._tonality_score(source_text, candidate_text)
        semantic = self._semantic_score(source_text, candidate_text)
        fluency = self._fluency_score(candidate_text)
        confidence_score = max(0.0, min(confidence, 1.0))

        weighted_features = {
            "entities": entities,
            "length": length,
            "target_script": target_script,
            "tonality": tonality,
            "semantic": semantic,
            "fluency": fluency,
            "confidence": confidence_score,
        }
        total = round(
            sum(self._weights[key] * weighted_features[key] for key in self._weights),
            4,
        )
        return CandidateScore(
            entities=round(entities, 4),
            length=round(length, 4),
            target_script=round(target_script, 4),
            tonality=round(tonality, 4),
            semantic=round(semantic, 4),
            fluency=round(fluency, 4),
            confidence=round(confidence_score, 4),
            total=total,
        )

    def _entity_score(self, source_text: str, candidate_text: str) -> float:
        strict_entities = self._extract_strict_entities(source_text)
        named_entities = self._extract_named_entities(source_text)

        strict_score = self._preservation_ratio(strict_entities, candidate_text, use_fuzzy=False)
        named_score = self._preservation_ratio(named_entities, candidate_text, use_fuzzy=True)

        if strict_entities and named_entities:
            return 0.75 * strict_score + 0.25 * named_score
        if strict_entities:
            return strict_score
        if named_entities:
            return 0.7 * named_score + 0.3
        return 0.8

    def _extract_strict_entities(self, source_text: str) -> list[str]:
        patterns = [
            r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
            r"https?://\S+",
            r"(?:^|\s)[@#][A-Za-z0-9_]+",
            r"\b\d+(?:[.,]\d+)?\b",
        ]
        extracted: list[str] = []
        for pattern in patterns:
            extracted.extend(match.strip() for match in re.findall(pattern, source_text))
        return self._dedupe_casefold(extracted)

    def _extract_named_entities(self, source_text: str) -> list[str]:
        patterns = [
            r"\b[A-Z][A-Za-z0-9_\-]{1,}\b",
            r"\b[A-Z]{2,}\b",
        ]
        extracted: list[str] = []
        for pattern in patterns:
            extracted.extend(match.strip() for match in re.findall(pattern, source_text))
        return self._dedupe_casefold(extracted)

    def _dedupe_casefold(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for token in values:
            lowered = token.lower()
            if lowered not in seen:
                seen.add(lowered)
                unique.append(token)
        return unique

    def _preservation_ratio(self, entities: list[str], candidate_text: str, use_fuzzy: bool) -> float:
        if not entities:
            return 1.0

        candidate_lower = candidate_text.lower()
        candidate_tokens = re.findall(r"[\w@#.+:-]+", candidate_lower)
        preserved = 0

        for entity in entities:
            normalized = entity.lower()
            if normalized in candidate_lower:
                preserved += 1
                continue

            if use_fuzzy and candidate_tokens:
                best = max(fuzz.ratio(normalized, token) for token in candidate_tokens)
                if best >= 85.0:
                    preserved += 1

        return preserved / len(entities)

    def _length_score(self, source_text: str, candidate_text: str) -> float:
        source_length = max(len(source_text), 1)
        candidate_length = max(len(candidate_text), 1)
        ratio = min(source_length, candidate_length) / max(source_length, candidate_length)
        return max(0.0, min(1.0, ratio))

    def _script_score(self, candidate_text: str, target_language: str) -> float:
        letters = [char for char in candidate_text if char.isalpha()]
        if not letters:
            return 0.0
        if target_language == "en":
            latin = sum(1 for char in letters if char.isascii())
            return latin / len(letters)
        target_ranges = {
            "hi": ((0x0900, 0x097F),),
            "kn": ((0x0C80, 0x0CFF),),
            "ta": ((0x0B80, 0x0BFF),),
            "ml": ((0x0D00, 0x0D7F),),
            "te": ((0x0C00, 0x0C7F),),
        }
        ranges = target_ranges.get(target_language, ())
        if not ranges:
            return 0.5
        matches = 0
        for char in letters:
            codepoint = ord(char)
            if any(start <= codepoint <= end for (start, end) in ranges):
                matches += 1
        return matches / len(letters)

    def _tonality_score(self, source_text: str, candidate_text: str) -> float:
        return self._tonality_scorer.score(source_text, candidate_text)

    def _semantic_score(self, source_text: str, candidate_text: str) -> float:
        return self._semantic_scorer.score(source_text, candidate_text)

    def _fluency_score(self, candidate_text: str) -> float:
        tokens = re.findall(r"\w+", candidate_text, flags=re.UNICODE)
        if not tokens:
            return 0.0

        lowered = [token.lower() for token in tokens]
        unique_ratio = len(set(lowered)) / len(lowered)

        consecutive_repeats = sum(1 for index in range(1, len(lowered)) if lowered[index] == lowered[index - 1])
        repeat_penalty = consecutive_repeats / max(len(lowered) - 1, 1)

        stretched_chars = len(re.findall(r"(.)\1{3,}", candidate_text))
        punct_bursts = len(re.findall(r"[!?.,]{3,}", candidate_text))
        noise_penalty = min(1.0, stretched_chars * 0.15 + punct_bursts * 0.1)

        score = (
            0.55 * unique_ratio
            + 0.3 * (1.0 - repeat_penalty)
            + 0.15 * (1.0 - noise_penalty)
        )
        return max(0.0, min(1.0, score))


class CandidateSelector:
    def select(self, candidates: list[ScoredText]) -> ScoredText:
        return sorted(candidates, key=lambda item: (item.score.total, item.confidence), reverse=True)[0]
