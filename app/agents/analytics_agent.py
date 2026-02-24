"""Analytics Agent - Predicts student performance and generates insights."""

import json
import time
from typing import Dict, Any

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult


class AnalyticsAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(agent_id="anl-001", agent_name="AnalyticsAgent", *args, **kwargs)

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        try:
            curriculum = await self.get_from_shared_memory("curriculum", context)
            obe_report = await self.get_from_shared_memory("obe_report", context)
            assessments = await self.get_from_shared_memory("assessments", context)

            course = context.input_data
            prompt = self._build_prompt(course, curriculum, obe_report, assessments)
            system_msg = (
                "You are an educational data analyst specializing in learning analytics and student performance prediction. "
                "Respond with valid JSON only."
            )

            response = await self.call_llm(prompt, system_msg, temperature=0.4, max_tokens=2500)
            analytics_data = self._parse_response(response)

            await self.update_shared_memory("analytics", analytics_data, context)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=analytics_data,
                processing_time=time.time() - start_time,
            )
        except Exception as e:
            self.logger.error(f"AnalyticsAgent failed: {e}", exc_info=True)
            return self.format_error_result(str(e), time.time() - start_time, context)

    def _build_prompt(self, course: dict, curriculum: dict, obe_report: dict, assessments: dict) -> str:
        bloom_dist = curriculum.get("bloom_analysis", {}).get("distribution", {}) if curriculum else {}
        compliance_score = obe_report.get("compliance_score", 0) if obe_report else 0

        return f"""Generate learning analytics insights for:

Course: {course.get('title')}
Program: {course.get('program')}
Semester: {course.get('semester')}
Credits: {course.get('credits')}
Bloom's Distribution: {json.dumps(bloom_dist)}
OBE Compliance Score: {compliance_score}/100

Return ONLY valid JSON:
{{
  "difficulty_analysis": {{
    "overall_difficulty": "moderate",
    "difficulty_score": 6.5,
    "challenging_topics": ["Topic 1", "Topic 2"],
    "prerequisite_gaps_risk": "medium"
  }},
  "student_performance_prediction": {{
    "expected_pass_rate": 78,
    "expected_distinction_rate": 15,
    "at_risk_factors": ["Heavy mathematical content", "Lab component"],
    "success_factors": ["Well-structured CLOs", "Progressive difficulty"]
  }},
  "teaching_effectiveness_indicators": {{
    "clo_attainability_score": 75,
    "assessment_alignment_score": 80,
    "bloom_coverage_score": 85,
    "overall_quality_score": {min(round(compliance_score * 0.8 + 20), 100)}
  }},
  "recommendations": {{
    "for_faculty": ["Recommendation 1", "Recommendation 2"],
    "for_students": ["Study tip 1", "Study tip 2"],
    "for_curriculum": ["Improvement 1"]
  }},
  "benchmarking": {{
    "similar_courses_avg_pass_rate": 72,
    "industry_alignment_score": 78,
    "research_relevance_score": 70
  }},
  "intervention_strategies": [
    {{
      "trigger": "Week 4 Quiz below 60%",
      "action": "Remedial session on foundational topics",
      "expected_impact": "15% improvement in mid-term scores"
    }}
  ]
}}"""

    def _parse_response(self, response: str) -> Dict[str, Any]:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {"difficulty_analysis": {}, "recommendations": {}}