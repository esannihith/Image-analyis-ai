from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import pyexiv2
import json
import os
from datetime import datetime

"""
Image metadata extraction tool for CrewAI. Extracts EXIF/IPTC/XMP metadata from images, with hachoir fallback.
Returns output matching the standardized schema: {"metadata": <dict>, "success": <bool>, "error": <str|null>}.
"""

class ImageMetadataInput(BaseModel):
    """Input schema for Image Metadata Extraction Tool."""
    image_path: str = Field(..., description="Full path to the image file for metadata extraction.")


class ImageMetadataExtractionTool(BaseTool):
    name: str = "Image Metadata Extractor"
    description: str = (
        "Extracts comprehensive metadata (EXIF, IPTC, XMP) from image files. "
        "Returns timestamp, GPS coordinates, camera settings (ISO, aperture, shutter speed, focal length), "
        "keywords, copyright information, and all other available metadata in JSON format."
    )
    args_schema: Type[BaseModel] = ImageMetadataInput

    def _run(self, image_path: str) -> str:
        """
        Extract all metadata from image file using pyexiv2, with hachoir fallback.
        Returns a JSON string matching the expected output schema.
        """
        try:
            # Validate file exists
            if not os.path.exists(image_path):
                return json.dumps({
                    "metadata": {},
                    "success": False,
                    "error": f"File not found: {image_path}"
                })
            
            # Validate file is an image
            valid_extensions = {'.jpg', '.jpeg', '.tiff', '.tif', '.png', '.raw', '.cr2', '.nef', '.arw', '.dng'}
            file_ext = os.path.splitext(image_path)[1].lower()
            if file_ext not in valid_extensions:
                return json.dumps({
                    "metadata": {},
                    "success": False,
                    "error": f"Unsupported file format: {file_ext}"
                })
            
            # Initialize metadata container
            metadata_result = {
                "file_info": {
                    "filename": os.path.basename(image_path),
                    "filepath": image_path,
                    "file_size": os.path.getsize(image_path)
                },
                "exif": {},
                "iptc": {},
                "xmp": {},
                "processed_data": {},
                "success": True,
                "extraction_timestamp": datetime.now().isoformat()
            }
            
            try:
                # Open image and extract metadata
                with pyexiv2.Image(image_path) as img:
                    # Extract EXIF data
                    exif_data = img.read_exif()
                    metadata_result["exif"] = exif_data
                    
                    # Extract IPTC data
                    iptc_data = img.read_iptc()
                    metadata_result["iptc"] = iptc_data
                    
                    # Extract XMP data
                    xmp_data = img.read_xmp()
                    metadata_result["xmp"] = xmp_data
                    
                    # Process and extract key fields for easy access
                    processed = self._process_key_metadata(exif_data, iptc_data, xmp_data)
                    metadata_result["processed_data"] = processed
                
                return json.dumps({
                    "metadata": metadata_result,
                    "success": True,
                    "error": None
                }, indent=2, ensure_ascii=False)
                
            except Exception as e:
                # Internal fallback using hachoir
                try:
                    from hachoir.parser import createParser
                    from hachoir.metadata import extractMetadata
                    parser = createParser(image_path)
                    if not parser:
                        raise Exception("Hachoir parser could not be created.")
                    metadata = extractMetadata(parser)
                    if not metadata:
                        raise Exception("Hachoir could not extract metadata.")
                    meta_dict = {item.key: item.value for item in metadata.exportPlaintext()}
                    return json.dumps({
                        "metadata": meta_dict,
                        "success": True,
                        "error": None
                    }, indent=2, ensure_ascii=False)
                except Exception as hachoir_exc:
                    return json.dumps({
                        "metadata": {},
                        "success": False,
                        "error": f"Extraction failed: {str(e)}; Hachoir fallback also failed: {str(hachoir_exc)}"
                    }, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({
                "metadata": {},
                "success": False,
                "error": f"Failed to extract metadata: {str(e)}"
            }, indent=2)
    
    def _process_key_metadata(self, exif_data: dict, iptc_data: dict, xmp_data: dict) -> dict:
        """
        Process raw metadata and extract key fields in a structured format.
        
        Args:
            exif_data: Raw EXIF data dictionary
            iptc_data: Raw IPTC data dictionary
            xmp_data: Raw XMP data dictionary
            
        Returns:
            Dictionary with processed key metadata fields
        """
        processed = {
            "camera_info": {},
            "technical_settings": {},
            "datetime_info": {},
            "gps_info": {},
            "descriptive_info": {},
            "copyright_info": {}
        }
        
        try:
            # Camera Information
            processed["camera_info"] = {
                "make": exif_data.get("Exif.Image.Make", "").strip(),
                "model": exif_data.get("Exif.Image.Model", "").strip(),
                "software": exif_data.get("Exif.Image.Software", "").strip(),
                "lens_make": exif_data.get("Exif.Photo.LensMake", "").strip(),
                "lens_model": exif_data.get("Exif.Photo.LensModel", "").strip()
            }
            
            # Technical Settings
            processed["technical_settings"] = {
                "iso": exif_data.get("Exif.Photo.ISOSpeedRatings", ""),
                "aperture": exif_data.get("Exif.Photo.FNumber", ""),
                "shutter_speed": exif_data.get("Exif.Photo.ExposureTime", ""),
                "focal_length": exif_data.get("Exif.Photo.FocalLength", ""),
                "focal_length_35mm": exif_data.get("Exif.Photo.FocalLengthIn35mmFilm", ""),
                "exposure_mode": exif_data.get("Exif.Photo.ExposureMode", ""),
                "metering_mode": exif_data.get("Exif.Photo.MeteringMode", ""),
                "flash": exif_data.get("Exif.Photo.Flash", ""),
                "white_balance": exif_data.get("Exif.Photo.WhiteBalance", "")
            }
            
            # DateTime Information
            processed["datetime_info"] = {
                "date_time_original": exif_data.get("Exif.Photo.DateTimeOriginal", ""),
                "date_time_digitized": exif_data.get("Exif.Photo.DateTimeDigitized", ""),
                "date_time": exif_data.get("Exif.Image.DateTime", ""),
                "subsec_time_original": exif_data.get("Exif.Photo.SubSecTimeOriginal", ""),
                "offset_time_original": exif_data.get("Exif.Photo.OffsetTimeOriginal", "")
            }
            
            # GPS Information
            processed["gps_info"] = {
                "latitude": exif_data.get("Exif.GPSInfo.GPSLatitude", ""),
                "latitude_ref": exif_data.get("Exif.GPSInfo.GPSLatitudeRef", ""),
                "longitude": exif_data.get("Exif.GPSInfo.GPSLongitude", ""),
                "longitude_ref": exif_data.get("Exif.GPSInfo.GPSLongitudeRef", ""),
                "altitude": exif_data.get("Exif.GPSInfo.GPSAltitude", ""),
                "altitude_ref": exif_data.get("Exif.GPSInfo.GPSAltitudeRef", ""),
                "timestamp": exif_data.get("Exif.GPSInfo.GPSTimeStamp", ""),
                "datestamp": exif_data.get("Exif.GPSInfo.GPSDateStamp", "")
            }
            
            # Descriptive Information (IPTC/XMP)
            processed["descriptive_info"] = {
                "title": iptc_data.get("Iptc.Application2.ObjectName", "") or xmp_data.get("Xmp.dc.title", ""),
                "description": iptc_data.get("Iptc.Application2.Caption", "") or xmp_data.get("Xmp.dc.description", ""),
                "keywords": iptc_data.get("Iptc.Application2.Keywords", "") or xmp_data.get("Xmp.dc.subject", ""),
                "category": iptc_data.get("Iptc.Application2.Category", ""),
                "creator": iptc_data.get("Iptc.Application2.Byline", "") or xmp_data.get("Xmp.dc.creator", ""),
                "city": iptc_data.get("Iptc.Application2.City", "") or xmp_data.get("Xmp.photoshop.City", ""),
                "country": iptc_data.get("Iptc.Application2.CountryName", "") or xmp_data.get("Xmp.photoshop.Country", ""),
                "rating": xmp_data.get("Xmp.xmp.Rating", "")
            }
            
            # Copyright Information
            processed["copyright_info"] = {
                "copyright": exif_data.get("Exif.Image.Copyright", "") or iptc_data.get("Iptc.Application2.Copyright", "") or xmp_data.get("Xmp.dc.rights", ""),
                "rights_usage_terms": xmp_data.get("Xmp.xmpRights.UsageTerms", ""),
                "credit": iptc_data.get("Iptc.Application2.Credit", ""),
                "source": iptc_data.get("Iptc.Application2.Source", "")
            }
            
        except Exception as e:
            processed["processing_error"] = f"Error processing metadata: {str(e)}"
        
        return processed