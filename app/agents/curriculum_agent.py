"""Curriculum Design Agent - Generates complete syllabus with CLOs."""

import json
import time
from typing import Dict, Any

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from app.services.ai.bloom_classifier import bloom_classifier


class CurriculumAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(agent_id="curr-001", agent_name="CurriculumAgent", *args, **kwargs)

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        try:
            if not await self.validate_input(context):
                return self.format_error_result("Invalid input", time.time() - start_time, context)

            course = context.input_data
            rag_docs = await self.enhance_with_rag(
                f"{course.get('title')} {course.get('program')} syllabus curriculum",
                context,
                top_k=3,
            )

            prompt = self._build_prompt(course, rag_docs)
            system_msg = (
                "You are an expert curriculum designer for engineering/management education. "
                "Generate comprehensive course syllabi following AICTE guidelines and Bloom's taxonomy. "
                "Always respond with valid JSON only."
            )

            response = await self.call_llm(prompt, system_msg, temperature=0.3, max_tokens=4000)
            curriculum = self._parse_response(response)
            curriculum = self._enrich_with_bloom(curriculum)

            await self.update_shared_memory("curriculum", curriculum, context)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=curriculum,
                processing_time=time.time() - start_time,
                metadata={"rag_docs_used": len(rag_docs), "course": course.get("title")},
            )
        except Exception as e:
            self.logger.error(f"CurriculumAgent failed: {e}", exc_info=True)
            return self.format_error_result(str(e), time.time() - start_time, context)

    def _build_prompt(self, course: dict, rag_docs: list) -> str:
        rag_ctx = ""
        if rag_docs:
            rag_ctx = "Reference similar syllabi:\n" + "\n".join(
                f"- {d.get('content', '')[:400]}" for d in rag_docs
            )

        return f"""Generate a complete course curriculum in JSON format for:

Course Title: {course.get('title')}
Program: {course.get('program', 'B.Tech')}
Department: {course.get('department', '')}
Semester: {course.get('semester', 3)}
Credits: {course.get('credits', 4)} (1 credit = 15 contact hours)

{rag_ctx}

Return ONLY valid JSON with this exact structure:
{{
  "course_objectives": ["objective1", ...],
  "course_learning_outcomes": [
    {{"id": "CLO1", "statement": "Students will be able to...", "bloom_level": "apply", "po_mapping": ["PO1", "PO2"]}}
  ],
  "modules": [
    {{
      "module_number": 1,
      "title": "Module Title",
      "topics": ["Topic 1", "Topic 2"],
      "hours": 8,
      "clo_mapping": ["CLO1"]
    }}
  ],
  "textbooks": [
    {{"title": "", "author": "", "publisher": "", "edition": "", "year": ""}}
  ],
  "references": [
    {{"title": "", "author": "", "publisher": "", "year": ""}}
  ],
  "prerequisites": ["Prerequisite 1"],
  "assessment_weightage": {{
    "internal_assessment": 40,
    "end_semester_exam": 60
  }},
  "co_attainment_methods": ["Quiz", "Assignment", "Lab"]
}}

Ensure:
- 6-8 CLOs covering all Bloom's levels (Remember through Create)
- 5-7 modules totaling {course.get('credits', 4) * 15} contact hours
- CLOs map to Program Outcomes (PO1-PO12)
"""

    def _parse_response(self, response: str) -> Dict[str, Any]:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            self.logger.error("Failed to parse LLM response as JSON")
            return {
                "course_objectives": [],
                "course_learning_outcomes": [],
                "modules": [],
                "textbooks": [],
                "references": [],
                "prerequisites": [],
                "assessment_weightage": {},
            }

    def _enrich_with_bloom(self, curriculum: Dict[str, Any]) -> Dict[str, Any]:
        """Add Bloom's classification to each CLO."""
        clos = curriculum.get("course_learning_outcomes", [])
        for clo in clos:
            if "bloom_level" not in clo or not clo["bloom_level"]:
                level, conf = bloom_classifier.classify(clo.get("statement", ""))
                clo["bloom_level"] = level
                clo["bloom_confidence"] = conf

        # Add HOT analysis
        statements = [c.get("statement", "") for c in clos]
        curriculum["bloom_analysis"] = bloom_classifier.validate_higher_order_thinking(statements)
        return curriculum