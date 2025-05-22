import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import math # For more complex calculations if needed, e.g. log

# Helper function to get nested dictionary values using dot notation
# Ensure this is identical to the one used in other tools or move to a shared utils module
def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    keys = path.split('.')
    current_level = data
    for key in keys:
        if isinstance(current_level, dict) and key in current_level:
            current_level = current_level[key]
        else:
            return default
    return current_level

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f)[\"TechnicalTools\"][\"NoiseAnalyzer\"][\"config\"]\nexcept Exception:
    tool_config = {}

class NoiseAnalysisInput(BaseModel):
    """Input schema for NoiseAnalyzerTool."""
    # Expects the `processed_data` dictionary from EXIFDecoderTool's output
    processed_metadata: Dict[str, Any] = Field(..., description="The processed metadata dictionary, typically from EXIFDecoderTool's output, containing keys like 'camera_info.model', 'technical_settings.iso', 'technical_settings.exposure_time'.")
    image_width_px: int = Field(..., description="Width of the image in pixels.")
    image_height_px: int = Field(..., description="Height of the image in pixels.")


class NoiseAnalyzerTool(BaseTool):
    name: str = "Image Noise Estimator"
    description: str = (
        "Estimates image noise levels based on processed metadata (ISO, exposure, camera model) "
        "and camera-specific noise profiles. The current model ('iso_variance') is a simplified estimation."
    )
    args_schema: Type[BaseModel] = NoiseAnalysisInput

    model_config: str = tool_config.get("model", os.getenv("NOISE_MODEL_CONFIG", "iso_variance"))
    
    _base_config_dir = Path(__file__).parent.parent / "config"
    camera_profiles_dir_config: Path = _base_config_dir / tool_config.get(
        "camera_profiles", 
        os.getenv("CAMERA_PROFILES_DIR", "camera_profiles_default")
    ).lstrip('/')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _load_camera_profile(self, camera_model: str) -> Dict[str, Any]:
        profile_data = {"profile_found": False, "profile_name": "default", "base_noise_raw": 0.1, "iso_gain_factor": 0.005, "exposure_scaling_factor": 0.5} 

        if not camera_model or camera_model.lower() == "unknown":
            profile_data["message"] = "Camera model unknown or not provided, using default noise profile."
            return profile_data

        sanitized_model_name = "".join(c if c.isalnum() or c in [' ', '-'] else '_' for c in camera_model).strip().lower()
        profile_filename = f"{sanitized_model_name}.json"
        profile_path = self.camera_profiles_dir_config / profile_filename
        
        profile_data["attempted_profile_path"] = str(profile_path)

        try:
            if profile_path.is_file():
                with open(profile_path, 'r') as f:
                    loaded_profile = json.load(f)
                    profile_data.update(loaded_profile)
                    profile_data["profile_found"] = True
                    profile_data["profile_name"] = sanitized_model_name
                    profile_data["message"] = f"Successfully loaded profile: {profile_filename}"
            else:
                profile_data["message"] = f"Camera profile '{profile_filename}' not found at '{profile_path}'. Using default noise profile."
        except json.JSONDecodeError:
            profile_data["message"] = f"Error decoding JSON from profile '{profile_filename}'. Using default noise profile."
            profile_data["profile_found"] = False
        except Exception as e:
            profile_data["message"] = f"Error loading profile '{profile_filename}': {str(e)}. Using default noise profile."
            profile_data["profile_found"] = False
            
        return profile_data

    def _calculate_noise_iso_variance(
        self, 
        iso: float, 
        exposure_time: float, 
        megapixels: float, 
        profile: Dict[str, Any]
    ) -> float:
        base_noise = float(profile.get("base_noise_raw", 0.1))
        iso_gain = float(profile.get("iso_gain_factor", 0.005))
        exposure_scale = float(profile.get("exposure_scaling_factor", 0.5))

        if exposure_time <= 0: exposure_time = 1e-6 
        if megapixels <=0: megapixels = 1e-6 # Avoid issues with zero megapixels

        # Simplified model: Noise increases with ISO, decreases with longer exposure and more megapixels (signal averaging)
        # This is illustrative and not physically accurate in a deep sense.
        noise_level = base_noise + (iso * iso_gain) / (math.log1p(exposure_time * 1000) * math.sqrt(megapixels))
        
        return max(0, min(100, noise_level * 10)) # Scaled and clamped

    def _run(self, processed_metadata: Dict[str, Any], image_width_px: int, image_height_px: int) -> str:
        response_data: Dict[str, Any]
        analysis_results = {}

        try:
            # Extract values from processed_metadata using dot-notation paths
            # Ensure these paths match the output of EXIFDecoderTool's _process_key_metadata
            camera_model_raw = str(get_nested_value(processed_metadata, "camera_info.model", "Unknown"))
            
            iso_raw = get_nested_value(processed_metadata, "technical_settings.iso", 100)
            iso = float(iso_raw[0] if isinstance(iso_raw, (list, tuple)) else iso_raw) # Handle if ISO is list

            # Assuming EXIFDecoderTool's _process_key_metadata stores exposure_time as a float under technical_settings
            exposure_time_raw = get_nested_value(processed_metadata, "technical_settings.exposure_time", 1/60.0)
            exposure_time = float(exposure_time_raw)


            analysis_results["input_camera_model"] = camera_model_raw
            analysis_results["input_iso"] = iso
            analysis_results["input_exposure_time_sec"] = exposure_time
            analysis_results["input_image_width_px"] = image_width_px
            analysis_results["input_image_height_px"] = image_height_px

            megapixels = (image_width_px * image_height_px) / 1_000_000.0
            analysis_results["calculated_megapixels"] = megapixels

            camera_profile_data = self._load_camera_profile(camera_model_raw)
            analysis_results["camera_profile_info"] = camera_profile_data

            if self.model_config == "iso_variance":
                noise_estimate = self._calculate_noise_iso_variance(iso, exposure_time, megapixels, camera_profile_data)
            else:
                noise_estimate = -1.0 
                analysis_results["calculation_model_error"] = f"Noise model '{self.model_config}' not implemented."
            
            analysis_results["estimated_noise_level"] = noise_estimate
            analysis_results["estimation_confidence"] = 0.75 if camera_profile_data.get("profile_found") else 0.40
            analysis_results["noise_model_used"] = self.model_config
            
            response_data = {"success": True, "analysis": analysis_results}

        except Exception as e:
            response_data = {
                "success": False, 
                "error": f"Failed during noise analysis: {str(e)}",
                "details": processed_metadata if 'processed_metadata' in locals() else "Metadata not available at point of error"
            }
            
        return json.dumps(response_data, default=str)
