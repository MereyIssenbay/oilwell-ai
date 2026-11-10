"""Grounding by construction: the provider selects IDs; Python renders facts."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import threading
import unicodedata

from llm.knowledge import KnowledgeBase, digest
from llm.providers.openai import OpenAIProvider, ProviderInvalid, ProviderUnavailable
from llm.schemas import Claim, EvidencePacket, Explanation, ExplanationRequest, Selection
from llm.store import ExplanationStore

LIMITATIONS = [
    Claim(claim_id="limit-score", text="Confidence is an uncalibrated model score, not certainty or verified event identity.", evidence_ids=["p1"]),
    Claim(claim_id="limit-model", text="This binary diagnostic model is rejected for monitoring. It cannot establish an event family, physical cause, or operating procedure.", evidence_ids=["m1"]),
    Claim(claim_id="limit-time", text="Historical playback only. Original source timezone is unknown; source coordinates are not verified UTC times.", evidence_ids=["w1", "h1"]),
    Claim(claim_id="limit-summary", text="Sensor means, latest readings and trends describe the supplied causal window; they are not feature attribution or proof of what caused the model decision.", evidence_ids=["w1", "m1"]),
]

QUESTIONS = {
    "": "explain", "explain": "explain", "explain this alert": "explain", "explain the alert": "explain",
    "explain this prediction": "explain", "why this alert": "explain", "why did this alert trigger": "explain",
    "what did the model observe": "observations", "what was observed": "observations", "show sensor readings": "observations",
    "what observations support this prediction": "observations", "what does this alert mean": "explain",
    "what does confidence mean": "score", "how confident is the model": "score", "explain the score": "score",
    "are any sensors missing": "missing", "what data is missing": "missing", "show missing data": "missing",
    "show sensor trends": "trends", "what are the trends": "trends", "what changed": "trends",
    "объясни тревогу": "explain", "объясни прогноз": "explain", "почему тревога": "explain",
    "что наблюдала модель": "observations", "какие данные отсутствуют": "missing",
    "что означает уверенность": "score", "покажи тренды": "trends",
}

INTERPRETATIONS = {
    "3w-missingness": "Missing observations limit the window summary. The public 3W description documents missing and frozen variables; it cannot establish why a particular reading is unavailable.",
    "3w-origins": "Real, simulated and hand-drawn are different source origins. Historical playback describes how records are displayed, not how the original data were produced.",
    "nist-association": "A possible statistical association is not a verified physical explanation. These observed summaries and the binary score cannot establish causality or a well diagnosis.",
}


def intent_for(question: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", question).strip().lower().rstrip("?.!").strip()
    return QUESTIONS.get(re.sub(r"\s+", " ", normalized))


def _number(value: float | None) -> str:
    return "unavailable" if value is None else format(value, ".17g")


def conflict(packet: EvidencePacket) -> bool:
    if packet.integrity != "verified":
        return True
    for sensor in packet.sensors:
        if sensor.observed_count > packet.sample_count:
            return True
        if not math.isclose(sensor.missing_fraction, 1 - sensor.observed_count / packet.sample_count, abs_tol=1e-12):
            return True
        if (sensor.mean is None) != (sensor.observed_count == 0):
            return True
        if sensor.observed_count == 0 and (sensor.latest is not None or sensor.trend_per_second is not None):
            return True
        if sensor.observed_count < 2 and sensor.trend_per_second is not None:
            return True
    if packet.event_type == "unknown":
        return (packet.abnormal_score is not None or packet.confidence is not None
                or packet.alert_status != "insufficient_data" or packet.abstention_reason is None)
    if packet.abnormal_score is None or packet.confidence is None or packet.abstention_reason is not None:
        return True
    positive = packet.abnormal_score >= packet.threshold
    return (packet.event_type != ("undesirable_event" if positive else "normal")
            or packet.alert_status != ("alert" if positive else "normal")
            or not math.isclose(packet.confidence, packet.abnormal_score if positive else 1 - packet.abnormal_score,
                                rel_tol=0, abs_tol=1e-15))


class CopilotService:
    def __init__(self, provider=None, cache_path: Path | None = None, knowledge: KnowledgeBase | None = None,
                 call_limit: int = 2):
        if type(call_limit) is not int or not 0 <= call_limit <= 2:
            raise ValueError("Phase 9 allows at most two lifetime provider calls")
        self.provider = provider
        self.knowledge = knowledge or KnowledgeBase()
        self.reviewed_sources = {s.source_id: s for s in KnowledgeBase().sources}
        self.store = ExplanationStore(cache_path)
        self.call_limit = call_limit
        self.lock = threading.RLock()

    @classmethod
    def from_environment(cls, root: Path) -> CopilotService:
        mode = os.environ.get("LLM_PROVIDER", "disabled")
        if mode not in {"disabled", "openai"}:
            raise ValueError("Unsupported LLM_PROVIDER")
        key = os.environ.get("OPENAI_API_KEY", "")
        provider = OpenAIProvider(key, os.environ.get("LLM_MODEL", "gpt-6-luna")) if mode == "openai" and key else None
        return cls(provider=provider, cache_path=Path(root) / ".local" / "copilot" / "cache.sqlite3",
                   call_limit=int(os.environ.get("LLM_MAX_CALLS", "2")))

    def get_source(self, source_id: str):
        return self.reviewed_sources[source_id]

    def list_sources(self):
        return list(self.reviewed_sources.values())

    def explain(self, packet: EvidencePacket, question: str = "", use_provider: bool = False) -> Explanation:
        request = ExplanationRequest(question=question, use_provider=use_provider)
        packet = EvidencePacket.model_validate(packet)
        evidence_hash = digest(packet.model_dump(mode="json"))
        intent = intent_for(request.question)
        key = digest({"evidence": evidence_hash, "question": request.question, "provider": request.use_provider,
                      "model": getattr(self.provider, "model", None), "kb": self.knowledge.version,
                      "prompt": "claim-selection-1.0.0"})
        # Serialize request/cache check/reservation so retries in this single-service
        # MVP never duplicate a paid request. Durable budget also spans processes.
        with self.lock:
            cached = self.store.get(key)
            if cached:
                fresh = self._explain(packet, intent, False, evidence_hash)
                try:
                    old = Explanation.model_validate_json(cached)
                    self._validate_cache(old, fresh)
                    return old.model_copy(update={"cached": True})
                except (ValueError, TypeError, KeyError):
                    # A corrupt/tampered cache never becomes factual authority and
                    # does not trigger another paid call. Rebuild known-safe facts.
                    self.store.put(key, fresh.model_dump_json())
                    return fresh
            result = self._explain(packet, intent, request.use_provider, evidence_hash)
            self.store.put(key, result.model_dump_json())
            return result

    @staticmethod
    def _validate_cache(old: Explanation, fresh: Explanation) -> None:
        if (old.evidence != fresh.evidence or old.evidence_hash != fresh.evidence_hash
                or old.kb_version != fresh.kb_version or old.prompt_version != fresh.prompt_version
                or old.prediction != fresh.prediction or old.limitations != fresh.limitations):
            raise ValueError("Cache provenance changed")
        for name in ("observations", "possible_interpretations", "citations"):
            current = {item.model_dump_json() for item in getattr(fresh, name)}
            items = [item.model_dump_json() for item in getattr(old, name)]
            if len(set(items)) != len(items) or any(item not in current for item in items):
                raise ValueError("Cache claim is not approved")
        citations = {c.source_id for c in old.citations}
        required = {cid for claim in old.possible_interpretations for cid in claim.citation_ids}
        if citations != required:
            raise ValueError("Cached citations do not support claims")
        if fresh.status == "abstained" and (old.status != "abstained" or old.abstention != fresh.abstention):
            raise ValueError("Cached abstention changed")
        if old.abstention not in {fresh.abstention, "Provider declined to select supported claims; factual deterministic context is retained."}:
            raise ValueError("Unapproved cached text")

    def _explain(self, packet: EvidencePacket, intent: str | None, use_provider: bool, evidence_hash: str) -> Explanation:
        base = dict(evidence=packet, evidence_hash=evidence_hash, kb_version=self.knowledge.version,
                    created_at=datetime.now(timezone.utc), limitations=LIMITATIONS,
                    observations=[], prediction=[], possible_interpretations=[], citations=[])
        if conflict(packet):
            return Explanation(status="abstained", reason="conflicting_evidence", abstention="Stored evidence is inconsistent; no factual alert explanation is available.", **base)
        if intent is None:
            return Explanation(status="abstained", reason="unsupported_question", abstention="This question is outside the supported evidence questions. Ask to explain this alert, show sensor readings or trends, explain the score, or show missing data. Diagnoses and control procedures are not supported.", **base)
        if packet.event_type == "unknown" or packet.sample_count < packet.expected_sample_count or not any(s.mean is not None for s in packet.sensors):
            return Explanation(status="abstained", reason="missing_evidence", abstention="A complete usable prediction and sensor window are unavailable. Missing observations do not establish normal operation.", **base)
        observations = []
        ordered = sorted(packet.sensors, key=lambda s: (s.mean is None, s.evidence_id))
        if intent == "missing":
            ordered.sort(key=lambda s: (-s.missing_fraction, s.evidence_id))
        for s in ordered[:6]:
            observations.append(Claim(claim_id="obs-" + s.evidence_id,
                text=(f"{s.sensor}: observed mean {_number(s.mean)}; endpoint reading {_number(s.latest)}; "
                      f"OLS trend {_number(s.trend_per_second)} per second; unit {s.unit or 'unspecified'}; "
                      f"{s.observed_count}/{packet.sample_count} observed, missing fraction {_number(s.missing_fraction)}."),
                evidence_ids=[s.evidence_id, "w1"]))
        prediction = [
            Claim(claim_id="pred-decision", text=(f"The stored model predicted {packet.event_type}. "
                f"Selected-class confidence {_number(packet.confidence)}; abnormal score {_number(packet.abnormal_score)}; "
                f"frozen threshold {_number(packet.threshold)} (alert when score >= threshold). "
                f"Prediction alert status: {packet.alert_status}."), evidence_ids=["p1"]),
            Claim(claim_id="pred-model", text=f"Model version: {packet.model_version}.", evidence_ids=["m1"]),
            Claim(claim_id="pred-episode", text=f"Episode state captured at prediction time: {packet.episode_state}.", evidence_ids=["r1"]),
        ]
        query = {"missing": "missing variables observations", "trends": "association causality sensor change",
                 "score": "association causality", "observations": "real simulated missing variables"}.get(intent, "missing variables association causality")
        sources = self.knowledge.retrieve(query)
        if (not sources or len(sources) > 3 or len({s.source_id for s in sources}) != len(sources)
                or any(s.source_id not in self.reviewed_sources or s.model_dump() != self.reviewed_sources[s.source_id].model_dump() for s in sources)):
            return Explanation(status="abstained", reason="conflicting_evidence", abstention="Retrieved references failed reviewed-source verification.", **base)
        interpretations = [Claim(claim_id="context-" + s.source_id, text=INTERPRETATIONS[s.source_id],
                                 evidence_ids=["w1"], citation_ids=[s.source_id]) for s in sources]
        base.update(observations=observations, prediction=prediction, possible_interpretations=interpretations, citations=sources)
        status, reason, provider_name, model, usage = "fallback", "deterministic_requested", "none", None, None
        if use_provider:
            if self.provider is None:
                reason = "provider_disabled"
            elif not self.store.reserve(self.call_limit):
                reason = "budget_exhausted"
            else:
                payload = {"intent": intent, "prediction": [c.model_dump() for c in prediction],
                           "observations": [c.model_dump() for c in observations],
                           "interpretations": [c.model_dump() for c in interpretations],
                           "sources": [{"source_id": s.source_id, "content": s.content} for s in sources],
                           "limitations": [c.model_dump() for c in LIMITATIONS]}
                try:
                    reply = self.provider.select(payload)
                    selection = Selection.model_validate(reply.selection)
                    obs = {c.claim_id: c for c in observations}
                    interps = {c.claim_id: c for c in interpretations}
                    if (not selection.observation_ids or len(set(selection.observation_ids)) != len(selection.observation_ids)
                            or len(set(selection.interpretation_ids)) != len(selection.interpretation_ids)
                            or len(set(selection.citation_ids)) != len(selection.citation_ids)
                            or any(x not in obs for x in selection.observation_ids)
                            or any(x not in interps for x in selection.interpretation_ids)):
                        raise ProviderInvalid("Unapproved claim identifier")
                    needed = {s for x in selection.interpretation_ids for s in interps[x].citation_ids}
                    if set(selection.citation_ids) != needed:
                        raise ProviderInvalid("Citation does not support selected interpretation")
                    usage = reply.usage
                    if selection.abstain:
                        return Explanation(status="abstained", reason="provider_refusal", abstention="Provider declined to select supported claims; factual deterministic context is retained.", usage=usage, **base)
                    base.update(observations=[obs[x] for x in selection.observation_ids],
                                possible_interpretations=[interps[x] for x in selection.interpretation_ids],
                                citations=[s for s in sources if s.source_id in needed])
                    status, reason, provider_name, model = "provider", "provider_selected", "openai", reply.model
                except ProviderInvalid:
                    reason = "provider_invalid"
                except (ProviderUnavailable, TimeoutError, OSError):
                    reason = "provider_unavailable"
                except Exception:
                    # An adapter is an untrusted boundary. Never surface exception
                    # messages (which could contain credentials or raw responses).
                    reason = "provider_invalid"
        return Explanation(status=status, reason=reason, abstention=None,
                           provider=provider_name, provider_model=model, usage=usage, **base)
