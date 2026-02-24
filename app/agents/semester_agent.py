"""Semester Planning Agent - Creates 16-week semester schedule."""

import json
import time
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult


class SemesterAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(agent_id="sem-001", agent_name="SemesterAgent", *args, **kwargs)

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        try:
            # Get curriculum from shared memory
            curriculum = await self.get_from_shared_memory("curriculum", context)
            if not curriculum:
                return self.format_error_result("Curriculum not found in shared memory", time.time() - start_time, context)

            course = context.input_data
            prompt = self._build_prompt(course, curriculum)
            system_msg = (
                "You are an expert academic planner. Create detailed 16-week teaching plans "
                "aligned with the course curriculum. Respond with valid JSON only."
            )

            response = await self.call_llm(prompt, system_msg, temperature=0.3, max_tokens=4000)
            semester_plan = self._parse_response(response)

            await self.update_shared_memory("semester_plan", semester_plan, context)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=semester_plan,
                processing_time=time.time() - start_time,
                metadata={"weeks": 16},
            )
        except Exception as e:
            self.logger.error(f"SemesterAgent failed: {e}", exc_info=True)
            return self.format_error_result(str(e), time.time() - start_time, context)

    def _build_prompt(self, course: dict, curriculum: dict) -> str:
        modules = curriculum.get("modules", [])
        clos = [c.get("id", "") for c in curriculum.get("course_learning_outcomes", [])]

        return f"""Create a detailed 16-week semester teaching plan for:

Course: {course.get('title')}
Credits: {course.get('credits', 4)}
Modules: {json.dumps(modules, indent=2)}
CLOs: {', '.join(clos)}

Return ONLY valid JSON:
{{
  "semester_overview": {{
    "total_weeks": 16,
    "total_hours": {course.get('credits', 4) * 15},
    "teaching_hours_per_week": 3
  }},
  "weeks": [
    {{
      "week": 1,
      "module": "Module Title",
      "topics": ["Topic covered"],
      "clos_addressed": ["CLO1"],
      "teaching_methods": ["Lecture", "Discussion"],
      "activities": ["Problem solving exercise"],
      "assessment": null
    }}
  ],
  "mid_semester_break": 8,
  "assessment_schedule": [
    {{"week": 4, "type": "Quiz 1", "topics_covered": ["Module 1 topics"]}},
    {{"week": 8, "type": "Mid-term Exam", "topics_covered": ["Modules 1-3"]}},
    {{"week": 12, "type": "Quiz 2", "topics_covered": ["Modules 4-5"]}},
    {{"week": 16, "type": "End Semester Exam", "topics_covered": ["All modules"]}}
  ]
}}

Ensure:
- Week 8 or 9 includes mid-semester exam
- Week 16 is revision/exam prep
- Topics are distributed proportionally per module hours
- Activities vary across weeks (lectures, labs, seminars, case studies)
"""

    def _parse_response(self, response: str) -> Dict[str, Any]:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {"weeks": [], "assessment_schedule": []}