from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, task, crew
from langchain_groq import ChatGroq
import os
import yaml
from typing import Dict, Any

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

from app.tools.suggestion_generator import SuggestionGeneratorTool
from app.tools.weather_api_client_tool import WeatherAPIClientTool

# Import SessionStore if tools need it passed during instantiation
from app.store.session_store import SessionStore

from dotenv import load_dotenv
load_dotenv()

@CrewBase
class ImageAnalysisCrew():
    # Define paths to config YAMLs as strings
    # These paths are relative to the project root (where main.py is executed)
    # If main.py is in backend/, and config is in backend/app/config/, then:
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    def __init__(self):
        # Initialize LLM
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name=os.getenv("GROQ_MODEL_NAME", "llama3-8b-8192"), # Added fallback
            temperature=float(os.getenv("GROQ_TEMPERATURE", 0.2)), # Added fallback
        )
        # Initialize SessionStore
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            raise ValueError("REDIS_URL environment variable not set.")
        self.session_store = SessionStore(redis_url=redis_url)
        
        # Manual YAML loading is removed. CrewBase handles it using the paths above.
        # self.agents_yaml_config and self.tasks_yaml_config are removed.
        # self.agents_config and self.tasks_config will be populated by CrewAI.

    # --- Agent Definitions ---
    # Agent names (method names) MUST match the top-level keys in agents.yaml

    @agent
    def session_context_manager(self) -> Agent:
        config = self.agents_config['session_context_manager'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                SessionRetrievalTool(session_store=self.session_store),
                ContextChainBuilderTool(session_store=self.session_store)
            ],
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def metadata_digestor(self) -> Agent:
        config = self.agents_config['metadata_digestor'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                MetadataValidatorTool(),
                FormatNormalizerTool(),
            ],
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def temporal_specialist(self) -> Agent:
        config = self.agents_config['temporal_specialist'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                DateTimeCalculatorTool(),
                SolarPositionAnalyzerTool(),
                SequenceDetectorTool()
            ],
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def geospatial_engine(self) -> Agent:
        config = self.agents_config['geospatial_engine'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                ReverseGeocoderTool(),
                LandmarkMatcherTool(),
                DistanceCalculatorTool()
            ],
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def technical_analyzer(self) -> Agent:
        config = self.agents_config['technical_analyzer'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                EXIFDecoderTool(),
                LensDatabaseTool(session_store=self.session_store), # Added session_store if needed
            ],
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )
    
    @agent
    def environmental_analyst(self) -> Agent:
        config = self.agents_config['environmental_analyst'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[WeatherAPIClientTool()],
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def comparative_engine(self) -> Agent:
        config = self.agents_config['comparative_engine'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[MatrixComparatorTool()], # Add session_store if needed by MatrixComparatorTool
            llm=self.llm if config.get('llm') else None,
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def query_decomposer(self) -> Agent:
        config = self.agents_config['query_decomposer'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[], # As per your YAML
            llm=self.llm if config.get('llm') else None, # Ensure 'llm: true' is in YAML for this agent
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', True), # As per your YAML
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def response_synthesizer(self) -> Agent:
        config = self.agents_config['response_synthesizer'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[VisualizationCreatorTool()],
            llm=self.llm if config.get('llm') else None, # Ensure 'llm: true'
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )

    @agent
    def fallback_handler(self) -> Agent:
        config = self.agents_config['fallback_handler'] # type: ignore
        return Agent(
            role=config['role'],
            goal=config['goal'],
            backstory=config['backstory'],
            tools=[
                SuggestionGeneratorTool()
            ],
            llm=self.llm if config.get('llm') else None, # Ensure 'llm: true'
            verbose=config.get('verbose', True),
            allow_delegation=config.get('allow_delegation', False),
            max_iter=config.get('max_iter', 15)
        )
    
    # --- Task Definitions ---
    # Task names (method names) MUST match the top-level keys in tasks.yaml

    @task
    def process_new_user_query_and_resolve_context(self) -> Task:
        config = self.tasks_config['process_new_user_query_and_resolve_context'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.session_context_manager()
        )

    @task
    def extract_base_image_metadata(self) -> Task:
        config = self.tasks_config['extract_base_image_metadata'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.technical_analyzer()
        )

    @task
    def validate_and_normalize_metadata(self) -> Task:
        config = self.tasks_config['validate_and_normalize_metadata'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.metadata_digestor()
        )

    @task
    def analyze_image_temporal_properties(self) -> Task:
        config = self.tasks_config['analyze_image_temporal_properties'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.temporal_specialist()
        )

    @task
    def analyze_image_geospatial_properties(self) -> Task:
        config = self.tasks_config['analyze_image_geospatial_properties'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.geospatial_engine()
        )

    @task
    def analyze_image_technical_details(self) -> Task:
        config = self.tasks_config['analyze_image_technical_details'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.technical_analyzer()
        )

    @task
    def get_environmental_context(self) -> Task:
        config = self.tasks_config['get_environmental_context'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.environmental_analyst()
        )

    @task
    def compare_images_technical_metadata(self) -> Task:
        config = self.tasks_config['compare_images_technical_metadata'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.comparative_engine()
        )
    
    @task
    def compare_images_temporal_aspects(self) -> Task:
        config = self.tasks_config['compare_images_temporal_aspects'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.temporal_specialist()
        )

    @task
    def compare_images_geospatial_aspects(self) -> Task:
        config = self.tasks_config['compare_images_geospatial_aspects'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.geospatial_engine()
        )
        
    @task
    def detect_image_sequences(self) -> Task:
        config = self.tasks_config['detect_image_sequences'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.temporal_specialist()
        )

    @task
    def decompose_complex_query(self) -> Task:
        config = self.tasks_config['decompose_complex_query'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.query_decomposer()
        )

    @task
    def synthesize_response_from_analyses(self) -> Task:
        config = self.tasks_config['synthesize_response_from_analyses'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.response_synthesizer()
        )
    
    @task
    def handle_unresolved_query_or_error(self) -> Task:
        config = self.tasks_config['handle_unresolved_query_or_error'] # type: ignore
        return Task(
            description=config['description'],
            expected_output=config['expected_output'],
            agent=self.fallback_handler()
        )
        
    @crew
    def analysis_crew(self) -> Crew:
        # The self.agents and self.tasks lists are automatically populated 
        # by CrewAI when using the @agent and @task decorators.
        return Crew(
            agents=self.agents, 
            tasks=self.tasks,   
            process=Process.hierarchical, 
            manager_llm=self.llm, 
            verbose=2 
            # memory=True # Consider if you want memory for the crew
        )
    
    def run(self, inputs: Dict[str, Any]):
        """
        Executes the crew with the given inputs.
        """
        print(f"Crew run called with inputs: {inputs}") # Keep for debugging
        if not self.llm.groq_api_key: # Check if API key is actually set on the llm instance
            message = "LLM not configured: GROQ_API_KEY is missing or not accessible by ChatGroq."
            print(f"ERROR: {message}")
            # Depending on how you want to handle this, you might return an error dict
            # or raise an exception. For now, printing and returning error dict.
            return {"success": False, "error": message, "message": message}
        try:
            # Make sure the crew is instantiated correctly before kickoff
            crew_instance = self.analysis_crew()
            if not crew_instance.agents or not crew_instance.tasks:
                message = "Crew initialization failed: No agents or tasks were collected. Check YAML configurations and @agent/@task decorators."
                print(f"ERROR: {message}")
                return {"success": False, "error": message, "message": message}
            
            result = crew_instance.kickoff(inputs=inputs)
            return result
            
        except Exception as e:
            print(f"Error during crew execution: {e}") # Basic print
            import traceback
            traceback.print_exc() # Detailed traceback
            return {"success": False, "error": str(e), "message": f"An error occurred during crew execution: {e}"}

    # --- Placeholder methods for train/replay if you had them ---
    # def train(self): 
    #     print("Training not implemented for this crew.")

    # def replay(self):
    #     print("Replay not implemented for this crew.")
