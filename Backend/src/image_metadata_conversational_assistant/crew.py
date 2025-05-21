from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from image_metadata_conversational_assistant.tools import *
from pathlib import Path
from groq import GroqLLM
import os

@CrewBase
class ImageMetadataConversationalAssistantCrew():
    """ImageMetadataConversationalAssistant crew"""
    agents_config_path = Path('agents_config.yaml')
    tasks_config_path  = Path('tasks_config.yaml')

    llm = GroqLLM(
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


    @crew
    def crew(self) -> Crew:
        """Creates the ImageMetadataConversationalAssistant crew"""
        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
        )
