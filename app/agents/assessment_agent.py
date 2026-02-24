"""Assessment Design Agent - Generates question banks and exam papers."""

import json
import time
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from app.services.ai.bloom_classifier import bloom_classifier


class AssessmentAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(agent_id="ass-001", agent_name="AssessmentAgent", *args, **kwargs)

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        try:
            curriculum = await self.get_from_shared_memory("curriculum", context)
            semester_plan = await self.get_from_shared_memory("semester_plan", context)

            if not curriculum:
                return self.format_error_result("Curriculum not found", time.time() - start_time, context)

            course = context.input_data
            assessment_schedule = semester_plan.get("assessment_schedule", []) if semester_plan else []

            assessments = []
            # Generate Quiz 1, Quiz 2, Midterm, Final
            assessment_types = [
                {"type": "quiz", "title": "Quiz 1", "marks": 20, "duration": 30, "modules": [0, 1]},
                {"type": "quiz", "title": "Quiz 2", "marks": 20, "duration": 30, "modules": [2, 3]},
                {"type": "midterm", "title": "Mid-Semester Examination", "marks": 50, "duration": 90, "modules": [0, 1, 2]},
                {"type": "final", "title": "End Semester Examination", "marks": 100, "duration": 180, "modules": "all"},
                {"type": "assignment", "title": "Assignment 1", "marks": 10, "modules": [0, 1]},
                {"type": "assignment", "title": "Assignment 2", "marks": 10, "modules": [3, 4]},
            ]

            for asmt in assessment_types:
                generated = await self._generate_assessment(course, curriculum, asmt)
                assessments.append(generated)

            # Build question bank
            question_bank = await self._generate_question_bank(course, curriculum)

            assessment_data = {
                "assessments": assessments,
                "question_bank": question_bank,
                "bloom_coverage": self._analyze_bloom_coverage(assessments),
            }

            await self.update_shared_memory("assessments", assessment_data, context)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=assessment_data,
                processing_time=time.time() - start_time,
                metadata={"assessments_generated": len(assessments)},
            )
        except Exception as e:
            self.logger.error(f"AssessmentAgent failed: {e}", exc_info=True)
            return self.format_error_result(str(e), time.time() - start_time, context)

    async def _generate_assessment(self, course: dict, curriculum: dict, asmt_config: dict) -> Dict[str, Any]:
        modules = curriculum.get("modules", [])
        clos = curriculum.get("course_learning_outcomes", [])

        if asmt_config["modules"] == "all":
            relevant_modules = modules
        else:
            relevant_modules = [modules[i] for i in asmt_config["modules"] if i < len(modules)]

        prompt = f"""Generate a {asmt_config['type']} paper for:

Course: {course.get('title')}
Assessment: {asmt_config['title']}
Total Marks: {asmt_config['marks']}
Duration: {asmt_config.get('duration', 60)} minutes
Modules Covered: {json.dumps([m.get('title') for m in relevant_modules])}
CLOs: {json.dumps([c.get('statement', '') for c in clos[:4]])}

Return ONLY valid JSON:
{{
  "assessment_title": "{asmt_config['title']}",
  "type": "{asmt_config['type']}",
  "total_marks": {asmt_config['marks']},
  "duration_minutes": {asmt_config.get('duration', 60)},
  "instructions": "General instructions for students",
  "sections": [
    {{
      "section": "A",
      "type": "Multiple Choice",
      "marks_per_question": 1,
      "questions": [
        {{
          "id": "Q1",
          "question": "Question text",
          "options": ["A) opt1", "B) opt2", "C) opt3", "D) opt4"],
          "answer": "A",
          "bloom_level": "remember",
          "clo": "CLO1"
        }}
      ]
    }},
    {{
      "section": "B",
      "type": "Short Answer",
      "marks_per_question": 5,
      "questions": [
        {{
          "id": "Q6",
          "question": "Question text",
          "model_answer": "Expected answer key",
          "bloom_level": "apply",
          "clo": "CLO2"
        }}
      ]
    }}
  ]
}}"""

        system_msg = "You are an expert assessment designer. Generate balanced, curriculum-aligned assessments. Respond with valid JSON only."
        response = await self.call_llm(prompt, system_msg, temperature=0.4, max_tokens=3000)

        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {"assessment_title": asmt_config["title"], "sections": []}

    async def _generate_question_bank(self, course: dict, curriculum: dict) -> Dict[str, Any]:
        """Generate a comprehensive question bank categorized by Bloom's level."""
        prompt = f"""Generate a comprehensive question bank for:

Course: {course.get('title')}
Modules: {json.dumps([m.get('title') for m in curriculum.get('modules', [])])}

Return ONLY valid JSON with 5 questions per Bloom's level per module (remember, understand, apply, analyze, evaluate, create):
{{
  "total_questions": 0,
  "by_bloom_level": {{
    "remember": [{{"question": "", "module": "", "marks": 1}}],
    "understand": [{{"question": "", "module": "", "marks": 2}}],
    "apply": [{{"question": "", "module": "", "marks": 5}}],
    "analyze": [{{"question": "", "module": "", "marks": 8}}],
    "evaluate": [{{"question": "", "module": "", "marks": 10}}],
    "create": [{{"question": "", "module": "", "marks": 15}}]
  }}
}}"""

        system_msg = "You are an expert educator. Create diverse question banks aligned with Bloom's taxonomy. Respond with valid JSON only."
        response = await self.call_llm(prompt, system_msg, temperature=0.5, max_tokens=3000)

        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {"total_questions": 0, "by_bloom_level": {}}

    def _analyze_bloom_coverage(self, assessments: List[dict]) -> Dict[str, int]:
        coverage = {}
        for asmt in assessments:
            for section in asmt.get("sections", []):
                for q in section.get("questions", []):
                    level = q.get("bloom_level", "understand")
                    coverage[level] = coverage.get(level, 0) + 1
        return coverage