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

def process_hindcast_data():
    pass

def calculate_threshold_data(
        tprate_hindcast: xr.Dataset,
        filtered_gdf: gpd.GeoDataFrame, 
        ) -> dict:
    """
    Calculate threshold data from hindcast data
    
    Parameters:
        tprate_hindcast: Hindcast dataset
        filtered_gdf: Filtered GeoDataFrame for the region
        
    Returns:
        dict: Calculated threshold data
    """

    sub_region = get_extent_shp(filtered_gdf)

    # Apply weighted mean for the region
    weights = np.cos(np.deg2rad(tprate_hindcast.latitude))

    # Calculate hindcast anomalies
    hindcast_sub = subset_region(tprate_hindcast, sub_region)
    hindcast_mean = hindcast_sub.weighted(weights).mean(['latitude', 'longitude'])
    hindcast_anomalies = hindcast_mean - hindcast_mean.mean(['number', 'time'])
    hindcast_anomalies_tp = hindcast_anomalies

    # Define thresholds
    thresholds = {
        'P0': dataarray_to_dict(hindcast_anomalies_tp.min(['number', 'time'])),
        'P33': dataarray_to_dict(hindcast_anomalies_tp.quantile(1 / 3., ['number', 'time'])),
        'P66': dataarray_to_dict(hindcast_anomalies_tp.quantile(2 / 3., ['number', 'time'])),
        'P100': dataarray_to_dict(hindcast_anomalies_tp.max(['number', 'time']))
    }

    return thresholds

def convert_to_dict(tprate_hindcast_mean: xr.DataArray) -> dict:
    ''' Convert to dictionary for storage in CosmosDB
    Store per-point documents containing both mean and ensemble (ensemble averaged over time)
    ''' 
    hindcast_dict = {}
    for month in tprate_hindcast_mean.forecastMonth.values:
        # select for the month
        sel = tprate_hindcast_mean.sel(forecastMonth=month)

        # if it's a Dataset, pick the first data variable
        if isinstance(sel, xr.Dataset):
            first_var = list(sel.data_vars)[0]
            sel_da = sel[first_var]
        else:
            sel_da = sel

        # derive a mean DataArray for storing 'mean' per-point
        if set(('number', 'time')).intersection(sel_da.dims):
            try:
                mean_da_month = sel_da.mean(dim=[d for d in ('number', 'time') if d in sel_da.dims])
            except Exception:
                mean_da_month = sel_da
        else:
            mean_da_month = sel_da.squeeze()

        # if ensemble dim exists, prepare ensemble array; otherwise we'll store single-value list
        if 'number' in sel_da.dims:
            try:
                ens_da_month = sel_da.mean(dim='time') if 'time' in sel_da.dims else sel_da
            except Exception:
                ens_da_month = sel_da
        else:
            ens_da_month = None

        lat_vals = mean_da_month.latitude.values
        lon_vals = mean_da_month.longitude.values
        point_map = {}
        for i, latv in enumerate(lat_vals):
            for j, lonv in enumerate(lon_vals):
                # mean value
                mean_v = mean_da_month.values[i, j]
                mean_out = None if np.isnan(mean_v) else float(mean_v)

                # ensemble values for this point (one value per ensemble member) or single-value fallback
                if ens_da_month is not None:
                    try:
                        ens_vals = ens_da_month[:, i, j].values
                        ens_list = [None if np.isnan(x) else float(x) for x in ens_vals]
                    except Exception:
                        try:
                            single = ens_da_month.values[i, j]
                        except Exception:
                            single = ens_da_month.values
                        ens_list = [None if np.isnan(single) else float(single)]
                else:
                    ens_list = [mean_out]

                key = f"{float(latv):.6f},{float(lonv):.6f}"
                point_map[key] = {'mean': mean_out, 'ens': ens_list}

        hindcast_dict[int(month)] = point_map

    return hindcast_dict

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

        # Download drought hindcast
        print(f"Download rainfall hindcast for country {country_name}, period {year_start}-{year_end}")
        load.download_ecmwf_hindcast(filepath+filename, country_name, year_start, year_end)
        
        # Load and process hindcast data
        ds_hindcast = convert_to_mm_per_month(f'{filepath+filename}')
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

        print(f"Processing drought thresholds for country {country_name}, trigger model {trigger_model}")
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
            thresholds = calculate_threshold_data(tprate_hindcast, filtered_gdf)

        # Save to CosmosDB
        hindcast_dict = convert_to_dict(tprate_hindcast_mean)
        load.save_hindcast_data(country_name, hindcast_dict, trigger_model)
        print(f"Saved hindcast mean data to CosmosDB for country {country_name}")
        load.save_threshold_data(country_name, thresholds, trigger_model, climate_region_code)
        print(f"Saved thresholds data to CosmosDB for country {country_name}")


if __name__ == "__main__":
    add_drought_thresholds()