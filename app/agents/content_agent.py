"""Content & PPT Generation Agent - Generates lecture content and slide outlines."""

import json
import time
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent, AgentContext, AgentResult


class ContentAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(agent_id="cnt-001", agent_name="ContentAgent", *args, **kwargs)

    async def process(self, context: AgentContext) -> AgentResult:
        start_time = time.time()
        try:
            curriculum = await self.get_from_shared_memory("curriculum", context)
            if not curriculum:
                return self.format_error_result("Curriculum not found", time.time() - start_time, context)

            course = context.input_data
            modules = curriculum.get("modules", [])

            # Generate content for each module
            all_content = []
            for module in modules:
                module_content = await self._generate_module_content(course, module, curriculum)
                all_content.append(module_content)

            content_data = {
                "course_title": course.get("title"),
                "total_modules": len(modules),
                "modules_content": all_content,
                "slide_deck_outline": self._build_slide_deck_outline(course, all_content),
            }

            await self.update_shared_memory("content", content_data, context)

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                data=content_data,
                processing_time=time.time() - start_time,
                metadata={"modules_processed": len(modules)},
            )
        except Exception as e:
            self.logger.error(f"ContentAgent failed: {e}", exc_info=True)
            return self.format_error_result(str(e), time.time() - start_time, context)

    async def _generate_module_content(self, course: dict, module: dict, curriculum: dict) -> Dict[str, Any]:
        rag_docs = await self.enhance_with_rag(
            f"{module.get('title')} {course.get('title')} lecture notes",
            AgentContext(
                workflow_id="temp",
                user_id="system",
                institution_id=course.get("institution_id", "default"),
                input_data={},
            ),
            top_k=2,
        )

        prompt = f"""Generate detailed lecture content for this module:

Course: {course.get('title')}
Module: {module.get('title')}
Topics: {', '.join(module.get('topics', []))}
Hours: {module.get('hours', 6)}

Return ONLY valid JSON:
{{
  "module_title": "{module.get('title')}",
  "key_concepts": ["concept1", "concept2"],
  "lecture_notes": [
    {{
      "topic": "Topic Name",
      "content": "Detailed explanation...",
      "examples": ["Example 1"],
      "key_points": ["Point 1"],
      "duration_minutes": 45
    }}
  ],
  "slide_outline": [
    {{
      "slide_number": 1,
      "title": "Slide Title",
      "bullet_points": ["Point 1", "Point 2"],
      "speaker_notes": "Notes for presenter",
      "visual_suggestion": "Diagram/chart type"
    }}
  ],
  "practice_problems": ["Problem 1", "Problem 2"],
  "discussion_questions": ["Question 1"],
  "further_reading": ["Resource 1"]
}}
"""
        system_msg = "You are an expert educator. Generate structured, engaging lecture content. Respond with valid JSON only."
        response = await self.call_llm(prompt, system_msg, temperature=0.5, max_tokens=3000)

        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {"module_title": module.get("title"), "key_concepts": [], "lecture_notes": []}

    def _build_slide_deck_outline(self, course: dict, modules_content: List[dict]) -> List[Dict]:
        slides = [
            {
                "slide_number": 1,
                "type": "title",
                "title": course.get("title", "Course Title"),
                "subtitle": f"{course.get('program')} - Semester {course.get('semester')}",
            }
        ]
        slide_num = 2
        for module in modules_content:
            slides.append({
                "slide_number": slide_num,
                "type": "module_intro",
                "title": module.get("module_title", ""),
                "bullet_points": module.get("key_concepts", [])[:5],
            })
            slide_num += 1
            for note in module.get("lecture_notes", []):
                for outline_slide in module.get("slide_outline", []):
                    slides.append({**outline_slide, "slide_number": slide_num})
                    slide_num += 1
                    if slide_num > 150:
                        break

        return slides