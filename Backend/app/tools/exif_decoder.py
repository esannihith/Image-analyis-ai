# app/tools/exif_decoder.py
import json
import os
from typing import Type, Dict, Any, Optional # Added Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from datetime import datetime

# Attempt to import pyexiv2 and hachoir
try:
    import pyexiv2
    PYEXIV2_AVAILABLE = True
except ImportError:
    PYEXIV2_AVAILABLE = False
    pyexiv2 = None # Placeholder

try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
    from hachoir.core.field import MissingField # For checking hachoir fields
    HACHOIR_AVAILABLE = True
except ImportError:
    HACHOIR_AVAILABLE = False
    createParser = None # Placeholder
    extractMetadata = None # Placeholder
    MissingField = None # Placeholder


class EXIFDecoderInput(BaseModel):
    """Input schema for Image Metadata Extraction Tool."""
    image_path: str = Field(..., description="Full path to the image file for metadata extraction.")


class EXIFDecoderTool(BaseTool):
    name: str = "Image Metadata Extractor"
    description: str = (
        "Extracts comprehensive metadata (EXIF, IPTC, XMP) from image files using pyexiv2, with hachoir fallback. "
        "Returns timestamp, GPS coordinates, camera settings (ISO, aperture, shutter speed, focal length), image dimensions, "
        "keywords, copyright information, and all other available metadata in JSON format."
    )
    args_schema: Type[BaseModel] = EXIFDecoderInput

    def _convert_rational_to_float(self, rational_val: Any) -> Optional[float]:
        """Converts a pyexiv2 Rational or string fraction to float if possible."""
        if rational_val is None:
            return None
        if isinstance(rational_val, (int, float)):
            return float(rational_val)
        # Check for pyexiv2.Rational type if pyexiv2 is available
        if PYEXIV2_AVAILABLE and pyexiv2 and isinstance(rational_val, pyexiv2.Rational):
            if rational_val.denominator == 0: return None
            return rational_val.numerator / rational_val.denominator
        if isinstance(rational_val, str):
            if '/' in rational_val:
                try:
                    num, den = map(float, rational_val.split('/', 1))
                    if den == 0: return None
                    return num / den
                except ValueError:
                    return None
            else:
                try:
                    return float(rational_val)
                except ValueError:
                    return None
        return None # Or raise error, or return as string

    def _format_exposure_bias(self, bias_val: Any) -> Optional[str]:
        """Formats exposure bias (often a Rational) into a readable string like '+1/3 EV'."""
        float_bias = self._convert_rational_to_float(bias_val)
        if float_bias is None:
            return None
        
        if float_bias == 0.0:
            return "0 EV"
        
        # Attempt to find a common fraction representation
        # This is a simplified approach for common EV steps
        common_thirds = {0.33: "1/3", 0.66: "2/3", 0.333: "1/3", 0.666:"2/3", 0.3333:"1/3", 0.6666:"2/3"}
        common_halves = {0.5: "1/2", 0.7:"7/10"} # 0.7 for some cameras

        sign = "+" if float_bias > 0 else "" # Negative sign will be inherent
        abs_bias = abs(float_bias)

        for val, frac_str in common_thirds.items():
            if abs(abs_bias - val) < 0.01: # Check for approximate match
                return f"{sign}{frac_str} EV"
        for val, frac_str in common_halves.items():
             if abs(abs_bias - val) < 0.01:
                return f"{sign}{frac_str} EV"
        
        # Default to decimal representation if no common fraction matches
        return f"{sign}{abs_bias:.2f} EV"


    def _run(self, image_path: str) -> str:
        final_response: Dict[str, Any] = {
            "success": False,
            "image_path": image_path,
            "extracted_metadata": {},
            "error": None
        }

        if not os.path.exists(image_path):
            final_response["error"] = f"File not found: {image_path}"
            return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)

        valid_extensions = {'.jpg', '.jpeg', '.tiff', '.tif', '.png', '.raw', '.cr2', '.nef', '.arw', '.dng', '.heic', '.heif'}
        file_ext = os.path.splitext(image_path)[1].lower()
        if file_ext not in valid_extensions:
            final_response["error"] = f"Unsupported file format: {file_ext}"
            return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)

        metadata_payload: Dict[str, Any] = { # Type hint for clarity
            "file_info": {
                "filename": os.path.basename(image_path),
                "filepath": image_path,
                "file_size_bytes": os.path.getsize(image_path)
            },
            "image_dimensions": {"width": None, "height": None}, # Initialize
            "raw_exif": {},
            "raw_iptc": {},
            "raw_xmp": {},
            "processed_data": {},
            "hachoir_metadata": None,
            "extraction_timestamp": datetime.now().isoformat(),
            "library_used": None
        }

        if PYEXIV2_AVAILABLE and pyexiv2:
            try:
                # Using context manager for pyexiv2.Image is preferred
                with pyexiv2.Image(image_path) as img:
                    exif_data = img.read_exif()
                    iptc_data = img.read_iptc()
                    xmp_data = img.read_xmp()
                    # Get dimensions from EXIF primary, then general image attributes as fallback
                    width = exif_data.get("Exif.Photo.PixelXDimension")
                    height = exif_data.get("Exif.Photo.PixelYDimension")
                    if not width and not height: # Fallback for non-EXIF images or if tags missing
                         try: # pyexiv2.Image object might have pixelWidth, pixelHeight directly (undocumented, varies)
                            width = img.pixelWidth 
                            height = img.pixelHeight
                         except AttributeError: # Fallback to other EXIF width/length tags
                            width = exif_data.get("Exif.Image.ImageWidth")
                            height = exif_data.get("Exif.Image.ImageLength")
                    
                    metadata_payload["image_dimensions"]["width"] = int(width) if width is not None else None
                    metadata_payload["image_dimensions"]["height"] = int(height) if height is not None else None


                metadata_payload["raw_exif"] = exif_data
                metadata_payload["raw_iptc"] = iptc_data
                metadata_payload["raw_xmp"] = xmp_data
                # Pass dimensions to _process_key_metadata if needed there, or use them as already set in metadata_payload
                metadata_payload["processed_data"] = self._process_key_metadata(
                    exif_data, iptc_data, xmp_data, 
                    metadata_payload["image_dimensions"]["width"], 
                    metadata_payload["image_dimensions"]["height"]
                )
                metadata_payload["library_used"] = "pyexiv2"
                
                final_response["success"] = True
                final_response["extracted_metadata"] = metadata_payload
                return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)

            except Exception as pyexiv2_exc:
                if not HACHOIR_AVAILABLE or not createParser or not extractMetadata: # Check all hachoir components
                    final_response["error"] = f"pyexiv2 failed: {str(pyexiv2_exc)}. Hachoir fallback not available."
                    return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)
                pass 
        
        if HACHOIR_AVAILABLE and createParser and extractMetadata and MissingField:
            try:
                parser = createParser(image_path)
                if not parser:
                    final_response["error"] = "Hachoir parser could not be created."
                    return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)
                
                with parser: 
                    hachoir_meta_obj = extractMetadata(parser)
                
                if not hachoir_meta_obj:
                    final_response["error"] = "Hachoir could not extract metadata."
                    return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)
                
                hachoir_dict = {}
                width, height = None, None
                for field in hachoir_meta_obj:
                    if not field._name.startswith('/') and field.values: # Avoid private/internal fields
                        try:
                            # Handle common dimension fields in hachoir
                            if field.key == 'width': width = field.values[0].value
                            elif field.key == 'height': height = field.values[0].value
                            hachoir_dict[field.key] = [v.display for v in field.values]
                        except Exception:
                            hachoir_dict[field.key] = [str(v.value) for v in field.values] # Fallback to .value
                
                metadata_payload["image_dimensions"]["width"] = width
                metadata_payload["image_dimensions"]["height"] = height
                metadata_payload["hachoir_metadata"] = hachoir_dict
                # _process_key_metadata is not called for hachoir here as its structure is too different.
                # The agent would need to interpret hachoir_dict if it gets this.
                # Or, add a _process_hachoir_metadata method.
                # For now, processed_data will be empty if only hachoir succeeded.
                metadata_payload["library_used"] = "hachoir"
                
                final_response["success"] = True
                final_response["extracted_metadata"] = metadata_payload
                return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)

            except Exception as hachoir_exc:
                error_msg = f"Hachoir fallback failed: {str(hachoir_exc)}"
                if not PYEXIV2_AVAILABLE or not pyexiv2 : 
                    final_response["error"] = f"pyexiv2 not available. {error_msg}"
                else: 
                    final_response["error"] = f"pyexiv2 failed previously. {error_msg}"
                return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)
        else: 
            final_response["error"] = "No suitable metadata extraction library (pyexiv2 or hachoir) is available."
            return json.dumps(final_response, indent=2, ensure_ascii=False, default=str)

    def _process_key_metadata(self, exif_data: dict, iptc_data: dict, xmp_data: dict, img_width: Optional[int], img_height: Optional[int]) -> dict:
        processed = {
            "image_dimensions": {"width": img_width, "height": img_height}, # Store dimensions here
            "camera_info": {},
            "technical_settings": {},
            "datetime_info": {},
            "gps_info": {},
            "descriptive_info": {},
            "copyright_info": {}
        }
        
        try:
            def get_stripped(data, key, default=""):
                val = data.get(key, default)
                return val.strip() if isinstance(val, str) else val

            processed["camera_info"] = {
                "make": get_stripped(exif_data, "Exif.Image.Make"),
                "model": get_stripped(exif_data, "Exif.Image.Model"),
                "software": get_stripped(exif_data, "Exif.Image.Software"),
                "lens_make": get_stripped(exif_data, "Exif.Photo.LensMake"),
                "lens_model": get_stripped(exif_data, "Exif.Photo.LensModel")
            }
            
            processed["technical_settings"] = {
                "iso": exif_data.get("Exif.Photo.ISOSpeedRatings"),
                "aperture": self._convert_rational_to_float(exif_data.get("Exif.Photo.FNumber")),
                "shutter_speed_value": self._convert_rational_to_float(exif_data.get("Exif.Photo.ExposureTime")), # Store as float seconds
                "shutter_speed_display": str(exif_data.get("Exif.Photo.ExposureTime")), # Store original string too
                "focal_length": self._convert_rational_to_float(exif_data.get("Exif.Photo.FocalLength")),
                "focal_length_35mm": self._convert_rational_to_float(exif_data.get("Exif.Photo.FocalLengthIn35mmFilm")),
                "exposure_bias_value": self._format_exposure_bias(exif_data.get("Exif.Photo.ExposureBiasValue")),
                "exposure_mode": exif_data.get("Exif.Photo.ExposureMode"), # Often an int, needs mapping
                "metering_mode": exif_data.get("Exif.Photo.MeteringMode"), # Often an int, needs mapping
                "flash": exif_data.get("Exif.Photo.Flash"), # Often an int, needs mapping
                "white_balance": exif_data.get("Exif.Photo.WhiteBalance") # Often an int, needs mapping
            }
            
            processed["datetime_info"] = {
                "date_time_original": exif_data.get("Exif.Photo.DateTimeOriginal"),
                "date_time_digitized": exif_data.get("Exif.Photo.DateTimeDigitized"),
                "date_time": exif_data.get("Exif.Image.DateTime"),
                "subsec_time_original": exif_data.get("Exif.Photo.SubSecTimeOriginal"),
                "offset_time_original": exif_data.get("Exif.Photo.OffsetTimeOriginal"),
                "offset_time_digitized": exif_data.get("Exif.Photo.OffsetTimeDigitized"),
                "offset_time": exif_data.get("Exif.Photo.OffsetTime")

            }
            
            lat_val = self._convert_rational_to_float(exif_data.get("Exif.GPSInfo.GPSLatitude"))
            lon_val = self._convert_rational_to_float(exif_data.get("Exif.GPSInfo.GPSLongitude"))
            alt_val = self._convert_rational_to_float(exif_data.get("Exif.GPSInfo.GPSAltitude"))

            processed["gps_info"] = {
                "latitude": lat_val,
                "latitude_ref": get_stripped(exif_data, "Exif.GPSInfo.GPSLatitudeRef"),
                "longitude": lon_val,
                "longitude_ref": get_stripped(exif_data, "Exif.GPSInfo.GPSLongitudeRef"),
                "altitude": alt_val,
                "altitude_ref": exif_data.get("Exif.GPSInfo.GPSAltitudeRef"), 
                "timestamp": exif_data.get("Exif.GPSInfo.GPSTimeStamp"), # List of Rationals usually
                "datestamp": get_stripped(exif_data, "Exif.GPSInfo.GPSDateStamp")
            }
            
            # Convert GPS latitude/longitude to signed decimal degrees
            if processed["gps_info"]["latitude"] is not None and processed["gps_info"]["latitude_ref"] in ['S', 'W']:
                processed["gps_info"]["latitude"] *= -1
            if processed["gps_info"]["longitude"] is not None and processed["gps_info"]["longitude_ref"] in ['S', 'W']: # Should be 'W' for longitude
                 processed["gps_info"]["longitude"] *= -1


            processed["descriptive_info"] = {
                "title": get_stripped(iptc_data.get("Iptc.Application2.ObjectName")) or get_stripped(xmp_data.get("Xmp.dc.title")),
                "description": get_stripped(iptc_data.get("Iptc.Application2.Caption")) or get_stripped(xmp_data.get("Xmp.dc.description")), 
                "keywords": iptc_data.get("Iptc.Application2.Keywords") or xmp_data.get("Xmp.dc.subject"), 
                "category": get_stripped(iptc_data.get("Iptc.Application2.Category")),
                "creator": iptc_data.get("Iptc.Application2.Byline") or xmp_data.get("Xmp.dc.creator"), 
                "city": get_stripped(iptc_data.get("Iptc.Application2.City")) or get_stripped(xmp_data.get("Xmp.photoshop.City")),
                "country": get_stripped(iptc_data.get("Iptc.Application2.CountryName")) or get_stripped(xmp_data.get("Xmp.photoshop.Country")),
                "rating": self._convert_rational_to_float(xmp_data.get("Xmp.xmp.Rating"))
            }
            
            processed["copyright_info"] = {
                "copyright": get_stripped(exif_data.get("Exif.Image.Copyright")) or get_stripped(iptc_data.get("Iptc.Application2.Copyright")) or get_stripped(xmp_data.get("Xmp.dc.rights")),
                "rights_usage_terms": get_stripped(xmp_data.get("Xmp.xmpRights.UsageTerms")), 
                "credit": get_stripped(iptc_data.get("Iptc.Application2.Credit")),
                "source": get_stripped(iptc_data.get("Iptc.Application2.Source"))
            }
            
        except Exception as e:
            processed["_processing_error"] = f"Error during metadata processing: {str(e)}"
        
        return processed
