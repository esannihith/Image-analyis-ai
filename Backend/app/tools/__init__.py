# app/tools/__init__.py
# Core Agent Tools
from .session_retrieval_tool import SessionRetrievalTool
# from .reference_resolver import ReferenceResolver # Removed
from .context_chain_builder import ContextChainBuilderTool # Renamed to ContextChainBuilderTool
from .metadata_validator import MetadataValidatorTool # Renamed to MetadataValidatorTool
from .format_normalizer import FormatNormalizerTool # Renamed to FormatNormalizerTool
# from .hash_generator import HashGeneratorTool # Removed

# Analysis Agent Tools
from .datetime_calculator import DateTimeCalculatorTool
from .solar_position_analyzer import SolarPositionAnalyzerTool
from .sequence_detector import SequenceDetectorTool
from .reverse_geocoder import ReverseGeocoderTool
from .landmark_matcher import LandmarkMatcherTool
from .distance_calculator import DistanceCalculatorTool
from .exif_decoder import EXIFDecoderTool
from .lens_database import LensDatabaseTool

# Specialized Agent Tools
from .matrix_comparator import MatrixComparatorTool 
from .visualization_creator import VisualizationCreatorTool 

# Control Agent Tools
from .suggestion_generator import SuggestionGeneratorTool

# Environmental Tools
from .weather_api_client_tool import WeatherAPIClientTool

# Consistent naming for __all__ using the actual class names being imported.
# Make sure these match the class names defined in the respective files.
__all__ = [
    # Core
    "SessionRetrievalTool",
    "ContextChainBuilderTool",
    # Metadata
    "MetadataValidatorTool",
    "FormatNormalizerTool",
    # Geospatial
    "ReverseGeocoderTool",
    "LandmarkMatcherTool",
    "DistanceCalculatorTool",
    # Technical
    "EXIFDecoderTool",
    "LensDatabaseTool",
    # Analytics
    "MatrixComparatorTool",
    # Response
    "VisualizationCreatorTool",
    # Error/Control
    "SuggestionGeneratorTool",
    # Temporal
    "DateTimeCalculatorTool",
    "SolarPositionAnalyzerTool",
    "SequenceDetectorTool",
    # Environmental
    "WeatherAPIClientTool"
]

# Note: I've also taken the liberty to:
# 1. Rename some imported classes in __init__.py to have "Tool" suffix if that's the convention
#    being followed (e.g., ContextChainBuilder -> ContextChainBuilderTool).
#    Please ensure the actual class names in your .py files match these imports.
#    I've updated the __all__ list accordingly.
# 2. Commented out other tools in the imports and __all__ that seemed like they were
#    previously planned but then superseded by LLM-based agents (like IntentParser) or explicitly removed.
#    Please verify these assumptions.