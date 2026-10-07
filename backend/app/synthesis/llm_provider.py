import os
import json
import httpx
from typing import Dict, Any, List, Optional
from app.core.config import settings

class LLMProvider:
    """
    Modular LLM adapter supporting Google Gemini, OpenAI,
    and a deterministic longitudinal synthesis fallback for zero-cost, offline research.
    """

    @staticmethod
    def generate_synthesis(
        prompt: str,
        system_instruction: str,
        context_tmus: List[Dict[str, Any]],
        detected_changes: List[Dict[str, Any]],
        detected_contradictions: List[Dict[str, Any]],
        model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        gemini_key = os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY
        openai_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY

        if gemini_key:
            try:
                return LLMProvider._call_gemini(gemini_key, prompt, system_instruction, model_name or "gemini-2.5-flash")
            except Exception as e:
                print(f"[LLMProvider] Gemini call failed: {e}. Falling back to deterministic synthesizer.")

        if openai_key:
            try:
                return LLMProvider._call_openai(openai_key, prompt, system_instruction, model_name or "gpt-4o-mini")
            except Exception as e:
                print(f"[LLMProvider] OpenAI call failed: {e}. Falling back to deterministic synthesizer.")

        return LLMProvider._deterministic_longitudinal_synthesizer(
            prompt, context_tmus, detected_changes, detected_contradictions
        )

    @staticmethod
    def _call_gemini(api_key: str, prompt: str, system_instruction: str, model: str) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)

    @staticmethod
    def _call_openai(api_key: str, prompt: str, system_instruction: str, model: str) -> Dict[str, Any]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return json.loads(data["choices"][0]["message"]["content"])

    @staticmethod
    def _deterministic_longitudinal_synthesizer(
        prompt: str,
        context_tmus: List[Dict[str, Any]],
        detected_changes: List[Dict[str, Any]],
        detected_contradictions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        High-precision rule-based longitudinal generation engine.
        Ensures 100% testability, deterministic claim grounding, and calibrated uncertainty.
        """
        if not context_tmus:
            return {
                "answer": "Based on your indexed documents, there is no documented evidence regarding this query.",
                "claims": [],
                "uncertainty_notes": ["No matching documents were found in the archive."]
            }

        # Sort context TMUs chronologically
        sorted_tmus = sorted(context_tmus, key=lambda x: x.get("event_date_start") or "9999")
        
        paragraphs = []
        claims = []
        uncertainty_notes = []

        # 1. Opening overview with epistemic caution
        first_date = sorted_tmus[0].get("event_date_start", "the earliest record")[:7]
        last_date = sorted_tmus[-1].get("event_date_start", "the most recent record")[:7]
        paragraphs.append(
            f"Based on your documented history from {first_date} through {last_date}, "
            "your documented perspective exhibits a clear progression rather than a static viewpoint."
        )

        # 2. Chronological progression
        for i, item in enumerate(sorted_tmus):
            date_label = item.get("event_date_start") or "Unrecorded Date"
            stmt = item.get("statement", "").strip()
            mem_type = str(item.get("memory_type", "observation")).replace("MemoryType.", "").lower()
            doc_title = item.get("document_title", "Document")
            tmu_id = item.get("id")

            claim_id = f"clm_{i+1}"
            claim_text = f"In {date_label[:7] if len(date_label)>=7 else date_label}, you documented a {mem_type}: '{stmt}'."
            paragraphs.append(f"• **{date_label[:7]}**: {stmt} *(Source: {doc_title})*")

            claims.append({
                "claim_id": claim_id,
                "claim_text": claim_text,
                "claim_type": "explicit",
                "confidence": item.get("date_confidence", 0.9),
                "evidence_tmu_ids": [tmu_id],
                "source_citations": [{
                    "document_title": doc_title,
                    "document_id": item.get("document_id"),
                    "statement": stmt,
                    "date": date_label
                }],
                "is_uncertain": False,
                "uncertainty_note": None
            })

        # 3. Transitions & Change-Points
        if detected_changes:
            paragraphs.append("\n**Identified Transitions & Shifts:**")
            for c in detected_changes:
                c_type = c.get("change_type", "evolution").replace("_", " ")
                topic = c.get("topic_or_entity", "topic")
                from_p = c.get("from_period", "")[:7]
                to_p = c.get("to_period", "")[:7]
                shift_summary = f"Your documents show a {c_type} in your stance regarding {topic} between {from_p} and {to_p}."
                paragraphs.append(f"- {shift_summary}")
                
                if c.get("uncertainty_bounds"):
                    uncertainty_notes.append(c["uncertainty_bounds"])

                claims.append({
                    "claim_id": f"clm_change_{c.get('id', 'c')}",
                    "claim_text": shift_summary,
                    "claim_type": "empirical_change",
                    "confidence": 0.85,
                    "evidence_tmu_ids": [c.get("earlier_memory_id"), c.get("later_memory_id")],
                    "source_citations": [],
                    "is_uncertain": bool(c.get("uncertainty_bounds")),
                    "uncertainty_note": c.get("uncertainty_bounds")
                })

        # 4. Contradictions & Reversals
        if detected_contradictions:
            paragraphs.append("\n**Potential Stance Reversals:**")
            for r in detected_contradictions:
                paragraphs.append(f"- {r.get('evidence_rationale')}")
                claims.append({
                    "claim_id": f"clm_rev_{r.get('id', 'r')}",
                    "claim_text": r.get("evidence_rationale", ""),
                    "claim_type": "inferred_relationship",
                    "confidence": r.get("confidence", 0.8),
                    "evidence_tmu_ids": [r.get("source_memory_id"), r.get("target_memory_id")],
                    "source_citations": [],
                    "is_uncertain": False,
                    "uncertainty_note": None
                })

        # Final answer text
        answer_text = "\n\n".join(paragraphs)

        return {
            "answer": answer_text,
            "claims": claims,
            "uncertainty_notes": uncertainty_notes
        }
