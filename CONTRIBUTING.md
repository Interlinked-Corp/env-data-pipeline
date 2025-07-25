# Contributing to Environmental Data Pipeline

## Development Setup

1. **Clone repository and setup environment:**
   ```bash
   git clone <repository-url>
   cd env-data-pipeline
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Run tests before making changes:**
   ```bash
   python tests/test_pipeline.py
   ```

## Code Standards

### Python Style
- Follow PEP 8 style guidelines
- Use type hints for all function parameters and return values
- Add docstrings to all classes and methods
- Maximum line length: 100 characters

### Testing
- Test all new functionality with `tests/test_pipeline.py`
- Validate data outputs for correctness
- Test error handling and edge cases
- Test with multiple geographic locations

### Documentation
- Update README.md for new features
- Document configuration changes in config.py
- Include usage examples for new functionality

## Submitting Changes

1. **Create feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes following code standards**

3. **Test thoroughly:**
   ```bash
   python tests/test_pipeline.py
   python pipeline.py  # Run example
   ```

4. **Commit with descriptive messages:**
   ```bash
   git add .
   git commit -m "Add: brief description of changes"
   ```

5. **Push and create pull request:**
   ```bash
   git push origin feature/your-feature-name
   ```

## Development Priorities

### Current Team Tasks
- **Mark/Emma**: Extract pixel values from GeoTIFF files using rasterio
- **Abhi**: Convert weather script from Jupyter to Python
- **Denver**: GitHub repository setup and dependency management
- **Meera/Ashwini**: Input/output validation and QA schemas

### Data Sources
- **LANDFIRE**: Vegetation and fuel model data (WCS endpoints)
- **MODIS**: Satellite vegetation indices via ORNL service
- **USGS 3DEP**: Elevation and topographic data

## Issue Reporting

When reporting issues:
1. Include Python version and operating system
2. Provide coordinates that reproduce the issue
3. Include full error messages and logs
4. Describe expected vs actual behavior

## Questions?

Contact the development team or create an issue for technical questions.