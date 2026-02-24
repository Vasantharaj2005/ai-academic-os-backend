"""
Question Paper AI Agent
Generates structured question papers for any exam type using the LLM.
Reads the course's curriculum/CLOs from memory to align questions with outcomes.
"""

import json
import uuid
import logging
import time
from typing import Dict, Any, Optional, List

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from app.models.schemas.question_paper import EXAM_DEFAULTS

logger = logging.getLogger(__name__)


class QuestionPaperAgent(BaseAgent):
    """
    Standalone agent — not part of the main generation pipeline.
    Called directly from the question paper API route.
    Generates a complete, exam-type-aware question paper using the active LLM.
    """

    def __init__(self, llm_service, rag_service=None, shared_memory=None):
        super().__init__(
            agent_id="question_paper_agent",
            agent_name="Question Paper Agent",
            llm_service=llm_service,
            rag_service=rag_service,
            shared_memory=shared_memory,
        )

    async def process(self, context: AgentContext) -> AgentResult:
        start = time.time()
        try:
            data        = context.input_data
            exam_type   = data["exam_type"]          # e.g. "CIA-1"
            course_data = data["course_data"]         # dict with title, CLOs, modules, etc.
            request     = data["request"]             # QuestionPaperRequest dict

            defaults    = EXAM_DEFAULTS.get(exam_type, EXAM_DEFAULTS["CIA-1"])
            parts       = defaults.get("parts", [])

            paper = await self._generate_paper(
                exam_type=exam_type,
                course_data=course_data,
                parts=parts,
                defaults=defaults,
                request=request,
            )

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=paper,
                processing_time=time.time() - start,
            )

        except Exception as e:
            logger.error(f"QuestionPaperAgent failed: {e}", exc_info=True)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                data={},
                error=str(e),
                processing_time=time.time() - start,
            )

    # ── Core generation ────────────────────────────────────────────────────────

    async def _generate_paper(
        self,
        exam_type: str,
        course_data: Dict[str, Any],
        parts: List[Dict],
        defaults: Dict,
        request: Dict[str, Any],
    ) -> Dict[str, Any]:

        curriculum = course_data.get("curriculum_data") or {}
        modules    = curriculum.get("modules", [])
        clos       = curriculum.get("course_learning_outcomes", [])
        modules_covered = request.get("modules_covered") or defaults.get("modules_covered", "All Modules")
        difficulty      = request.get("difficulty", "mixed")
        extra_context   = request.get("additional_context", "")

        # Filter modules based on modules_covered text
        relevant_modules = self._filter_relevant_modules(modules, modules_covered)

        # Build compact topic/CLO context for the prompt
        topics_summary = self._build_topic_summary(relevant_modules, clos)

        # Generate each part/section from the LLM
        sections = []
        for part in parts:
            label       = part["label"]
            qtype       = part["type"]
            num_q       = part["num_questions"]
            marks_each  = part["marks_each"]
            choose      = part.get("choose")
            either_or   = part.get("either_or", False)

            system_msg = self._system_prompt(exam_type, course_data)
            prompt     = self._build_prompt(
                exam_type=exam_type,
                part_label=label,
                question_type=qtype,
                num_questions=num_q,
                marks_each=marks_each,
                difficulty=difficulty,
                topics_summary=topics_summary,
                choose=choose,
                either_or=either_or,
                extra_context=extra_context,
            )

            raw = await self.call_llm(
                prompt=prompt,
                system_message=system_msg,
                temperature=0.4,
                max_tokens=3000,
                response_format="json",
            )
            questions = self._parse_questions(raw, marks_each)

            sections.append({
                "label":      label,
                "type":       qtype,
                "marks_each": marks_each,
                "choose":     choose,
                "either_or":  either_or,
                "questions":  questions,
            })

        return {
            "sections":         sections,
            "part_count":       len(sections),
            "total_generated":  sum(len(s["questions"]) for s in sections),
            "modules_covered":  modules_covered,
        }

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _filter_relevant_modules(self, modules: List[Dict], coverage: str) -> List[Dict]:
        """Return modules whose number/title matches the coverage string."""
        if not modules or "all" in coverage.lower():
            return modules
        relevant = []
        for m in modules:
            num   = str(m.get("module_number", ""))
            title = m.get("title", "").lower()
            if num in coverage or title[:10].lower() in coverage.lower():
                relevant.append(m)
        return relevant or modules     # fall back to all if nothing matched

    def _build_topic_summary(self, modules: List[Dict], clos: List[Dict]) -> str:
        parts = []
        for m in modules[:5]:
            topics = ", ".join(m.get("topics", [])[:6])
            parts.append(f"Module {m.get('module_number','')}: {m.get('title','')} — {topics}")
        clo_stmts = [f"{c.get('id')}: {c.get('statement','')[:80]}" for c in clos[:6]]
        return "\n".join(parts) + "\n\nCLOs:\n" + "\n".join(clo_stmts)

    def _system_prompt(self, exam_type: str, course_data: Dict) -> str:
        return (
            f"You are an expert academic question paper setter for Indian universities. "
            f"You are generating a {exam_type} question paper for the course: "
            f"'{course_data.get('title', 'Course')}'. "
            f"Follow AICTE/Anna University / VTU patterns. "
            f"Return ONLY valid JSON — no markdown, no prose outside JSON."
        )

    def _build_prompt(
        self,
        exam_type: str,
        part_label: str,
        question_type: str,
        num_questions: int,
        marks_each: int,
        difficulty: str,
        topics_summary: str,
        choose: Optional[int],
        either_or: bool,
        extra_context: str,
    ) -> str:

        choose_note = ""
        if choose:
            choose_note = f"Generate {num_questions} questions (students answer any {choose})."
        elif either_or:
            choose_note = f"Generate {num_questions} questions as either/or pairs."
        else:
            choose_note = f"Generate exactly {num_questions} questions."

        return f"""
Generate the {part_label} of a {exam_type} examination paper.
Section type: {question_type}
{choose_note}
Marks per question: {marks_each}
Difficulty: {difficulty}
{f'Additional instructions: {extra_context}' if extra_context else ''}

Topics and CLOs available:
{topics_summary}

Return a JSON object with this exact structure:
{{
  "questions": [
    {{
      "question": "Full question text",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create",
      "marks": {marks_each},
      "answer_hint": "brief key points for answer (1-2 lines)",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."]   // only for MCQ, else null
    }}
  ]
}}
Ensure questions are original, academically rigorous, and directly related to the topics above.
"""

    def _parse_questions(self, raw: str, marks_each: int) -> List[Dict]:
        """Parse LLM JSON output safely."""
        try:
            # Try to find JSON in the response
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start == -1:
                return self._mock_questions(marks_each)
            obj = json.loads(raw[start:end])
            return obj.get("questions", [])
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM question output: {e}. Using mock.")
            return self._mock_questions(marks_each)

    def _mock_questions(self, marks_each: int) -> List[Dict]:
        return [
            {
                "question":    "Define the fundamental concepts of this subject. Explain with examples.",
                "bloom_level": "understand",
                "marks":       marks_each,
                "answer_hint": "See lecture notes.",
                "options":     None,
            }
        ]
