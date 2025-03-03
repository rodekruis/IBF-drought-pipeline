# IBF Drought Pipeline

## Overview
The IBF Drought Pipeline updates the IBF Drought Portal based on predefined trigger thresholds derived from various drought indicators. The current implementation uses the Seasonal Rainfall Forecast from ECMWF (European Centre for Medium-Range Weather Forecasts). Two specific indicators serve as drought trigger thresholds:
1. 1-month Seasonal Rainfall Forecast (configured as `seasonal_rainfall_forecast`).
2. 3-month Aggregated Seasonal Rainfall Forecast (configured as `seasonal_rainfall_forecast_3m`).

> **Note:** In some countries, the rainy season may exceed 3 months. However, ECMWF forecasts for lead times longer than 3 months are typically less reliable for many regions.

The pipeline assesses whether forecasted rainfall falls below the lower tercile threshold (i.e., the 33rd percentile) to determine if a region is at risk for drought conditions as outlined in the EAPs.

## How It Works
The pipeline follows a series of steps to retrieve, process, and store data based on a trigger model that defines drought conditions. The core functionality includes:

### 1. Data Extraction
- The pipeline retrieves data from the ECMWF Seasonal Rainfall Forecast, providing predictions for upcoming months.
- The forecast can be broken down into individual months or aggregated over a rolling 3-month period. This is dependent on the drought inicator selected for the specific country (based on the EAP document)

### 2. Drought Indicators
- The current implmentation of the pipeline calculates the drought indicator using the lower tercile threshold:
    - **1-month Forecast:** The system checks if the predicted rainfall is below the lower tercile (33rd percentile) for a one-month period.
    - **3-month Rolling Forecast:** The system checks if the accumulated rainfall over the 3-month period is below the lower tercile.

### 3. Trigger Model
- The trigger model defines specific rules for calculating drought thresholds. currently two options are implmented.
    - **Seasonal Rainfall Forecast (1-month):** Determines drought conditions by checking if the forecasted rainfall is below the lower tercile of the historical average based on ECMWF hindcast data.
    - **Seasonal Rainfall Forecast (3-month):** Aggregates rainfall over 3 months and checks if the combined forecast falls below the lower tercile of the historical average.

### 4. Spatial Units
- Climate regions are used for spatial aggregation. In smaller countries with a single climate zone, there will be one spatial aggregation. In larger countries with multiple climate regions, aggregation will occur based on the number of climate regions.
- To implement the pipeline for a new country, the climate regions dataset should be defined and uploaded to the Azure Cosmos database.

### 5. Drought Extent
- If the trigger level is met, the extent of the drought is determined by comparing the average rainfall layer for the current forecast period with the average climate conditions as forecasted by ECMWF.
- Grid cells with lower-than-average rainfall are classified as being within the drought extent.
- This drought extent map is then used to calculate the number of affected populations.

### 6. Update IBF Drought Portal
- Once the data is processed, the pipeline updates the IBF Drought Portal with the latest drought information.

## Key Modules

### Extract Module (`extract.py`)
- The main module for extracting and processing drought data. It retrieves ECMWF data (including seasonal rainfall forecasts) and processes it according to the defined drought indicators.
- The `Extract` class in this module allows users to specify data sources, download forecast data, and process it according to the set thresholds.
- Users can configure the trigger model (e.g., `seasonal_rainfall_forecast` or `seasonal_rainfall_forecast_3m`).
- New drought indicators can be added by implementing the necessary logic within this class, with functions such as `prepare_ecmwf_data()` and `extract_ecmwf_data()`.

### Drought Indicators
- The current indicators are based on seasonal rainfall forecasts. The trigger model settings can be adjusted.
- To add a new drought indicator (e.g., based on soil moisture), users need to extend the logic in the `Extract` module, specifically in the `get_data()` and `extract_ecmwf_data()` methods.

## Adding New Drought Indicators
To implement a new drought indicator:
1. **Define the New Indicator:** Identify the data source and threshold for triggering drought conditions (e.g., soil moisture, temperature, or river discharge).
2. **Update the Extract Class:** Modify or add new methods in the `extract.py` module to handle data extraction and processing for the new indicator. This may involve downloading data from new sources, applying new thresholds, and performing the necessary calculations.

## Adding a New Country
1. **Update Configuration:** Add the new country to the configuration file.
2. **Define Climate Regions:** Create and upload the climate regions dataset for the new country to the Azure Cosmos database.
