import yaml
from pathlib import Path
import os
from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import math

# Attempt to import pandas and numpy
try:
    import pandas as pd
    import numpy as np
    PANDAS_NUMPY_AVAILABLE = True
except ImportError:
    PANDAS_NUMPY_AVAILABLE = False
    pd = None # Placeholder
    np = None # Placeholder

# Load configuration from tools.yaml
try:
    config_path = Path(__file__).parent.parent / "config" / "tools.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        tool_config = yaml.safe_load(f).get("AnalyticsTools", {}).get("MatrixComparator", {}).get("config", {})
except Exception:
    tool_config = {}

DEFAULT_COMPARISON_FIELDS = ["technical_settings.iso", "technical_settings.aperture", "technical_settings.shutter_speed_value"]
DEFAULT_SCORING_METHOD = "weighted_deviation_from_mean"

class MatrixComparatorInput(BaseModel):
    """Input schema for MatrixComparatorTool."""
    images_metadata: List[Dict[str, Any]] = Field(..., description="A list of metadata dictionaries. Each item should have an ID field and a 'processed_data' dictionary containing the fields to compare.")
    id_field: str = Field(default="image_hash", description="Field in the root of each metadata item used as a unique ID (e.g., 'image_hash').")
    fields_to_compare: Optional[List[str]] = Field(None, description="Optional: List of metadata field keys within 'processed_data' (e.g., 'technical_settings.iso'). Overrides config.")
    custom_weights: Optional[Dict[str, float]] = Field(None, description="Optional: Dictionary of weights for fields for scoring (e.g., {'technical_settings.iso': 0.4}).")

class MatrixComparatorTool(BaseTool):
    name: str = "Image Metadata Matrix Comparator (Pandas/NumPy)"
    description: str = (
        "Compares multiple images across specified technical metadata parameters from 'processed_data', "
        "using Pandas and NumPy for efficient matrix generation and calculation of a weighted deviation score "
        "for each image relative to the average of the set."
    )
    args_schema: Type[BaseModel] = MatrixComparatorInput

    _comparison_fields_config: List[str]
    _scoring_method_config: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not PANDAS_NUMPY_AVAILABLE:
            # This tool is heavily reliant on these libraries.
            # In a real scenario, you might raise an error or have a pure Python fallback.
            # For this exercise, we'll assume the caller handles this.
            print("WARNING: Pandas and NumPy are not available. MatrixComparatorTool may not function correctly.")
        self._comparison_fields_config = tool_config.get("comparison_fields", DEFAULT_COMPARISON_FIELDS)
        self._scoring_method_config = tool_config.get("scoring_method", DEFAULT_SCORING_METHOD)

    def _get_nested_value(self, data: Dict[str, Any], path: str, default: Any = np.nan if PANDAS_NUMPY_AVAILABLE else "N/A") -> Any:
        # Helper to extract nested values, compatible with Pandas (returns np.nan for missing)
        keys = path.split('.')
        current_level = data
        for key in keys:
            if isinstance(current_level, dict) and key in current_level:
                current_level = current_level[key]
            else:
                return default
        return current_level

    def _run(
        self,
        images_metadata: List[Dict[str, Any]],
        id_field: str = "image_hash",
        fields_to_compare: Optional[List[str]] = None,
        custom_weights: Optional[Dict[str, float]] = None
    ) -> str:
        logs: List[str] = []

        if not PANDAS_NUMPY_AVAILABLE:
            return json.dumps({"success": False, "error": "Pandas and NumPy libraries are required but not available.", "comparison_matrix": [], "image_scores": [], "summary": "", "logs": ["Tool disabled due to missing dependencies."]})

        if not images_metadata:
            return json.dumps({"success": False, "error": "No image metadata provided.", "comparison_matrix": [], "image_scores": [], "summary": "", "logs": logs})

        actual_fields_to_compare = fields_to_compare if fields_to_compare else self._comparison_fields_config
        logs.append(f"Comparing based on fields: {actual_fields_to_compare}")

        # 1. Prepare data for DataFrame
        data_for_df = []
        for i, meta_item_root in enumerate(images_metadata):
            image_id = meta_item_root.get(id_field, f"Image_{i+1}")
            # Assume comparable fields are within 'processed_data' or at root of meta_item_root
            # if 'processed_data' itself is the path start.
            source_dict = meta_item_root.get("processed_data", meta_item_root)
            
            record = {id_field: image_id}
            for field_path in actual_fields_to_compare:
                record[field_path] = self._get_nested_value(source_dict, field_path)
            data_for_df.append(record)

        df = pd.DataFrame(data_for_df)
        if id_field in df.columns:
            df = df.set_index(id_field)
        else:
            logs.append(f"Warning: id_field '{id_field}' not found in columns. Using default index.")
            # return json.dumps error or handle gracefully

        # Convert fields to compare to numeric, coercing errors to NaN
        for field in actual_fields_to_compare:
            if field in df.columns:
                df[field] = pd.to_numeric(df[field], errors='coerce')
            else:
                logs.append(f"Warning: Field '{field}' not found in prepared data. It will be ignored.")
                # Add NaN column to prevent errors later if it was expected
                df[field] = np.nan


        # Create the comparison matrix for output (original values)
        # Ensure only requested and available fields are in matrix
        display_fields = [f for f in actual_fields_to_compare if f in df.columns]
        comparison_matrix_df = df[display_fields].copy()
        # Replace NaNs with "N/A" for display if desired, or keep as null for JSON
        comparison_matrix = comparison_matrix_df.replace({np.nan: "N/A"}).reset_index().to_dict(orient='records')


        # --- Weighted Scoring Logic (Deviation from Mean) ---
        image_scores_list: List[Dict[str, Any]] = []
        
        if self._scoring_method_config == "weighted_deviation_from_mean" and len(df) >= 2:
            field_stats: Dict[str, Dict[str, Optional[float]]] = {}
            scorable_fields: List[str] = []

            for field in display_fields: # Iterate only over fields present in DataFrame
                series = df[field].dropna() # Work with non-NaN values for stats
                if not series.empty:
                    min_v, max_v = series.min(), series.max()
                    avg_v = series.mean()
                    range_span = max_v - min_v
                    field_stats[field] = {
                        "min": min_v, "max": max_v, "avg": avg_v,
                        "range_span": range_span if range_span > 0 else 1.0 # Avoid div by zero later
                    }
                    scorable_fields.append(field)
                else:
                    logs.append(f"Field '{field}' has no numerical values or is all NaN, excluded from scoring.")
            
            if not scorable_fields:
                logs.append("No fields were scorable for weighted comparison.")
            else:
                active_weights: Dict[str, float] = {}
                default_weight = 1.0 / len(scorable_fields)
                for field in scorable_fields:
                    active_weights[field] = (custom_weights.get(field, default_weight)
                                             if custom_weights else default_weight)
                
                weight_sum = sum(active_weights.values())
                if weight_sum > 0 and not math.isclose(weight_sum, 1.0):
                    logs.append(f"Normalizing weights (sum was {weight_sum:.4f}).")
                    for field in active_weights: active_weights[field] /= weight_sum
                
                # Initialize series for calculations
                total_weighted_norm_dev = pd.Series(0.0, index=df.index)
                sum_of_weights_applied = pd.Series(0.0, index=df.index)

                for field in scorable_fields:
                    stats = field_stats[field]
                    # Calculate absolute deviation from the mean for the current field
                    abs_deviation = (df[field] - stats["avg"]).abs()
                    # Normalize this deviation by the field's range
                    norm_deviation = abs_deviation / stats["range_span"]
                    
                    # Apply weight and add to total; only for non-NaN original values
                    # df[field].notna() gives a boolean Series to select valid entries
                    is_valid_val = df[field].notna()
                    total_weighted_norm_dev[is_valid_val] += norm_deviation[is_valid_val] * active_weights[field]
                    sum_of_weights_applied[is_valid_val] += active_weights[field]
                
                # Calculate final score: sum of weighted normalized deviations / sum of weights applied
                final_scores = total_weighted_norm_dev / sum_of_weights_applied
                final_scores = final_scores.replace([np.inf, -np.inf], np.nan) # Handle potential division by zero if sum_of_weights is 0

                for img_id, score_val in final_scores.items():
                    image_scores_list.append({
                        "image_id": img_id, # Index of DataFrame
                        "score": round(score_val, 4) if pd.notna(score_val) else "N/A",
                        "notes": "Lower score indicates values closer to the set average." if pd.notna(score_val) else "Not scorable (e.g., all compared fields were N/A)."
                    })
                logs.append(f"Weighted scoring performed. Fields used: {scorable_fields}. Weights: {active_weights}")

        elif len(df) < 2 and self._scoring_method_config == "weighted_deviation_from_mean":
            logs.append("Weighted scoring requires at least two images; matrix displayed only.")

        summary_parts = [f"Comparison Matrix for {len(df)} image(s)."]
        if image_scores_list:
            summary_parts.append("Weighted deviation scores calculated (lower is closer to set average).")

        return json.dumps({
            "success": True,
            "comparison_matrix": comparison_matrix,
            "image_scores": image_scores_list,
            "summary": "\n".join(summary_parts),
            "logs": logs
        }, default=str, ensure_ascii=False) # Added ensure_ascii=False for broader char support
