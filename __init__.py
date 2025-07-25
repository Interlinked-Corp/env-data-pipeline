"""
Environmental Data Pipeline

A modular pipeline for retrieving environmental data by latitude and longitude coordinates.
Integrates LANDFIRE, MODIS, USGS, and weather data sources.
"""

from .pipeline import EnvironmentalDataPipeline
from .metadata import LANDFIREMetadataExtractor, extract_all_metadata

__version__ = "1.0.0"
__author__ = "Interlinked Corp"

__all__ = [
    "EnvironmentalDataPipeline",
    "LANDFIREMetadataExtractor", 
    "extract_all_metadata"
]