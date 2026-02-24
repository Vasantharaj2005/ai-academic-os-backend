"""
Master Agent Orchestrator.
Coordinates the multi-agent workflow for course generation.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.agents.base_agent import AgentContext, AgentResult
from app.agents.curriculum_agent import CurriculumAgent
from app.agents.semester_agent import SemesterAgent
from app.agents.content_agent import ContentAgent
from app.agents.assessment_agent import AssessmentAgent
from app.agents.obe_agent import OBEAgent
from app.agents.analytics_agent import AnalyticsAgent
from app.core.memory import shared_memory
from app.services.ai.llm_service import llm_service
from app.services.ai.rag_service import rag_service
from app.utils.helpers import generate_workflow_id, now_iso
from app.utils.metrics import course_generations_total, course_generation_duration_seconds, active_generation_tasks

logger = logging.getLogger(__name__)


class WorkflowStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentOrchestrator:
    """
    Orchestrates the multi-agent pipeline for course generation.

    Workflow:
    1. CurriculumAgent  -> generates syllabus & CLOs
    2. SemesterAgent    -> creates 16-week plan (depends on 1)
    3. ContentAgent     -> generates lecture content (depends on 1)
    4. AssessmentAgent  -> creates assessments (depends on 1, 2)
    5. OBEAgent         -> CO-PO mapping (depends on 1, 4)
    6. AnalyticsAgent   -> insights & predictions (depends on 1, 4, 5)
    """

    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize all agents with shared services."""
        await llm_service.initialize()
        await rag_service.initialize()
        await shared_memory.connect()

        # Create agent instances
        agent_kwargs = dict(
            llm_service=llm_service,
            rag_service=rag_service,
            shared_memory=shared_memory,
        )
        self._agents = {
            "curriculum": CurriculumAgent(**agent_kwargs),
            "semester": SemesterAgent(**agent_kwargs),
            "content": ContentAgent(**agent_kwargs),
            "assessment": AssessmentAgent(**agent_kwargs),
            "obe": OBEAgent(**agent_kwargs),
            "analytics": AnalyticsAgent(**agent_kwargs),
        }
        self._initialized = True
        logger.info(f"AgentOrchestrator initialized with {len(self._agents)} agents")

    async def run_full_generation(
        self,
        course_data: Dict[str, Any],
        user_id: str,
        institution_id: str,
        mode: str = "full",
        workflow_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full course generation pipeline.
        Returns a comprehensive generation result.
        """
        if not self._initialized:
            await self.initialize()

        workflow_id = workflow_id or generate_workflow_id("wf")
        start_time = time.time()

        logger.info(f"Starting workflow {workflow_id} for course: {course_data.get('title')}")

        # Initialize workflow status
        status = {
            "workflow_id": workflow_id,
            "status": WorkflowStatus.RUNNING,
            "started_at": now_iso(),
            "agents": {},
            "progress": 0.0,
        }
        await shared_memory.set_workflow_status(workflow_id, status)
        active_generation_tasks.inc()

        # Build context
        context = AgentContext(
            workflow_id=workflow_id,
            course_id=course_data.get("id"),
            user_id=user_id,
            institution_id=institution_id,
            input_data=course_data,
        )

        results: Dict[str, AgentResult] = {}
        errors: List[str] = []

        try:
            # Phase 1: Curriculum (independent)
            await self._update_agent_status(workflow_id, "CurriculumAgent", "running")
            curr_result = await self._run_agent("curriculum", context)
            results["curriculum"] = curr_result
            await self._update_agent_status(workflow_id, "CurriculumAgent", "completed" if curr_result.success else "failed")
            await self._update_progress(workflow_id, 20)

            if not curr_result.success:
                errors.append(f"CurriculumAgent: {curr_result.error}")

            if mode == "curriculum_only":
                return self._build_result(workflow_id, results, errors, start_time)

            # Phase 2: Semester + Content in parallel (both depend on curriculum)
            await self._update_agent_status(workflow_id, "SemesterAgent", "running")
            await self._update_agent_status(workflow_id, "ContentAgent", "running")

            sem_task = asyncio.create_task(self._run_agent("semester", context))
            cnt_task = asyncio.create_task(self._run_agent("content", context))
            sem_result, cnt_result = await asyncio.gather(sem_task, cnt_task, return_exceptions=True)

            if isinstance(sem_result, Exception):
                sem_result = self._error_result("SemesterAgent", str(sem_result))
                errors.append(str(sem_result.error))
            if isinstance(cnt_result, Exception):
                cnt_result = self._error_result("ContentAgent", str(cnt_result))
                errors.append(str(cnt_result.error))

            results["semester"] = sem_result
            results["content"] = cnt_result
            await self._update_agent_status(workflow_id, "SemesterAgent", "completed" if sem_result.success else "failed")
            await self._update_agent_status(workflow_id, "ContentAgent", "completed" if cnt_result.success else "failed")
            await self._update_progress(workflow_id, 50)

            # Phase 3: Assessment (depends on curriculum + semester)
            await self._update_agent_status(workflow_id, "AssessmentAgent", "running")
            ass_result = await self._run_agent("assessment", context)
            results["assessment"] = ass_result
            await self._update_agent_status(workflow_id, "AssessmentAgent", "completed" if ass_result.success else "failed")
            await self._update_progress(workflow_id, 70)

            if mode == "assessments_only":
                return self._build_result(workflow_id, results, errors, start_time)

            # Phase 4: OBE (depends on curriculum + assessment)
            await self._update_agent_status(workflow_id, "OBEAgent", "running")
            obe_result = await self._run_agent("obe", context)
            results["obe"] = obe_result
            await self._update_agent_status(workflow_id, "OBEAgent", "completed" if obe_result.success else "failed")
            await self._update_progress(workflow_id, 85)

            if mode == "obe_only":
                return self._build_result(workflow_id, results, errors, start_time)

            # Phase 5: Analytics (depends on everything)
            await self._update_agent_status(workflow_id, "AnalyticsAgent", "running")
            anl_result = await self._run_agent("analytics", context)
            results["analytics"] = anl_result
            await self._update_agent_status(workflow_id, "AnalyticsAgent", "completed" if anl_result.success else "failed")
            await self._update_progress(workflow_id, 100)

            # Final result
            final_result = self._build_result(workflow_id, results, errors, start_time)

            # Update workflow status to completed
            status["status"] = WorkflowStatus.COMPLETED
            status["completed_at"] = now_iso()
            status["progress"] = 100.0
            await shared_memory.set_workflow_status(workflow_id, status)

            duration = time.time() - start_time
            course_generation_duration_seconds.observe(duration)
            course_generations_total.labels(status="success").inc()
            logger.info(f"Workflow {workflow_id} completed in {duration:.1f}s")

            return final_result

        except Exception as e:
            logger.error(f"Workflow {workflow_id} failed: {e}", exc_info=True)
            status["status"] = WorkflowStatus.FAILED
            status["error"] = str(e)
            await shared_memory.set_workflow_status(workflow_id, status)
            course_generations_total.labels(status="failure").inc()
            raise
        finally:
            active_generation_tasks.dec()

    async def _run_agent(self, agent_name: str, context: AgentContext) -> AgentResult:
        agent = self._agents.get(agent_name)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_name}")
        return await agent.process(context)

    def _error_result(self, agent_name: str, error: str) -> AgentResult:
        return AgentResult(
            agent_name=agent_name,
            success=False,
            data={},
            error=error,
            processing_time=0,
        )

    async def _update_agent_status(self, workflow_id: str, agent_name: str, status_str: str):
        status = await shared_memory.get_workflow_status(workflow_id) or {}
        agents = status.get("agents", {})
        agents[agent_name] = {
            "status": status_str,
            "updated_at": now_iso(),
        }
        status["agents"] = agents
        await shared_memory.set_workflow_status(workflow_id, status)

    async def _update_progress(self, workflow_id: str, progress: float):
        status = await shared_memory.get_workflow_status(workflow_id) or {}
        status["progress"] = progress
        await shared_memory.set_workflow_status(workflow_id, status)

    def _build_result(self, workflow_id: str, results: Dict[str, AgentResult], errors: List[str], start_time: float) -> Dict[str, Any]:
        return {
            "workflow_id": workflow_id,
            "success": len(errors) == 0,
            "generated_components": [k for k, v in results.items() if v.success],
            "curriculum": results.get("curriculum", AgentResult(agent_name="", success=False, data={}, processing_time=0)).data,
            "semester_plan": results.get("semester", AgentResult(agent_name="", success=False, data={}, processing_time=0)).data,
            "content": results.get("content", AgentResult(agent_name="", success=False, data={}, processing_time=0)).data,
            "assessments": results.get("assessment", AgentResult(agent_name="", success=False, data={}, processing_time=0)).data,
            "obe_report": results.get("obe", AgentResult(agent_name="", success=False, data={}, processing_time=0)).data,
            "analytics": results.get("analytics", AgentResult(agent_name="", success=False, data={}, processing_time=0)).data,
            "errors": errors,
            "duration_seconds": round(time.time() - start_time, 2),
        }

    async def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        return await shared_memory.get_workflow_status(workflow_id)

    async def close(self):
        await shared_memory.close()
        await llm_service.close()
        await rag_service.close()


# Singleton
orchestrator = AgentOrchestrator()