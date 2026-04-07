from __future__ import annotations

from dataclasses import dataclass

from ..core.language import LanguageRegistry
from ..core.schemas import CandidateScore, TranslationCandidate, TranslationRequest, TranslationResponse
from .model_adapter import ModelAdapter
from .scoring import CandidateSelector, HeuristicScorer, ScoredText
from .text_processing import TextPreprocessor


@dataclass
class PairRouting:
    prompt_profile: str
    retry_profile: str


class LanguagePairRouter:
    def route(self, source_language: str, target_language: str) -> PairRouting:
        if source_language == "en" or target_language == "en":
            return PairRouting(prompt_profile="faithful", retry_profile="strict")
        return PairRouting(prompt_profile="balanced", retry_profile="strict")


class TranslationPipeline:
    def __init__(self) -> None:
        self.registry = LanguageRegistry()
        self.preprocessor = TextPreprocessor()
        self.router = LanguagePairRouter()
        self.adapter = ModelAdapter(self.registry)
        self.scorer = HeuristicScorer()
        self.selector = CandidateSelector()

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        if request.source_language == request.target_language:
            candidate = self._make_identity_candidate(request.text)
            return self._build_response(request, [candidate], candidate, retry_used=False)

        normalized = self.preprocessor.normalize(request.text)
        routing = self.router.route(request.source_language, request.target_language)
        candidates = self._generate_candidates(
            normalized,
            request.source_language,
            request.target_language,
            routing.prompt_profile,
            request.max_candidates,
        )
        selected = self.selector.select(candidates)

        retry_used = False
        if selected.score.total < 0.58:
            retry_used = True
            retry_candidates = self._generate_candidates(
                normalized,
                request.source_language,
                request.target_language,
                routing.retry_profile,
                request.max_candidates,
            )
            candidates.extend(retry_candidates)
            selected = self.selector.select(candidates)

        return self._build_response(request, candidates, selected, retry_used)

    def _generate_candidates(self, text: str, source_language: str, target_language: str, profile: str, max_candidates: int) -> list[ScoredText]:
        strategy_map = {
            "faithful": ["greedy", "beam", "sample"],
            "balanced": ["beam", "greedy", "sample"],
            "strict": ["strict", "beam", "greedy"],
        }
        strategies = strategy_map.get(profile, ["beam", "greedy", "sample"])
        candidates: list[ScoredText] = []
        for index, strategy in enumerate(strategies[:max_candidates], start=1):
            translated, confidence = self.adapter.translate(text, source_language, target_language, strategy)
            score = self.scorer.score(text, translated, source_language, target_language, confidence)
            notes = self._build_notes(score, confidence)
            candidates.append(
                ScoredText(
                    candidate_id=f"cand-{profile}-{index}",
                    strategy=strategy,
                    text=translated,
                    confidence=confidence,
                    score=score,
                    notes=notes,
                )
            )
        return candidates

    def _build_notes(self, score: CandidateScore, confidence: float) -> list[str]:
        notes: list[str] = []
        if score.entities < 0.5:
            notes.append("Entity handling needs improvement")
        if score.punctuation < 0.5:
            notes.append("Punctuation drift detected")
        if score.tonality < 0.5:
            notes.append("Tone alignment is low")
        if score.target_script < 0.5:
            notes.append("Target script coverage is low")
        if confidence < 0.5:
            notes.append("Model confidence is low")
        if not notes:
            notes.append("Balanced candidate")
        return notes

    def _make_identity_candidate(self, text: str) -> ScoredText:
        score = CandidateScore(
            punctuation=1.0,
            entities=1.0,
            length=1.0,
            target_script=1.0,
            tonality=1.0,
            confidence=1.0,
            total=1.0,
        )
        return ScoredText(
            candidate_id="cand-identity",
            strategy="identity",
            text=text,
            confidence=1.0,
            score=score,
            notes=["Source and target language are identical"],
        )

    def _build_response(self, request: TranslationRequest, candidates: list[ScoredText], selected: ScoredText, retry_used: bool) -> TranslationResponse:
        candidate_models = [
            TranslationCandidate(
                candidate_id=item.candidate_id,
                strategy=item.strategy,
                text=item.text,
                confidence=item.confidence,
                score=item.score.total,
                breakdown=item.score,
                notes=item.notes,
            )
            for item in candidates
        ]
        selected_model = next(item for item in candidate_models if item.candidate_id == selected.candidate_id)
        return TranslationResponse(
            source_language=request.source_language,
            target_language=request.target_language,
            pair_label=self.registry.pair_label(request.source_language, request.target_language),
            input_text=request.text,
            selected_candidate=selected_model,
            candidates=candidate_models,
            model_status=self.adapter.status,
            retry_used=retry_used,
            diagnostics={
                "candidate_count": len(candidate_models),
                "selected_strategy": selected.strategy,
                "selected_total_score": selected.score.total,
                "selected_confidence": selected.confidence,
            },
        )
