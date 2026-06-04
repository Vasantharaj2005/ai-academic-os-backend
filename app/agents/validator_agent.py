"""
Validator Agent.
Verifies the consistency, completeness, and quality of the generated course content.
"""

import logging
import json
import time
from typing import Any, Dict

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult
from app.services.ai.llm_service import LLMService
from app.services.ai.model_router import model_router
from app.core.memory import SharedMemory

logger = logging.getLogger(__name__)


class ValidatorAgent(BaseAgent):
    """
    Quality Assurance Agent.
    Runs at the end of the pipeline to validate alignment between:
    - Syllabus (Curriculum)
    - Semester Plan
    - Assessments
    - OBE Mapping
    """

    def __init__(self, llm_service: LLMService, rag_service: Any, shared_memory: SharedMemory):
        self.llm_service = llm_service
        self.shared_memory = shared_memory

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        logger.info(f"ValidatorAgent starting for workflow {context.workflow_id}")

        try:
            # 1. Fetch all generated data from shared memory
            data = await self.shared_memory.get_workflow_data(context.workflow_id)

            curriculum = data.get("curriculum")
            semester = data.get("semester_plan")
            assessments = data.get("assessments")
            obe = data.get("obe_report")
            content = data.get("content")

            if not curriculum:
                return AgentResult(
                    agent_name="ValidatorAgent",
                    success=False,
                    data={
                        "overall_score": 0,
                        "status": "FAIL",
                        "critical_issues": ["Missing curriculum data. Cannot perform validation."]
                    },
                    error="Missing curriculum data for validation",
                    processing_time=time.time() - start_time
                )

            # 2. Construct Validation Prompt
            prompt = self._build_prompt(curriculum, semester, assessments, obe, content)

            # 3. Call LLM
            provider, model, temp, max_tokens = model_router.route("validator")
            response_text = await self.llm_service.generate(
                prompt=prompt,
                provider=provider,
                model=model,
                temperature=temp,
                max_tokens=max_tokens,
                response_format="json"
            )

            # 4. Parse Result
            try:
                validation_report = json.loads(response_text)
            except json.JSONDecodeError:
                validation_report = {
                    "valid": False,
                    "score": 0,
                    "issues": ["Failed to parse validator output"],
                    "raw_output": response_text
                }

            # 5. Save and Return
            await self.shared_memory.set(f"{context.workflow_id}:validation", validation_report)

            return AgentResult(
                agent_name="ValidatorAgent",
                success=True,
                data=validation_report,
                processing_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"ValidatorAgent failed: {e}", exc_info=True)
            return AgentResult(
                agent_name="ValidatorAgent",
                success=False,
                data={
                    "overall_score": 0,
                    "status": "FAIL",
                    "critical_issues": [f"Validator Agent Error: {str(e)}"]
                },
                error=str(e),
                processing_time=time.time() - start_time
            )

    def _build_prompt(self, curriculum, semester, assessments, obe, content) -> str:
        # Create a compact summary of the content to avoid excessive token usage
        content_summary = "N/A"
        if content and "modules_content" in content:
            summary_parts = []
            for module_content in content["modules_content"][:3]: # Limit to first 3 modules for brevity
                title = module_content.get("module_title", "Untitled Module")
                concepts = ", ".join(module_content.get("key_concepts", []))
                num_notes = len(module_content.get("lecture_notes", []))
                summary_parts.append(f"Module '{title}': {num_notes} lecture notes covering concepts like '{concepts}'.")
            content_summary = " ".join(summary_parts)

        return f"""
        You are a meticulous Quality Assurance Lead for an AI Academic OS.
        Your task is to perform a deep analysis of the generated course package and identify inconsistencies, quality issues, and gaps.

        INPUT DATA:
        1. Curriculum: {json.dumps(curriculum)[:2000] if curriculum else "N/A"}
        2. Semester Plan: {json.dumps(semester)[:2000] if semester else "N/A"}
        3. Assessments: {json.dumps(assessments)[:3000] if assessments else "N/A"}
        4. OBE Mapping: {json.dumps(obe)[:1000] if obe else "N/A"}
        5. Content Summary: {content_summary}

        IN-DEPTH CHECKLIST:
        1.  **Structural Alignment**:
            - Do the modules in the Semester Plan exactly match the modules in the Curriculum?
            - Do the assessments in the Assessment Schedule (from Semester Plan) align with the generated Assessment papers?
        2.  **Content Quality & Duplication**:
            - Scan for placeholder text like "...", "insert here", "TBD", or overly generic phrases.
            - Identify if different modules have highly repetitive or duplicated `lecture_notes` content.
            - Check if questions in the `assessments` are just copy-pasted from `practice_problems` in the `content`.
        3.  **Pedagogical Consistency**:
            - Is there a logical progression of Bloom's level from CLOs -> Content -> Assessments? (e.g., an 'Analyze' CLO should have 'Analyze' level questions).
            - **OBE Verification**: Does the `assessment_co_mapping` in the OBE report accurately reflect the generated assessments?
            - Are all CLOs defined in the curriculum actually mapped in the OBE report?
        4.  **Completeness Check**:
            - Are all CLOs from the curriculum addressed in the semester plan and covered by at least one assessment?
            - Are there any empty sections in the generated data (e.g., empty `modules`, empty `questions`)?

        OUTPUT JSON FORMAT:
        {{
            "overall_score": <0-100, based on severity and number of issues>,
            "obe_compliance_percentage": <0-100, specific assessment of OBE alignment>,
            "status": "PASS" | "WARN" | "FAIL",
            "checks": [
                {{ "name": "Structural Alignment", "status": "PASS" | "FAIL", "comment": "Comment on module and assessment schedule alignment." }},
                {{ "name": "Content Quality", "status": "PASS" | "WARN" | "FAIL", "comment": "Comment on placeholders or generic content." }},
                {{ "name": "Content Duplication", "status": "PASS" | "WARN" | "FAIL", "comment": "Specifically mention any duplicated content found." }},
                {{ "name": "Pedagogical Consistency", "status": "PASS" | "FAIL", "comment": "Comment on Bloom's level flow and CO mapping." }},
                {{ "name": "Completeness", "status": "PASS" | "FAIL", "comment": "Comment on any missing mappings or empty sections." }}
            ],
            "critical_issues": [
                "List of high-severity issues found, e.g., 'Module 3 content is a duplicate of Module 1.'"
            ],
            "recommendations": [
                "Actionable recommendations, e.g., 'Regenerate ContentAgent for Module 3 to resolve duplication.'"
            ]
        }}
        """