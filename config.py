"""
Environmental Data Pipeline Configuration

This file contains all configuration settings for the environmental data pipeline.
Modify these settings to customize data sources and behavior.
"""

# MODIS Data Access
# MODIS data is now accessed through ORNL web service (no authentication required)
# Set ENABLE_MODIS to False to disable MODIS data retrieval
MODIS_ENABLED = True

# LANDFIRE Configuration
# Available years: 2024, 2023, 2022
LANDFIRE_YEAR = 2024

# Data Retrieval Parameters
DEFAULT_BUFFER_METERS = 1000    # Default buffer around coordinates in meters
MODIS_SEARCH_DAYS = 30         # Days back to search for MODIS data

# Data Source Controls
ENABLE_LANDFIRE = True         # LANDFIRE vegetation and fuel data
ENABLE_USGS_ELEVATION = True   # USGS 3DEP elevation data
ENABLE_MODIS = True           # MODIS satellite data (via ORNL service)

# Weather Data Configuration (OpenWeatherMap)
# Loads from .env file or environment variables
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")  # Load from .env file or environment variable
OPENWEATHER_ENV = os.getenv("OPENWEATHER_ENV", "dev")   # Default to "dev" if not set

# Logging Configuration
LOG_LEVEL = "INFO"            # DEBUG, INFO, WARNING, ERROR