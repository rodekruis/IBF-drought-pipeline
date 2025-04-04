# IBF Drought Pipeline

## Running the Drought Pipeline with Docker Compose

To run the drought pipeline for testing using Docker Compose, follow these steps:

1. Ensure you have Docker and Docker Compose installed on your machine.

2. Place your `.env` file in the same directory as your `docker-compose.yml` file. This file should contain the necessary environment variables for the pipeline. The variables are in `.en.example` file 

3. Build and run the Docker container using Docker Compose:

    ```sh
    docker-compose up --build
    ```

This will build the Docker image and run the drought pipeline with the specified options (`--country ETH --prepare --extract --forecast --send`).

You can modify the `command` section in the `docker-compose.yml` file to change the options as needed for your testing.

## Triggering Model Run for Drought Scenarios

This s allows you to test **"Warning"** and **"No Warning"** scenarios for a specific month by triggering a pipeline run via an API. The API is integrated with the [Logic App `drought-pipeline-sen`](https://portal.azure.com/#@rodekruis.onmicrosoft.com/resource/subscriptions/57b0d17a-5429-4dbb-8366-35c928e3ed94/resourceGroups/IBF-system/providers/Microsoft.Logic/workflows/drought-pipeline-sen/logicApp).

### How to Trigger a Model Run

You can trigger a model run by making a request to the API and passing the following parameters:

- `month` – A three-letter format of the month (e.g., `"Jan"`, `"Jul"`).
- `year` – The four-digit year (e.g., `2024`).
- `scenario` *(optional)* – Can be one of the following:
  - `"Warning"` – Forces the model to trigger at a low threshold.
  - `"NoWarning"` – Forces the model to trigger only at a very high threshold.
  - the default is the standard threshold set in the Early Action Protocol (EAP).

If you **omit** the `scenario` parameter, the default `"Forecast"` mode is used.
you can run a scenario upto the current month, these forecasts are initialized on the 1st of each month and are released at 12:00 UTC on the 5th day of the month . [ECMWF data Dissemination schedule](https://confluence.ecmwf.int/display/DAC/Dissemination+schedule)

### Scenario Logic

The `trigger_on_minimum_probability` is set based on the selected scenario:

```python
scenario = os.getenv("SCENARIO", "Forecast")

if scenario == "Warning":
    trigger_on_minimum_probability = 0.1
elif scenario == "NoWarning":
    trigger_on_minimum_probability = 0.9
elif scenario == "Forecast":
    trigger_on_minimum_probability = 0.4
```

 
 



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

For more details, refer to the ECMWF documentation: [Section 8.3.1 Chart Output](https://confluence.ecmwf.int/display/FUG/Section+8.3.1+Chart+output).  



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
2. **Define Climate Regions:** Create and upload the climate regions dataset for the new country to the Azure Cosmos database. Look at the [add_climate region script](data_updates/add_climateregions_cosmos.py) for instruction on how to do this 



# Configuration File: Country-Specific Settings

This configuration file defines settings for climate regions, triggers, and thresholds for a specific country (e.g., Kenya). It is used to control how alerts and forecasts are generated, and how they interact with the portal. Below is an explanation of the various settings and their purpose.


The configuration file is structured in YAML format, and each section pertains to different country-specific settings. The key sections include:

1. **countries**: This defines settings for specific countries (e.g., KEN for Kenya).
2. **admin-levels**: Specifies which administrative levels the settings apply to.
3. **pipeline-will-trigger-portal**: Controls whether the trigger should be uploaded to the portal.
4. **classify-alert-on**: Defines whether multi-threshold classification is enabled.
5. **alert-on-minimum-probability**: Sets the minimum thresholds for various alert levels.
6. **trigger_model**: Defines the trigger model and its settings for triggering alerts.
7. **Climate_Region**: Defines the climate region (e.g., National) and lead-time and season for each month.


### **countries**
This section defines settings specific to a country, in this case, Kenya (`KEN`). Each country can have its own configuration settings, and multiple regions or administrative levels can be defined.

Example:

```yaml
countries:
  - name: KEN
    admin-levels:
      - 1
    pipeline-will-trigger-portal: disable
    classify-alert-on: disable
```

#### **Parameters:**
- `name`: The ISO country code for the country (e.g., "KEN" for Kenya).
- `admin-levels`: The administrative levels within the country to which the settings apply (e.g., 1 for first-level administrative areas).
- `pipeline-will-trigger-portal`: Whether the pipeline will trigger the portal (values: `enable` or `disable`).
- `classify-alert-on`: Whether multi-threshold classification is enabled (values: `enable` or `disable`).

---

### **alert-on-minimum-probability**
This section defines the thresholds for the multi-threshold alert system. It specifies the probability levels that trigger different alert types. **This is DISABLED in current piepline**

Example:

```yaml
alert-on-minimum-probability:
  min: 0.65
  med: 0.75
  max: 0.85
```

#### **Parameters:**
- `min`: The minimum probability threshold to trigger an alert (e.g., 0.65).
- `med`: The medium probability threshold (e.g., 0.75).
- `max`: The maximum probability threshold (e.g., 0.85).

These thresholds can be adjusted depending on the sensitivity needed for generating alerts.

---

### **trigger_model**
Defines the settings for the climate model used for triggering alerts based on seasonal forecasts.

Example:

```yaml
trigger_model:
  model: seasonal_rainfall_forecast
  trigger-on-minimum-probability: 0.6
  trigger-on-minimum-probability-drought-extent: 0.6
  trigger-on-minimum-admin-area-in-drought-extent: 0.5
```

#### **Parameters:**
- `model`: The name of the indicator or trigger model used (e.g., `seasonal_rainfall_forecast`).
- `trigger-on-minimum-probability`: The minimum probability at which the seasonal forecast is considered to be below the lower tercile (indicating a potential drought).
- `trigger-on-minimum-probability-drought-extent`: Defines the minimum probability that the ensemble members suggest the seasonal average is below the climate average (for assessing drought extent).
- `trigger-on-minimum-admin-area-in-drought-extent`: Defines the threshold for determining whether a region is experiencing drought based on the drought extent map. This setting is not currently used but is reserved for future use.

---

### **Climate_Region**
This section specifies the climate region and the lead-time for each forecast season (e.g., for January, the forecast lead time could be 2 months).

Example:

```yaml
Climate_Region:
  - name: National
    climate-region-code: 1
    leadtime:
      Jan:
        - MAM: "2-month"
```

#### **Parameters:**
- `name`: The name of the climate region (e.g., "National").
- `climate-region-code`: The numerical code associated with the climate region.
- `leadtime`: Defines the lead-time for each season (e.g., "MAM" (March-April-May) for January with a 2-month lead time).





 
