from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from app.tools.extraction_tool import ImageMetadataExtractionTool
from app.tools.metadata_cache_tool import MetadataCacheTool
from app.tools.prompt_enrichment_tool import PromptEnrichmentTool
from app.tools.filter_and_stats_tool import FilterAndStatsTool
from app.tools.comparison_tool import ComparisonTool
from app.tools.reverse_geocoding_tool import ReverseGeocodingTool
from app.tools.named_place_enrichment_tool import NamedPlaceEnrichmentTool
from app.tools.weather_data_tool import WeatherDataTool
from app.tools.csv_export_tool import CSVExportTool
from app.store.session_store import SessionStore
from pathlib import Path
from langchain_groq import ChatGroq
import os

@CrewBase
class ImageMetadataConversationalAssistantCrew():
    """ImageMetadataConversationalAssistant crew"""
    agents_config_path = Path('app/config/agents.yaml')
    tasks_config_path  = Path('app/config/tasks.yaml')

    llm = ChatGroq(
        api_key=os.environ.get("GROQ_API_KEY"),
        model = "groq/llama-3.3-70b-versatile",
        max_tokens=4096,
        temperature=0.7,
        )

    @agent
    def MetadataExtractionAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['MetadataExtractionAgent'],
            tools=[ImageMetadataExtractionTool()],
        )

    @agent
    def MetadataCacheAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['MetadataCacheAgent'],
            tools=[MetadataCacheTool()],
        )

    @agent
    def PromptEnrichmentAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['PromptEnrichmentAgent'],
            tools=[PromptEnrichmentTool()],
            llm=self.llm,
        )

    @agent
    def FilterAndStatsAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['FilterAndStatsAgent'],
            tools=[FilterAndStatsTool()],
        )

    @agent
    def ComparisonAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['ComparisonAgent'],
            tools=[ComparisonTool()],
        )

    @agent
    def ReverseGeocodingAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['ReverseGeocodingAgent'],
            tools=[ReverseGeocodingTool()],
        )

    @agent
    def NamedPlaceEnrichmentAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['NamedPlaceEnrichmentAgent'],
            tools=[NamedPlaceEnrichmentTool()],
        )

    @agent
    def WeatherDataAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['WeatherDataAgent'],
            tools=[WeatherDataTool()],
        )

    @agent
    def CSVExportAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['CSVExportAgent'],
            tools=[CSVExportTool()],
        )

    @agent
    def FallBackAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['FallBackAgent'],
        )

    @agent
    def CriticAgent(self) -> Agent:
        return Agent(
            config=self.agents_config['CriticAgent'],
            llm=self.llm,
        )

    @agent
    def OrchestrationManager(self) -> Agent:
        return Agent(
            config=self.agents_config['OrchestrationManager'],
            llm=self.llm,
        )


    @task
    def extract_metadata(self) -> Task:
        return Task(
            config=self.tasks_config['extract_metadata'],
            output_file='metadata.json',
        )

    @task
    def cache_session_metadata(self) -> Task:
        return Task(
            config=self.tasks_config['cache_session_metadata'],
        )

    @task
    def normalize_prompt(self) -> Task:
        return Task(
            config=self.tasks_config['normalize_prompt'],
        )

    @task
    def filter_statistics(self) -> Task:
        return Task(
            config=self.tasks_config['filter_statistics'],
        )

    @task
    def compare_metadata(self) -> Task:
        return Task(
            config=self.tasks_config['compare_metadata'],
        )

    @task
    def reverse_geocode_location(self) -> Task:
        return Task(
            config=self.tasks_config['reverse_geocode_location'],
        )

    @task
    def enrich_named_place(self) -> Task:
        return Task(
            config=self.tasks_config['enrich_named_place'],
        )

    @task
    def lookup_weather(self) -> Task:
        return Task(
            config=self.tasks_config['lookup_weather'],

        )

    @task
    def export_csv(self) -> Task:
        return Task(
            config=self.tasks_config['export_csv'],
        )

    @task
    def assemble_response(self) -> Task:
        return Task(
            config=self.tasks_config['assemble_response'],
            llm=self.llm,
        )

    @task
    def handle_fallback(self) -> Task:
        return Task(
            config=self.tasks_config['handle_fallback'],
            llm=self.llm,
        )

    @task
    def extract_datetime(self) -> Task:
        return Task(
            config=self.tasks_config['extract_datetime'],
        )

    @task
    def extract_location(self) -> Task:
        return Task(
            config=self.tasks_config['extract_location'],
        )

    # Removed detect_duplicates task as requested

    @crew
    def crew(self) -> Crew:
        """Creates the ImageMetadataConversationalAssistant crew"""
        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
        )

    def answer_question(self, session_id: str, image_id: str, question: str) -> str:
        """
        CrewAI conversational pipeline: normalize prompt, use Groq LLM for intent detection, run only relevant agents, assemble, and return answer.
        Returns standardized JSON: {"success": bool, "answer": str, "error": str|None}
        """
        import json
        try:
            # 1. Normalize prompt
            prompt_tool = self.PromptEnrichmentAgent().tools[0]
            prompt_result = prompt_tool._run(session_id, question, image_id)
            prompt_data = json.loads(prompt_result) if isinstance(prompt_result, str) else prompt_result
            if not prompt_data.get("success"):
                return json.dumps({"success": False, "answer": None, "error": prompt_data.get("error", "Prompt normalization failed.")})
            normalized_query = prompt_data.get("normalized_query", question)
            resolved_image_ids = prompt_data.get("resolved_image_ids", [image_id])

            # 2. Use Groq LLM to classify intent(s)
            llm_prompt = (
                "You are an intent classifier for an image metadata assistant. "
                "Given the user question: '" + normalized_query + "', "
                "return a JSON list of which of these actions should be taken: "
                "['compare', 'geocode', 'place', 'weather', 'stats']. "
                "Only include actions that are relevant."
            )
            llm_response = self.llm(llm_prompt)
            try:
                # Try to extract the list from the LLM response
                import re
                import ast
                match = re.search(r'\[(.*?)\]', llm_response, re.DOTALL)
                if match:
                    actions = ast.literal_eval('[' + match.group(1) + ']')
                    actions = [a.strip().strip('"\'') for a in actions]
                else:
                    actions = []
            except Exception:
                actions = []
            context = {
                "normalized_query": normalized_query,
                "resolved_image_ids": resolved_image_ids,
                "session_id": session_id,
                "image_id": image_id,
                "question": question,
                "llm_intents": actions
            }
            # 3. Run only the agents/tools matching the LLM-detected intents
            if "compare" in actions:
                comparison_tool = self.ComparisonAgent().tools[0]
                comparison_result = comparison_tool._run(session_id, resolved_image_ids)
                context["comparison"] = json.loads(comparison_result) if isinstance(comparison_result, str) else comparison_result
            if "geocode" in actions:
                geocode_tool = self.ReverseGeocodingAgent().tools[0]
                geocode_result = geocode_tool._run(session_id, resolved_image_ids)
                context["geocode"] = json.loads(geocode_result) if isinstance(geocode_result, str) else geocode_result
            if "place" in actions:
                place_tool = self.NamedPlaceEnrichmentAgent().tools[0]
                place_result = place_tool._run(session_id, resolved_image_ids)
                context["place"] = json.loads(place_result) if isinstance(place_result, str) else place_result
            if "weather" in actions:
                weather_tool = self.WeatherDataAgent().tools[0]
                weather_result = weather_tool._run(session_id, resolved_image_ids)
                context["weather"] = json.loads(weather_result) if isinstance(weather_result, str) else weather_result
            if "stats" in actions:
                filter_tool = self.FilterAndStatsAgent().tools[0]
                filter_result = filter_tool._run(session_id, resolved_image_ids)
                context["filter"] = json.loads(filter_result) if isinstance(filter_result, str) else filter_result

            # 4. Fallback: If no actions detected, use FallBackAgent
            if not actions:
                fallback_agent = self.FallBackAgent()
                fallback_task = self.handle_fallback()
                fallback_context = {
                    "normalized_query": normalized_query,
                    "session_id": session_id,
                    "image_id": image_id,
                    "question": question
                }
                fallback_result = fallback_agent.run(fallback_task, context=fallback_context)
                fallback_data = json.loads(fallback_result) if isinstance(fallback_result, str) else fallback_result
                if not fallback_data.get("success"):
                    return json.dumps({"success": False, "answer": None, "error": fallback_data.get("error", "Fallback failed.")})
                return json.dumps({
                    "success": True,
                    "answer": fallback_data.get("fallback_message"),
                    "error": None
                })

            # 5. Assemble final response using OrchestrationManager
            orchestration_agent = self.OrchestrationManager()
            assemble_task = self.assemble_response()
            final_result = orchestration_agent.run(
                assemble_task,
                context=context
            )
            final_data = json.loads(final_result) if isinstance(final_result, str) else final_result
            if not final_data.get("success"):
                return json.dumps({"success": False, "answer": None, "error": final_data.get("error", "Orchestration failed.")})
            return json.dumps({
                "success": True,
                "answer": final_data.get("final_response"),
                "error": None
            })
        except Exception as e:
            return json.dumps({"success": False, "answer": None, "error": str(e)})
