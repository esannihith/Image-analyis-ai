from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import requests
import json

class NamedPlaceEnrichmentInput(BaseModel):
    location: str = Field(..., description="Human-friendly location name (e.g., 'Eiffel Tower, Paris') to enrich.")

class NamedPlaceEnrichmentTool(BaseTool):
    name: str = "Named Place Enrichment Tool"
    description: str = (
        "Fetches a concise summary or Wikipedia snippet about a named place/location. "
        "Given a location string, returns a short enrichment text providing historical or descriptive details."
    )
    args_schema: Type[BaseModel] = NamedPlaceEnrichmentInput

    def _run(self, location: str) -> str:
        # Use Wikipedia API to fetch a summary
        try:
            # Wikipedia API expects underscores instead of spaces
            search_term = location.replace(' ', '_')
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if 'extract' in data and data['extract']:
                    return json.dumps({
                        "success": True,
                        "summary": data['extract'],
                        "title": data.get('title', location),
                        "source": "wikipedia"
                    })
                elif 'type' in data and data['type'] == 'disambiguation':
                    return json.dumps({
                        "success": False,
                        "error": f"Disambiguation page found for '{location}'. Please specify a more precise location.",
                        "source": "wikipedia"
                    })
            # If not found, try a search
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={location}&format=json"
            search_resp = requests.get(search_url, timeout=10)
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                if search_data.get('query', {}).get('search'):
                    first_title = search_data['query']['search'][0]['title']
                    # Try fetching summary for the first search result
                    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{first_title.replace(' ', '_')}"
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        if 'extract' in data and data['extract']:
                            return json.dumps({
                                "success": True,
                                "summary": data['extract'],
                                "title": data.get('title', first_title),
                                "source": "wikipedia"
                            })
            return json.dumps({
                "success": False,
                "error": f"No Wikipedia summary found for '{location}'."
            })
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Failed to fetch enrichment: {e}"
            })
