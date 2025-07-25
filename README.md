# Environmental Data Pipeline

Environmental data pipeline for retrieving geospatial data by latitude and longitude coordinates. Returns topography, vegetation, and weather data with real-time data currency tracking.

## Core Functionality

**Input:** Latitude and longitude coordinates  
**Output:** Topography, weather, and vegetation data for the specified location

## Quick Start

1. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env file with your OpenWeatherMap API key
   export OPENWEATHER_API_KEY="your_api_key_here"
   ```

3. **Run the pipeline:**
   ```bash
   python pipeline.py
   ```

4. **Test the pipeline:**
   ```bash
   python test_pipeline.py
   ```

## Usage Example

```python
from pipeline import EnvironmentalDataPipeline

# Initialize pipeline with latest LANDFIRE data
pipeline = EnvironmentalDataPipeline(landfire_year='latest')

# Get data for specific coordinates
data = pipeline.get_location_data(
    latitude=34.0522,
    longitude=-118.2437,
    buffer_meters=1000
)

# Access retrieved data
landfire_data = data['landfire']['data']
elevation_data = data['elevation']['data']
weather_data = data['weather']['data']
modis_data = data['modis']['data']

# Check data currency
currency = data['data_currency']
print(f"Real-time sources: {currency['real_time_sources']}")
print(f"Timeliness score: {data['summary']['timeliness_score']}/100")
```

## Data Sources & Products

### OpenWeatherMap (Weather Data)
**What it provides**: Real-time weather conditions and forecasts
**Goal**: Current weather parameters for fire behavior and response planning
**Format**: Python dictionary with current conditions and 5-day forecast

**Products**:
- **Current Weather**: Temperature, humidity, pressure, wind speed/direction, visibility
  - *What it looks like*: Real-time measurements updated every few minutes
  - *Values*: Temperature (°C), humidity (%), wind speed (m/s), pressure (hPa)
  
- **5-Day Forecast**: Extended weather predictions in 3-hour intervals
  - *What it looks like*: Time series of weather parameters
  - *Values*: Same parameters as current weather plus precipitation forecasts
  
- **Fire Weather Risk**: Basic risk assessment based on temperature, humidity, and wind
  - *What it looks like*: Risk categories for fire weather conditions
  - *Values*: LOW, MODERATE, HIGH, EXTREME

### LANDFIRE (Vegetation & Fuel Data)
**What it provides**: Current vegetation conditions and fire behavior fuel characteristics
**Goal**: Understand fuel loading, vegetation types, and canopy structure for fire modeling
**Format**: GeoTIFF raster data (pixel-based coverage maps)

**Products**:
- **`vegetation_type`**: Existing vegetation communities (forest, grassland, shrubland, etc.)
  - *What it looks like*: Categorical map with different colors for each vegetation type
  - *Values*: Integer codes (7000-9000s for developed areas, 1000s-6000s for natural vegetation)
  
- **`fuel_model`**: Fire behavior fuel model classifications (Scott & Burgan 40-model system)
  - *What it looks like*: Categorical map showing fuel loading characteristics
  - *Values*: Integer codes 91-204 (91=urban, 101-109=grass, 121-149=shrub, 161-189=timber)
  
- **`canopy_cover`**: Percentage of ground covered by tree canopy
  - *What it looks like*: Grayscale/color gradient map (darker = more canopy)
  - *Values*: 0-100% coverage
  
- **`canopy_height`**: Average height of tree canopy in meters
  - *What it looks like*: Height gradient map (green to red, low to high)
  - *Values*: 0-50+ meters
  
- **`canopy_bulk_density`**: Density of canopy fuels (kg/m³)
  - *What it looks like*: Density gradient map for crown fire potential
  - *Values*: 0-255 (scaled values, higher = denser canopy fuels)
  
- **`canopy_base_height`**: Height to bottom of tree canopy (meters)
  - *What it looks like*: Gradient map showing ladder fuel potential
  - *Values*: 0-50+ meters

**Topographic Products**:
- **`slope`**: Ground slope in degrees
  - *What it looks like*: Gradient map from flat (dark) to steep (bright)
  - *Values*: 0-90 degrees (0=flat, 90=vertical cliff)
  
- **`aspect`**: Compass direction of slope face
  - *What it looks like*: Circular color map (north=red, east=yellow, south=cyan, west=blue)
  - *Values*: 0-360 degrees (0/360=north, 90=east, 180=south, 270=west)
  
- **`elevation`**: Ground elevation above sea level (LANDFIRE version)
  - *What it looks like*: Topographic relief map (brown/green low to white/red high)
  - *Values*: Meters above sea level (-100 to 4000+ meters)

### USGS 3DEP (High-Resolution Elevation Data)
**What it provides**: High-resolution topographic information (higher precision than LANDFIRE)
**Goal**: Detailed terrain analysis for evacuation routes and precise elevation modeling
**Format**: GeoTIFF raster with continuous elevation values at higher spatial resolution

**Products**:
- **`elevation`**: Ground elevation above sea level (USGS high-resolution version)
  - *What it looks like*: Detailed topographic relief map with fine terrain features
  - *Values*: Meters above sea level (-100 to 4000+ meters)
  - *Difference from LANDFIRE*: Higher spatial resolution and more recent updates

### NASA MODIS (Satellite Data)
**What it provides**: Recent vegetation health, biophysical parameters, and land surface conditions
**Goal**: Current vegetation state and environmental conditions for analysis
**Format**: Python dictionary with time series measurements (90-day lookback for vegetation indices)

**Vegetation Indices** (16-day composites):
- **`MOD13Q1`**: Terra NDVI/EVI vegetation health indicators (250m resolution)
  - *What it looks like*: Time series showing vegetation greenness and health
  - *Values*: NDVI (-1 to +1), EVI (-1 to +1), higher values indicate healthier vegetation
  
- **`MYD13Q1`**: Aqua NDVI/EVI vegetation health indicators (250m resolution)
  - *What it looks like*: Time series showing vegetation greenness and health
  - *Values*: NDVI (-1 to +1), EVI (-1 to +1), higher values indicate healthier vegetation

**Biophysical Parameters**:
- **`MOD15A2H/MYD15A2H`**: Leaf Area Index (LAI) and Fraction of Photosynthetically Active Radiation (FPAR) (8-day, 500m)
  - *What it looks like*: Time series of vegetation density measurements
  - *Values*: LAI (0-10+ m²/m²), FPAR (0-1), higher values indicate denser vegetation
  
- **`MOD11A2/MYD11A2`**: Land Surface Temperature (8-day, 1km)
  - *What it looks like*: Time series of ground temperature measurements
  - *Values*: Temperature in Kelvin, converted to Celsius for analysis
  
- **`MOD17A2H/MYD17A2H`**: Gross Primary Productivity (8-day, 500m)
  - *What it looks like*: Time series of vegetation productivity measurements
  - *Values*: Carbon uptake rates (kg C/m²), indicating vegetation activity

## File Documentation

### `pipeline.py`
**Purpose**: Main pipeline entry point using modular service architecture
**Contains**:
- `EnvironmentalDataPipeline` class - main interface with data currency tracking
- Service imports from modular services package

**How to use**:
```python
from pipeline import EnvironmentalDataPipeline
pipeline = EnvironmentalDataPipeline(landfire_year='latest')
data = pipeline.get_location_data(latitude, longitude, buffer_meters)
```

### `services/` Directory
**Purpose**: Modular service architecture with individual data source modules

**`services/landfire_service.py`**:
- `LANDFIREDataService` - LANDFIRE vegetation and fuel data access
- Handles WCS requests for vegetation, fuel models, and topographic data

**`services/modis_service.py`**:
- `MODISDataService` - MODIS satellite data via ORNL API
- 90-day lookback for vegetation indices, optimized timeout handling

**`services/usgs_service.py`**:
- `USGSElevationService` - USGS 3DEP elevation data access
- High-resolution digital elevation models

**`services/weather_service.py`**:
- `OpenWeatherMapService` - Real-time weather data access
- Current conditions, 5-day forecasts, and fire weather risk assessment

**Output format**: Python dictionary structure with nested data organized by source:
```json
{
  "request": {"latitude": 34.0522, "longitude": -118.2437, "buffer_meters": 1000},
  "landfire": {"data": {"vegetation_type": {"data": "binary_geotiff", "size_bytes": 131476}}},
  "elevation": {"data": {"data": "binary_geotiff", "size_bytes": 262982}},
  "summary": {"total_sources": 2, "successful_sources": 2, "total_errors": 0}
}
```

### `test_pipeline.py`
**Purpose**: Test suite for the modular pipeline architecture
**Contains**:
- Core functionality tests with modular services
- Service architecture validation
- Data currency and timeliness testing
- Performance validation

**How to use**: `python test_pipeline.py`

## Data Format Details

### GeoTIFF Data Structure (LANDFIRE & USGS)

**Binary Data Storage**: GeoTIFF data is stored as raw binary bytes in the Python dictionary
```python
landfire_data = {
    'vegetation_type': {
        'data': b'\x49\x49\x2a\x00...',  # Raw binary GeoTIFF bytes
        'size_bytes': 131476,
        'format': 'GeoTIFF',
        'crs': 'EPSG:4326',
        'bbox': [-118.2527, 34.0432, -118.2347, 34.0612]
    }
}
```

**Extracting Pixel Values**: To access meaningful data, you need to process the binary GeoTIFF
```python
import rasterio
from io import BytesIO

# Extract binary data from dictionary
geotiff_bytes = landfire_data['vegetation_type']['data']

# Read with rasterio
with rasterio.open(BytesIO(geotiff_bytes)) as dataset:
    # Get pixel values as numpy array
    pixel_array = dataset.read(1)  # Shape: (256, 256)
    
    # Get geospatial metadata
    transform = dataset.transform    # Geographic transform matrix
    crs = dataset.crs               # Coordinate reference system
    bounds = dataset.bounds         # Geographic bounds
    
    # Convert pixel coordinates to geographic coordinates
    row, col = 128, 128  # Center pixel
    x, y = rasterio.transform.xy(transform, row, col)
    print(f"Center pixel value: {pixel_array[row, col]} at ({x}, {y})")
```

**Data Properties**:
- **Resolution**: 250-256 meters per pixel
- **Coordinate System**: EPSG:4326 (WGS84 lat/lon)
- **Dimensions**: 256x256 pixels
- **Data Type**: Integer values (varies by product)
- **No Data Value**: Typically -9999 or 255 for missing data

**Value Interpretation**:
- **Vegetation Type**: Integer codes (1000s-9000s, see LANDFIRE legend)
- **Fuel Model**: Integer codes (91-204, see Scott & Burgan classification)
- **Canopy Cover**: Percentage values (0-100)
- **Elevation**: Meters above sea level (float values)

### Time Series Data Structure (MODIS)

**Nested Dictionary Format**: MODIS data contains time series measurements
```python
modis_data = {
    'MOD13Q1': {
        'data': {
            'subset': [
                {
                    'calendar_date': '2025-06-26',
                    'modis_date': 'A2025177',
                    'data': {
                        'NDVI': '0.7234',
                        'EVI': '0.4521',
                        'pixel_reliability': '0'
                    }
                },
                # ... more time points
            ]
        },
        'description': 'Terra Vegetation Indices...'
    }
}
```

**Accessing Time Series Values**:
```python
# Get NDVI time series
ndvi_values = []
dates = []
for point in modis_data['MOD13Q1']['data']['subset']:
    ndvi_values.append(float(point['data']['NDVI']))
    dates.append(point['calendar_date'])

# Latest NDVI value
latest_ndvi = float(modis_data['MOD13Q1']['data']['subset'][-1]['data']['NDVI'])
```

### Weather Data Structure

**Real-time Dictionary Format**: Weather data is directly accessible
```python
weather_data = {
    'current': {
        'temperature_celsius': 28.5,
        'humidity_percent': 45,
        'wind_speed_mps': 3.2,
        'fire_weather_risk': 'MODERATE'
    },
    'forecast': [
        {
            'timestamp': '2025-07-25T12:00:00',
            'temperature_celsius': 30.1,
            'precipitation_mm': 0.0
        },
        # ... more forecast points
    ]
}
```

### Processing Requirements

**Required Libraries**:
```python
pip install rasterio numpy  # For GeoTIFF processing
pip install pandas         # For time series analysis (optional)
```

**Memory Considerations**:
- GeoTIFF files: ~130KB each in memory
- MODIS time series: ~1-5KB per product
- Weather data: <1KB
- Total memory per location: ~1-2MB