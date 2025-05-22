from crewai import Agent, Crew, Process, Task, CrewBase
from crewai.project import agent, crew, task
from langchain_groq import ChatGroq
from pathlib import Path
import os
import yaml
from typing import List, Dict, Any, Optional

# Import ONLY the tools we are keeping/adding
from app.tools.session_retrieval_tool import SessionRetrievalTool
from app.tools.context_chain_builder import ContextChainBuilderTool
from app.tools.metadata_validator import MetadataValidatorTool
from app.tools.format_normalizer import FormatNormalizerTool
from app.tools.datetime_calculator import DateTimeCalculatorTool
from app.tools.solar_position_analyzer import SolarPositionAnalyzerTool
from app.tools.sequence_detector import SequenceDetectorTool
from app.tools.reverse_geocoder import ReverseGeocoderTool
from app.tools.landmark_matcher import LandmarkMatcherTool
from app.tools.distance_calculator import DistanceCalculatorTool
from app.tools.exif_decoder import EXIFDecoderTool
from app.tools.lens_database import LensDatabaseTool
from app.tools.matrix_comparator import MatrixComparatorTool
from app.tools.visualization_creator import VisualizationCreatorTool
from app.tools.error_classifier import ErrorClassifierTool
from app.tools.suggestion_generator import SuggestionGeneratorTool
from app.tools.weather_api_client_tool import WeatherAPIClientTool

# Import SessionStore if tools need it passed during instantiation
from app.store.session_store import SessionStore

from dotenv import load_dotenv
load_dotenv()

def _get_config_item_by_name(config_list: List[Dict[str, Any]], name_to_find: str) -> Optional[Dict[str, Any]]:
    """Helper to find a specific config block by its 'name'."""
    if not isinstance(config_list, list):
        # print(f"Warning: Expected a list of configs, but got {type(config_list)}. Cannot find '{name_to_find}'.")
        return None
    for item in config_list:
        if isinstance(item, dict) and item.get("name") == name_to_find:
            return item
    # print(f"Warning: Config for '{name_to_find}' not found in the provided list.")
    return None

@CrewBase
class ImageAnalysisCrew():
    agents_config_path = Path(__file__).parent / "config/agents.yaml"
    tasks_config_path = Path(__file__).parent / "config/tasks.yaml"

    def __init__(self):
        # Load YAML configurations once
        with open(self.agents_config_path, 'r', encoding='utf-8') as f:
            self.agents_yaml_config = yaml.safe_load(f)
        with open(self.tasks_config_path, 'r', encoding='utf-8') as f:
            self.tasks_yaml_config = yaml.safe_load(f)

        # Initialize LLM
        # Ensure GROQ_API_KEY is set in your environment
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama3-8b-8192", # Or your preferred Groq model
            temperature=0.2, 
        )
        # Initialize SessionStore
        # Ensure REDIS_URL is set in your environment
        self.session_store = SessionStore()

    def _get_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Safely retrieves an agent's configuration by name."""
        for category_list in self.agents_yaml_config.values():
            if isinstance(category_list, list):
                config = _get_config_item_by_name(category_list, agent_name)
                if config:
                    return config
        raise ValueError(f"Agent configuration for '{agent_name}' not found in {self.agents_config_path}")

    def _get_task_config(self, task_name: str) -> Dict[str, Any]:
        """Safely retrieves a task's configuration by name."""
        tasks_list = self.tasks_yaml_config.get("tasks", [])
        config = _get_config_item_by_name(tasks_list, task_name)
        if config:
            return config
        raise ValueError(f"Task configuration for '{task_name}' not found in {self.tasks_config_path}")

    # --- Agent Definitions ---
    @agent
    def session_context_manager(self) -> Agent:
        config = self._get_agent_config("SessionContextManager")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                SessionRetrievalTool(session_store=self.session_store),
                ContextChainBuilderTool(session_store=self.session_store)
            ],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def metadata_digestor(self) -> Agent:
        config = self._get_agent_config("MetadataDigestor")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                MetadataValidatorTool(),
                FormatNormalizerTool(),
            ],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def temporal_specialist(self) -> Agent:
        config = self._get_agent_config("TemporalSpecialist")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                DateTimeCalculatorTool(),
                SolarPositionAnalyzerTool(),
                SequenceDetectorTool()
            ],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def geospatial_engine(self) -> Agent:
        config = self._get_agent_config("GeospatialEngine")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                ReverseGeocoderTool(),
                LandmarkMatcherTool(),
                DistanceCalculatorTool()
            ],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def technical_analyzer(self) -> Agent:
        config = self._get_agent_config("TechnicalAnalyzer")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                EXIFDecoderTool(),
                LensDatabaseTool(),
            ],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )
    
    @agent
    def environmental_analyst(self) -> Agent:
        config = self._get_agent_config("EnvironmentalAnalyst")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[WeatherAPIClientTool()],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def comparative_engine(self) -> Agent:
        config = self._get_agent_config("ComparativeEngine")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[MatrixComparatorTool()],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def query_decomposer(self) -> Agent:
        config = self._get_agent_config("QueryDecomposer")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', True),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def response_synthesizer(self) -> Agent:
        config = self._get_agent_config("ResponseSynthesizer")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[VisualizationCreatorTool()],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def fallback_handler(self) -> Agent:
        config = self._get_agent_config("FallbackHandler")
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                ErrorClassifierTool(),
                SuggestionGeneratorTool()
            ],
            llm=self.llm if config.get('llm', False) else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )
    
    # --- Task Definitions ---
    @task
    def process_new_user_query_and_resolve_context(self) -> Task:
        config = self._get_task_config("process_new_user_query_and_resolve_context")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.session_context_manager() # Call the agent method to get the instance
        )

    @task
    def extract_base_image_metadata(self) -> Task:
        config = self._get_task_config("extract_base_image_metadata")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.technical_analyzer() 
        )

    @task
    def validate_and_normalize_metadata(self) -> Task:
        config = self._get_task_config("validate_and_normalize_metadata")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.metadata_digestor()
        )

    @task
    def analyze_image_temporal_properties(self) -> Task:
        config = self._get_task_config("analyze_image_temporal_properties")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.temporal_specialist()
        )

    @task
    def analyze_image_geospatial_properties(self) -> Task:
        config = self._get_task_config("analyze_image_geospatial_properties")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.geospatial_engine()
        )

    @task
    def analyze_image_technical_details(self) -> Task:
        config = self._get_task_config("analyze_image_technical_details")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.technical_analyzer()
        )

    @task
    def get_environmental_context(self) -> Task:
        config = self._get_task_config("get_environmental_context")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.environmental_analyst()
        )

    @task
    def compare_images_technical_metadata(self) -> Task:
        config = self._get_task_config("compare_images_technical_metadata")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.comparative_engine()
        )
    
    @task
    def compare_images_temporal_aspects(self) -> Task:
        config = self._get_task_config("compare_images_temporal_aspects")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.temporal_specialist()
        )

    @task
    def compare_images_geospatial_aspects(self) -> Task:
        config = self._get_task_config("compare_images_geospatial_aspects")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.geospatial_engine()
        )
        
    @task
    def detect_image_sequences(self) -> Task:
        config = self._get_task_config("detect_image_sequences")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.temporal_specialist()
        )

    @task
    def decompose_complex_query(self) -> Task:
        config = self._get_task_config("decompose_complex_query")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.query_decomposer()
        )

    @task
    def synthesize_response_from_analyses(self) -> Task:
        config = self._get_task_config("synthesize_response_from_analyses")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.response_synthesizer()
        )
    
    @task
    def handle_unresolved_query_or_error(self) -> Task:
        config = self._get_task_config("handle_unresolved_query_or_error")
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.fallback_handler()
        )
        
    @crew
    def analysis_crew(self) -> Crew:
        return Crew(
            agents=self.agents,  # Auto-collected by @agent decorator
            tasks=self.tasks,    # Auto-collected by @task decorator
            process=Process.hierarchical, 
            manager_llm=self.llm, 
            verbose=2 
            # memory=True # Consider if you want memory for the crew; requires config if True
        )
    
    def run(self, inputs: Dict[str, Any]):
        """
        Executes the crew with the given inputs.
        Inputs should typically contain 'user_query' and 'session_id'.
        """
        print(f"Crew run called with inputs: {inputs}")
        if not self.llm:
            message = "LLM not configured. Cannot run the crew. Please check GROQ_API_KEY or LLM setup."
            print(f"ERROR: {message}")
            return {"success": False, "error": message, "message": message}
        try:
            result = self.analysis_crew().kickoff(inputs=inputs)
            return result
            
        except Exception as e:
            print(f"Error during crew execution: {e}")
            import traceback
            traceback.print_exc()
            # Consider a more structured error response or re-raising for the caller to handle.
            return {"success": False, "error": str(e), "message": "An error occurred during crew execution."}

    # --- Placeholder methods for train/replay if you had them ---
    # def train(self): 
    #     print("Training not implemented for this crew.")

    # def replay(self):
    #     print("Replay not implemented for this crew.")
