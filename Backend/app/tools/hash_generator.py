import hashlib
import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path) as f:
        tool_config = yaml.safe_load(f)["MetadataTools"]["HashGenerator"]["config"]
except Exception:
    tool_config = {}

class HashGeneratorInput(BaseModel):
    """Input schema for HashGeneratorTool."""
    image_path: str = Field(..., description="The absolute path to the image file.")
    # Optionally, allow overriding the algorithm from config at runtime
    algorithm: str = Field(
        default=None, 
        description="Hashing algorithm to use (e.g., 'sha256', 'md5'). Overrides tool config if provided."
    )

class HashGeneratorTool(BaseTool):
    name: str = "Content-Based Hash Generator"
    description: str = "Generates a content-based hash (e.g., SHA256) for an image file, useful for deduplication."
    args_schema: Type[BaseModel] = HashGeneratorInput

    # Configuration from YAML/env
    default_algorithm: str = tool_config.get("algorithm", os.getenv("HASH_ALGORITHM", "sha256"))
    chunk_size: int = tool_config.get("chunk_size", int(os.getenv("HASH_CHUNK_SIZE", 4096)))

    def _run(self, image_path: str, algorithm: str = None) -> str:
        """
        Generates a content-based hash for the specified image file.

        Args:
            image_path: The absolute path to the image file.
            algorithm: The hashing algorithm to use. If None, uses the default from config.

        Returns:
            A JSON string containing the generated hash or an error message.
        """
        response_data: Dict[str, Any]
        chosen_algorithm = algorithm if algorithm else self.default_algorithm

        try:
            hasher = hashlib.new(chosen_algorithm)
            
            if not Path(image_path).is_file():
                response_data = {"success": False, "error": f"Image file not found at path: {image_path}"}
                return json.dumps(response_data)

            with open(image_path, 'rb') as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
            
            generated_hash = hasher.hexdigest()
            response_data = {
                "success": True, 
                "image_path": image_path,
                "algorithm": chosen_algorithm,
                "hash": generated_hash
            }

        except FileNotFoundError:
            response_data = {"success": False, "error": f"File not found: {image_path}"}
        except ValueError:
            # This can happen if hashlib.new() gets an unsupported algorithm
            response_data = {"success": False, "error": f"Unsupported hash algorithm: {chosen_algorithm}"}
        except Exception as e:
            response_data = {"success": False, "error": f"Failed to generate hash for {image_path}: {str(e)}"}
        
        return json.dumps(response_data)
