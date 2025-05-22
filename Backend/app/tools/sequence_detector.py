import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
from datetime import datetime, timezone, timedelta

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f).get("TemporalTools", {}).get("SequenceDetector", {}).get("config", {})
except Exception:
    tool_config = {}

class ImageTimestampInfo(BaseModel):
    """Represents an image and its timestamp for sequence detection."""
    image_identifier: str = Field(..., description="A unique identifier for the image (e.g., hash, filename, ID).")
    utc_timestamp_iso: str = Field(..., description="UTC timestamp in ISO8601 format (e.g., '2023-10-27T10:30:00Z').")
    # Optional: other metadata that might be useful to return with the sequence
    extra_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional dictionary for other relevant image data.")

class SequenceDetectorInput(BaseModel):
    """Input schema for SequenceDetectorTool."""
    images: List[ImageTimestampInfo] = Field(..., description="A list of images, each with an identifier and a UTC ISO8601 timestamp.")
    # Allow overriding config at runtime if needed
    max_gap_seconds_override: Optional[int] = Field(None, description="Override default max time gap (seconds) between images in a sequence.")
    min_sequence_length_override: Optional[int] = Field(None, description="Override default minimum number of images for a sequence.")


class DetectedSequence(BaseModel):
    """Represents a detected temporal sequence of images."""
    sequence_id: str
    image_count: int
    start_time_utc: str
    end_time_utc: str
    duration_seconds: float
    average_gap_seconds: Optional[float] = None
    image_identifiers: List[str]
    # To include full image info if needed:
    # images_in_sequence: List[ImageTimestampInfo] 


class SequenceDetectorTool(BaseTool):
    name: str = "Temporal Image Sequence Detector"
    description: str = (
        "Analyzes a list of images with timestamps to identify temporal sequences "
        "(e.g., bursts, time-lapses) based on configurable time gaps and minimum sequence length."
    )
    args_schema: Type[BaseModel] = SequenceDetectorInput

    # Configuration from YAML/env
    default_max_gap_seconds: int = tool_config.get("max_gap", int(os.getenv("SEQDET_MAX_GAP_SEC", 3600)))
    default_min_sequence_length: int = tool_config.get("min_sequence_length", int(os.getenv("SEQDET_MIN_LEN", 3)))

    def _parse_utc_iso_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        """Parses an ISO8601 UTC string to a datetime object."""
        try:
            # Ensure 'Z' for UTC or handle offset properly if present (though input spec says UTC ISO)
            if timestamp_str.endswith('Z'):
                dt_obj = datetime.fromisoformat(timestamp_str[:-1] + '+00:00')
            elif '+' in timestamp_str[10:] or '-' in timestamp_str[10:]: # Has offset
                 dt_obj = datetime.fromisoformat(timestamp_str)
            else: # Naive or missing Z, assume UTC as per input spec
                dt_obj = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
            
            return dt_obj.astimezone(timezone.utc) # Ensure it's UTC
        except ValueError:
            return None

    def _run(self, images: List[Dict[str, Any]], 
             max_gap_seconds_override: Optional[int] = None, 
             min_sequence_length_override: Optional[int] = None) -> str:
        
        response: Dict[str, Any] = {"success": False, "sequences_found": [], "total_images_processed": 0}

        # Validate input using Pydantic models (CrewAI usually handles this via args_schema,
        # but if _run is called directly, manual validation is good)
        try:
            input_data = SequenceDetectorInput(
                images=[ImageTimestampInfo(**img) for img in images],
                max_gap_seconds_override=max_gap_seconds_override,
                min_sequence_length_override=min_sequence_length_override
            )
            valid_images_input = input_data.images
        except Exception as pydantic_error: # Catches Pydantic ValidationError
            response["error"] = f"Invalid input data structure: {str(pydantic_error)}"
            return json.dumps(response)

        if not valid_images_input:
            response["error"] = "No images provided for sequence detection."
            response["success"] = True # No error, just no data
            return json.dumps(response)

        max_gap = timedelta(seconds=max_gap_seconds_override if max_gap_seconds_override is not None else self.default_max_gap_seconds)
        min_len = min_sequence_length_override if min_sequence_length_override is not None else self.default_min_sequence_length
        
        response["config_params"] = {"max_gap_seconds": max_gap.total_seconds(), "min_sequence_length": min_len}
        response["total_images_processed"] = len(valid_images_input)

        # Parse timestamps and filter out any images with unparseable timestamps
        parsed_images: List[Tuple[datetime, ImageTimestampInfo]] = []
        parsing_errors: List[str] = []
        for img_info in valid_images_input:
            dt_obj = self._parse_utc_iso_timestamp(img_info.utc_timestamp_iso)
            if dt_obj:
                parsed_images.append((dt_obj, img_info))
            else:
                parsing_errors.append(f"Could not parse timestamp for image: {img_info.image_identifier}")
        
        if parsing_errors:
            response["warnings"] = parsing_errors
        
        if not parsed_images:
            response["error"] = "No images with valid timestamps found."
            if not parsing_errors: # If no images were provided initially vs all failed parsing
                 response["success"] = True 
            return json.dumps(response)

        # Sort images by timestamp
        parsed_images.sort(key=lambda x: x[0])

        sequences: List[Dict[str, Any]] = []
        current_sequence_images: List[ImageTimestampInfo] = []
        current_sequence_timestamps: List[datetime] = []
        
        seq_counter = 0

        for i in range(len(parsed_images)):
            dt_obj, img_info = parsed_images[i]

            if not current_sequence_images: # Start of a new potential sequence
                current_sequence_images.append(img_info)
                current_sequence_timestamps.append(dt_obj)
            else:
                # Check gap with the last image in the current sequence
                time_diff = dt_obj - current_sequence_timestamps[-1]
                if time_diff <= max_gap:
                    current_sequence_images.append(img_info)
                    current_sequence_timestamps.append(dt_obj)
                else:
                    # Gap is too large, current sequence (if valid) ends
                    if len(current_sequence_images) >= min_len:
                        seq_counter += 1
                        total_duration = (current_sequence_timestamps[-1] - current_sequence_timestamps[0]).total_seconds()
                        avg_gap = None
                        if len(current_sequence_timestamps) > 1:
                            avg_gap = total_duration / (len(current_sequence_timestamps) -1)

                        seq_data = DetectedSequence(
                            sequence_id=f"seq_{seq_counter}",
                            image_count=len(current_sequence_images),
                            start_time_utc=current_sequence_timestamps[0].isoformat().replace('+00:00', 'Z'),
                            end_time_utc=current_sequence_timestamps[-1].isoformat().replace('+00:00', 'Z'),
                            duration_seconds=total_duration,
                            average_gap_seconds=round(avg_gap, 2) if avg_gap is not None else None,
                            image_identifiers=[img.image_identifier for img in current_sequence_images]
                            # images_in_sequence=current_sequence_images # If full info is needed
                        )
                        sequences.append(seq_data.model_dump())
                    
                    # Start a new sequence with the current image
                    current_sequence_images = [img_info]
                    current_sequence_timestamps = [dt_obj]
        
        # Check the last running sequence after the loop
        if len(current_sequence_images) >= min_len:
            seq_counter += 1
            total_duration = (current_sequence_timestamps[-1] - current_sequence_timestamps[0]).total_seconds()
            avg_gap = None
            if len(current_sequence_timestamps) > 1:
                avg_gap = total_duration / (len(current_sequence_timestamps) -1)

            seq_data = DetectedSequence(
                sequence_id=f"seq_{seq_counter}",
                image_count=len(current_sequence_images),
                start_time_utc=current_sequence_timestamps[0].isoformat().replace('+00:00', 'Z'),
                end_time_utc=current_sequence_timestamps[-1].isoformat().replace('+00:00', 'Z'),
                duration_seconds=total_duration,
                average_gap_seconds=round(avg_gap,2) if avg_gap is not None else None,
                image_identifiers=[img.image_identifier for img in current_sequence_images]
            )
            sequences.append(seq_data.model_dump())

        response["sequences_found"] = sequences
        response["success"] = True
        
        return json.dumps(response, default=str)
