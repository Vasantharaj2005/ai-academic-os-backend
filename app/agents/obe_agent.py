"""OBE Compliance Agent - CO-PO mapping and NBA/NAAC compliance."""

import json
import time
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult


class OBEAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(agent_id="obe-001", agent_name="OBEAgent", *args, **kwargs)

    # Program Outcomes (POs) as per NBA/AICTE
    PROGRAM_OUTCOMES = {
        "PO1": "Engineering knowledge",
        "PO2": "Problem analysis",
        "PO3": "Design/development of solutions",
        "PO4": "Conduct investigations of complex problems",
        "PO5": "Modern tool usage",
        "PO6": "The engineer and society",
        "PO7": "Environment and sustainability",
        "PO8": "Ethics",
        "PO9": "Individual and team work",
        "PO10": "Communication",
        "PO11": "Project management and finance",
        "PO12": "Life-long learning",
    }

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        try:
            curriculum = await self.get_from_shared_memory("curriculum", context)
            assessments = await self.get_from_shared_memory("assessments", context)

            if not curriculum:
                return self.format_error_result("Curriculum not found", time.time() - start_time, context)

            clos = curriculum.get("course_learning_outcomes", [])
            prompt = self._build_prompt(context.input_data, clos)
            system_msg = (
                "You are an OBE (Outcome-Based Education) compliance expert for NBA/NAAC accreditation. "
                "Generate detailed CO-PO mapping and compliance reports. Respond with valid JSON only."
            )

            response = await self.call_llm(prompt, system_msg, temperature=0.2, max_tokens=3000)
            obe_data = self._parse_response(response)

            # Add compliance scoring
            obe_data["compliance_score"] = self._calculate_compliance_score(obe_data, clos)
            obe_data["bloom_analysis"] = curriculum.get("bloom_analysis", {})

            await self.update_shared_memory("obe_report", obe_data, context)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=obe_data,
                processing_time=time.time() - start_time,
                metadata={"clos_mapped": len(clos)},
            )
        except Exception as e:
            self.logger.error(f"OBEAgent failed: {e}", exc_info=True)
            return self.format_error_result(str(e), time.time() - start_time, context)

    def _build_prompt(self, course: dict, clos: List[dict]) -> str:
        clo_list = json.dumps([{"id": c.get("id"), "statement": c.get("statement")} for c in clos], indent=2)
        po_list = json.dumps(self.PROGRAM_OUTCOMES, indent=2)

        return f"""Generate OBE compliance report for:

Course: {course.get('title')}
Program: {course.get('program', 'B.Tech')}

Course Learning Outcomes (CLOs/COs):
{clo_list}

Program Outcomes (POs):
{po_list}

Return ONLY valid JSON:
{{
  "co_po_mapping": {{
    "CLO1": {{"PO1": 3, "PO2": 2, "PO3": 1}},
    "CLO2": {{...}}
  }},
  "co_pso_mapping": {{
    "CLO1": {{"PSO1": 3, "PSO2": 2}},
    "CLO2": {{...}}
  }},
  "mapping_justification": {{
    "CLO1-PO1": "Justification text",
    "CLO1-PO2": "Justification text"
  }},
  "co_attainment_targets": {{
    "CLO1": {{"target": 70, "method": "Direct + Indirect"}},
    "CLO2": {{"target": 60, "method": "Direct"}}
  }},
  "po_attainment_contribution": {{
    "PO1": {{"contributing_cos": ["CLO1", "CLO3"], "average_level": 2.5}},
    "PO2": {{...}}
  }},
  "assessment_co_mapping": {{
    "Quiz 1": ["CLO1", "CLO2"],
    "Midterm": ["CLO1", "CLO2", "CLO3"],
    "End Semester": ["CLO1", "CLO2", "CLO3", "CLO4", "CLO5", "CLO6"]
  }},
  "recommendations": ["Recommendation 1", "Recommendation 2"],
  "nba_compliance_notes": "Compliance notes for NBA accreditation"
}}

Use scale 1-3 for mapping strength: 1=Low, 2=Medium, 3=High. 0 means no mapping.
"""

    def _parse_response(self, response: str) -> Dict[str, Any]:
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {"co_po_mapping": {}, "recommendations": []}

    def _calculate_compliance_score(self, obe_data: dict, clos: List[dict]) -> float:
        """Calculate overall OBE compliance score (0-100)."""
        score = 0
        max_score = 100

        # Check CO-PO mapping completeness (40 pts)
        co_po = obe_data.get("co_po_mapping", {})
        if co_po and len(co_po) >= len(clos):
            score += 40

        # Check attainment targets set (20 pts)
        if obe_data.get("co_attainment_targets"):
            score += 20

        # Check assessment mapping (20 pts)
        if obe_data.get("assessment_co_mapping"):
            score += 20

        # Check recommendations provided (10 pts)
        if obe_data.get("recommendations"):
            score += 10

        # Check NBA notes (10 pts)
        if obe_data.get("nba_compliance_notes"):
            score += 10

        return round(score, 1)