import os
import geopandas as gpd
from droughtpipeline.load import Load
from droughtpipeline.settings import Settings
from droughtpipeline.secrets import Secrets
from droughtpipeline.utils import (
    convert_to_mm_per_month,
    get_extent_shp,
    subset_region,
    dataarray_to_dict
)
import xarray as xr
import numpy as np
import click


secrets = Secrets()
settings = Settings("config/config.yaml")
load = Load(settings=settings, secrets=secrets)

def calculate_threshold_data(
        ds_hindcast: xr.Dataset,
        filtered_gdf: gpd.GeoDataFrame, 
        trigger_model: str) -> dict:
    """
    Calculate threshold data from hindcast data
    
    Parameters:
        ds_hindcast: Hindcast dataset
        filtered_gdf: Filtered GeoDataFrame for the region
        trigger_model: Trigger model type
        
    Returns:
        dict: Calculated threshold data
    """
    
    # Process based on trigger model
    if trigger_model == 'seasonal_rainfall_forecast':
        tprate_hindcast = ds_hindcast['tprate']
        tprate_hindcast_mean = ds_hindcast.mean(['number', 'time'])
    elif trigger_model == 'seasonal_rainfall_forecast_3m':
        ds_hindcast_3m = (
            ds_hindcast.shift(forecastMonth=-2)
            .rolling(forecastMonth=3, min_periods=1)
            .sum()
        )
        tprate_hindcast = ds_hindcast_3m['tprate']
        tprate_hindcast_mean = ds_hindcast_3m.mean(['number', 'time'])
    else:
        raise ValueError(f"Trigger model {trigger_model} not supported")
    
    # Ensure the mean is a DataArray (not a Dataset) before combining
    if isinstance(tprate_hindcast_mean, xr.Dataset):
        tprate_hindcast_mean = tprate_hindcast_mean['tprate']
    else:
        tprate_hindcast_mean = tprate_hindcast_mean

    sub_region = get_extent_shp(filtered_gdf)

    # Apply weighted mean for the region
    weights = np.cos(np.deg2rad(tprate_hindcast.latitude))

    # Calculate hindcast anomalies
    hindcast_sub = subset_region(tprate_hindcast, sub_region)
    hindcast_mean = hindcast_sub.weighted(weights).mean(['latitude', 'longitude'])
    hindcast_anomalies = hindcast_mean - hindcast_mean.mean(['number', 'time'])
    hindcast_anomalies_tp = hindcast_anomalies # * hindcast_anomalies.numdays * 24 * 60 * 60 * 1000   

    # Define thresholds
    thresholds = {
        'P0': dataarray_to_dict(hindcast_anomalies_tp.min(['number', 'time'])),
        'P33': dataarray_to_dict(hindcast_anomalies_tp.quantile(1 / 3., ['number', 'time'])),
        'P66': dataarray_to_dict(hindcast_anomalies_tp.quantile(2 / 3., ['number', 'time'])),
        'P100': dataarray_to_dict(hindcast_anomalies_tp.max(['number', 'time']))
}

    return thresholds


@click.command()
@click.option("--country", "-c", help="country ISO3", default="all")
@click.option("--year_start", "-ys", help="start year", default=1991)
@click.option("--year_end", "-ye", help="end year", default=2020)
@click.option("--trigger_model", help="trigger model name", default="seasonal_rainfall_forecast_3m")
def add_drought_thresholds(country, year_start, year_end, trigger_model):
    filepath = "data/updates/"
    filename = "ecmwf_seas5_hindcast_monthly_tp.grib"
    os.makedirs(f"{filepath}", exist_ok=True)

    if country != "all" and country not in [
        c["name"] for c in settings.get_setting("countries")
    ]:
        raise ValueError(f"No config found for country {country}")
    
    # loop over countries
    for country_settings in settings.get_setting("countries"):
        if country != "all" and country != country_settings["name"]:
            continue
        country_name = country_settings["name"]

        if trigger_model not in country_settings["trigger_model"]["model"]:
            raise ValueError(f"No config found for trigger model {trigger_model}")

        # # Download drought hindcast
        print(f"Download rainfall hindcast for country {country_name}, period {year_start}-{year_end}")
        load.download_ecmwf_hindcast(filepath+filename, country_name, year_start, year_end)
        
        print(f"Processing drought thresholds for country {country_name}, trigger model {trigger_model}")
        # Load and process hindcast data
        ds_hindcast = convert_to_mm_per_month(f'{filepath+filename}')

        for climateRegion in country_settings["climate_region"]:
            climate_region_data = load.get_pipeline_data("climate-region", country_name)
            climate_region_code = climateRegion["climate-region-code"]
            
            print(f'Calculating thresholds for climate region {climate_region_code}')
            climate_region_du = climate_region_data.get_climate_region_data_unit(climate_region_code)
            pcodes = climate_region_du.pcodes
            admin_level_ = climate_region_du.adm_level

            # filter geofile for the climate region
            geofile = load.get_adm_boundaries(country_name, admin_level_)
            climate_region_pcodes = pcodes[f'{admin_level_}']
            filtered_gdf = geofile[geofile[f'adm{admin_level_}_pcode'].isin(climate_region_pcodes)]
            filtered_gdf['placeCode']= filtered_gdf[f'adm{admin_level_}_pcode']          
            
            if filtered_gdf.empty:
                raise ValueError(f"No data matching {climate_region_code} found in the geofile.")  
            
            # Calculate thresholds
            thresholds = calculate_threshold_data(ds_hindcast, filtered_gdf, trigger_model)

        # Save to CosmosDB as per-point documents for future runs
        load.save_threshold_data(country_name, thresholds, trigger_model, climate_region_code)
        print(f"Saved thresholds data to CosmosDB for country {country_name}")


if __name__ == "__main__":
    add_drought_thresholds()