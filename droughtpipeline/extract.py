from droughtpipeline.secrets import Secrets
from droughtpipeline.settings import Settings
from droughtpipeline.data import (
    PipelineDataSets,
    ForecastDataUnit,
    RainfallDataUnit,
    RainfallClimateRegionDataUnit,
)
from droughtpipeline.load import Load
from droughtpipeline.utils import (
    replace_year_month, 
    convert_to_mm_per_month,
    get_extent_shp,
)
import os
from datetime import datetime
import geopandas as gpd
import pandas as pd
import xarray as xr
from rasterstats import zonal_stats
from rasterio.transform import from_origin
from rasterio.crs import CRS
import rasterio
import logging
from dateutil.relativedelta import relativedelta
from calendar import monthrange
import rioxarray
import numpy as np
import warnings
from rasterio.mask import mask

warnings.simplefilter("ignore", category=RuntimeWarning)

supported_sources = ["ECMWF"]

class Extract:
    """Extract river discharge data from external sources"""

    def __init__(
        self,
        settings: Settings = None,
        secrets: Secrets = None,
        data: PipelineDataSets = None,
    ):
        self.source = None
        self.country = None
        self.secrets = None
        self.settings = None
        self.inputPathGrid = "./data/input"
        self.outputPathGrid = "./data/output"
        self.confgPath = "./config"
        self.load = Load()
        if not os.path.exists(self.inputPathGrid):
            os.makedirs(self.inputPathGrid)
        if not os.path.exists(self.outputPathGrid):
            os.makedirs(self.outputPathGrid)
        if settings is not None:
            self.set_settings(settings)
            self.load.set_settings(settings)
        if secrets is not None:
            self.set_secrets(secrets)
            self.load.set_secrets(secrets)
        self.data = data

    def set_settings(self, settings):
        """Set settings"""
        if not isinstance(settings, Settings):
            raise TypeError(f"invalid format of settings, use settings.Settings")
        self.settings = settings

    def set_secrets(self, secrets):
        """Set secrets based on the data source"""
        if not isinstance(secrets, Secrets):
            raise TypeError(f"invalid format of secrets, use secrets.Secrets")
        self.secrets = secrets

    def set_source(self, source_name, secrets: Secrets = None):
        """Set the data source"""
        if source_name is not None:
            if source_name not in supported_sources:
                raise ValueError(
                    f"Source {source_name} is not supported."
                    f"Supported sources are {', '.join(supported_sources)}")
            else:
                self.source = source_name
                self.inputPathGrid = os.path.join(self.inputPathGrid, self.source)
        else:
            raise ValueError(
                f"Source not specified; provide one of {', '.join(supported_sources)}"
            )        
        if secrets is not None:
            self.set_secrets(secrets)
        elif self.secrets is not None:
            self.set_secrets(self.secrets)
        else:
            raise ValueError(f"Set secrets before setting source")
        return self

    def get_data(self, country: str, source: str = None):
        """Get river discharge data from source and return AdminDataSet"""
        if source is None and self.source is None:
            raise RuntimeError("Source not specified, use set_source()")
        elif self.source is None and source is not None:
            self.source = source
        self.country = country
        if self.source == "ECMWF":
            self.prepare_ecmwf_data()
            self.extract_ecmwf_data()

    def prepare_ecmwf_data(self, country: str = None, debug: bool = False, datestart: datetime = None):
        """
        download ecmwf data to the extent of the country
        """
        if country is None:
            country = self.country
        logging.info(f"start preparing ECMWF seasonal forecast data for country {country}") 
        
        current_year = datestart.strftime('%Y')
        current_month = datestart.strftime("%m")

        # Download netcdf file
        logging.info(f"downloading ecmwf data ")
        try:
            self.load.download_ecmwf_forecast(
                country,
                self.inputPathGrid,
                current_year, 
                current_month,
            )
        except FileNotFoundError:
            logging.warning(
                f"downloading ECMWF file failed"
            )     

        logging.info("finished downloading ECMWF data")

    def calculate_percentage_below_zero(self,ds, threshold):
        percentage = (ds.where(ds < 0).notnull().sum(dim='number') / ds.sizes['number']) 
        return (percentage > threshold).astype(int)

    def save_to_geotiff(self,data_array,country: str = None, prefix: str = None):
        """
        Save each forecast month of the data array to a separate GeoTIFF file.

        Parameters:
            data_array (xarray.DataArray): The data array to save.
            output_dir (str): The directory to save the GeoTIFF files.
            prefix (str): The prefix for the GeoTIFF file names.
        """
        # Get the coordinates and dimensions
        latitudes = data_array.latitude.values
        longitudes = data_array.longitude.values
        forecast_months = data_array.forecastMonth.values

        # Define the transform
    
        transform = from_origin(longitudes[0], latitudes[0], longitudes[1] - longitudes[0], latitudes[0] - latitudes[1])

        # Loop through each forecast month and save to a separate GeoTIFF file
        for i, month in enumerate(forecast_months):
            lead_time=month-1
            output_file = f"{self.outputPathGrid}/{prefix}_{lead_time}-month_{country}.tif"
            data = data_array.sel(forecastMonth=month).values

            with rasterio.open(
                output_file,
                'w',
                driver='GTiff',
                height=data.shape[0],
                width=data.shape[1],
                count=1,
                dtype=data.dtype,
                crs=CRS.from_epsg(4326),
                transform=transform,
            ) as dst:
                dst.write(data, 1)
            # If month is 1, also write a file for month 0 we probably should not be doing this here. 
            # we discussed with IBF team that we will not upload 
            ''' 
            if month == 1:
                output_file_zero = f"{self.outputPathGrid}/{prefix}_0-month_{country}.tif"
                data_zero = data_array.sel(forecastMonth=month).values

                with rasterio.open(
                    output_file_zero,
                    'w',
                    driver='GTiff',
                    height=data_zero.shape[0],
                    width=data_zero.shape[1],
                    count=1,
                    dtype=data_zero.dtype,
                    crs='+proj=latlong',
                    transform=transform,
                ) as dst_zero:
                    dst_zero.write(data_zero, 1)

            ''' 


    def subset_region(self,ds, region, latname='latitude', lonname='longitude'):
        lon1 = region[1] % 360
        lon2 = region[3] % 360
        if lon2 >= lon1:
            mask_lon = (ds[lonname] <= lon2) & (ds[lonname] >= lon1)
        else:
            mask_lon = (ds[lonname] <= lon2) | (ds[lonname] >= lon1)

        mask = (ds[latname] <= region[0]) & (ds[latname] >= region[2]) & mask_lon
        subset = ds.where(mask, drop=True)

        if lon2 < lon1:
            subset[lonname] = (subset[lonname] + 180) % 360 - 180
            subset = subset.sortby(subset[lonname])

        return subset
    

    def process_forecast_data(self, country: str, triggermodel: str):
        """
        Process forecast data using hindcast mean
        
        Parameters:
            country (str): Country code
            triggermodel (str): Trigger model type
            
        Returns:
            tuple: (forecast data, anomalies, valid_time, numdays, trigger_df)
        """
        logging.info(f"Processing forecast data for country {country}")
        
        # Get precalculated hindcast mean from CosmosDB
        tprate_hindcast = self.load.get_pipeline_data(
            data_type="seasonal-rainfall-hindcast",
            country=country
        )

        # Load forecast data
        ds_forecast = convert_to_mm_per_month(
            f'{self.inputPathGrid}/ecmwf_seas5_forecast_monthly_tp.grib'
        )
        
        # Process based on trigger model
        if triggermodel == 'seasonal_rainfall_forecast':
            tprate_forecast = ds_forecast['tprate']
            
            # Convert lead time into valid dates
            valid_time = [
                pd.to_datetime(tprate_forecast.time.values) + relativedelta(months=fcmonth - 1)
                for fcmonth in tprate_forecast.forecastMonth
            ]
            tprate_hindcast_mean = tprate_hindcast.get_data_unit(model=triggermodel)
            hindcast = self.__hindcast_list_to_xarray(tprate_hindcast_mean)
            anomalies = ds_forecast['tprate'] - hindcast["hindcast_mean"]
            
            # Convert precipitation rates to accumulation
            numdays = [monthrange(dd.year, dd.month)[1] for dd in valid_time]
            anomalies = anomalies.assign_coords(valid_time=('forecastMonth', valid_time))
            anomalies = anomalies.assign_coords(numdays=('forecastMonth', numdays))
            anomalies_tp = anomalies
            anomalies_tp.attrs['units'] = 'mm'
            anomalies_tp.attrs['long_name'] = 'Total precipitation anomaly'
            
        elif triggermodel == 'seasonal_rainfall_forecast_3m':
            seas5_forecast_3m = (
                ds_forecast.shift(forecastMonth=-2)
                .rolling(forecastMonth=3, min_periods=1)
                .sum()
            )
            tprate_forecast = seas5_forecast_3m['tprate']

            tprate_hindcast_mean = tprate_hindcast.get_data_unit(model=triggermodel)
            hindcast = self.__hindcast_list_to_xarray(tprate_hindcast_mean)
            anomalies = seas5_forecast_3m.tprate - hindcast["hindcast_mean"]
            
            # Calculate number of days for each forecast month
            vt = [pd.to_datetime(tprate_forecast.time.values) + relativedelta(months=fcmonth+1) 
                  for fcmonth in tprate_forecast.forecastMonth]
            vts = [[thisvt+relativedelta(months=-mm) for mm in range(3)] for thisvt in vt]
            numdays = [np.sum([monthrange(dd.year, dd.month)[1] for dd in d3]) for d3 in vts]
            
            # Convert lead time into valid dates
            valid_time = [
                pd.to_datetime(tprate_forecast.time.values) + relativedelta(months=fcmonth - 1)
                for fcmonth in tprate_forecast.forecastMonth
            ]
            
            anomalies = anomalies.assign_coords(numdays=('forecastMonth', numdays))
            anomalies = anomalies.assign_coords(valid_time=('forecastMonth', valid_time))
            anomalies_tp = anomalies
            anomalies_tp.attrs['units'] = 'mm'
            anomalies_tp.attrs['long_name'] = 'SEAS5 3-monthly total precipitation ensemble mean anomaly for 6 lead-time months'
        else:
            raise ValueError(f"Trigger model {triggermodel} not supported")
        
        return tprate_forecast, anomalies_tp, valid_time, numdays
   
    def extract_ecmwf_data(self, country: str = None, debug: bool = False, datestart: datetime = None):
        """
        Extract seasonal rainfall forecast and extract it per climate region
        Refactored to separate hindcast and forecast processing
        """
        if country is None:
            country = self.country   

        current_year = datestart.year
        current_month = datestart.month
        data_timestamp = replace_year_month(datetime.now(), current_year, current_month)
        
        ### admin_level 
        logging.info(f"Extract ecmwf data for country {country}")
        admin_level_ = self.settings.get_country_setting(country, "admin-levels")
        triggermodel = self.settings.get_country_setting(country, "trigger_model")['model']
        trigger_on_minimum_probability = self.settings.get_country_setting(
            country, "trigger_model")['trigger-on-minimum-probability']
        trigger_on_minimum_admin_area_in_drought_extent = self.settings.get_country_setting(
            country, "trigger_model")['trigger-on-minimum-admin-area-in-drought-extent']     
        
        if debug:
            scenario = os.getenv("SCENARIO", "Forecast")
            logging.info(f"scenario: {scenario}")
            if scenario == "NoWarning":
                trigger_on_minimum_probability = 0.99
            elif scenario == "Warning":
                trigger_on_minimum_probability = 0.3
        
        # Process forecast data
        logging.info("Processing forecast data...")
        tprate_forecast, anomalies_tp, valid_time, numdays = self.process_forecast_data(
            country, triggermodel
        )
        
        ########################### Rainfall layer for IBF portal
        logging.info("Preparing rainfall forecast mean for IBF portal...")
        tprate_forecast_mean = tprate_forecast.mean(['number'])
        tprate_forecast_mean = tprate_forecast_mean.assign_coords(valid_time=('forecastMonth', valid_time))
        tprate_forecast_mean = tprate_forecast_mean.assign_coords(numdays=('forecastMonth', numdays))
        tprate_forecast_mean.attrs['units'] = 'mm'

        # Step 4: Process each climate region
        logging.info("Processing climate regions...")
        for climateRegion in self.data.threshold_climateregion.get_climate_region_codes():
            pcodes=self.data.threshold_climateregion.get_data_unit(
                climate_region_code=climateRegion).pcodes
            admin_level_=self.data.threshold_climateregion.get_data_unit(
                climate_region_code=climateRegion).adm_level
            climateRegionName= self.data.threshold_climateregion.get_data_unit(
                climate_region_code=climateRegion).climate_region_name
            geofile=self.load.get_adm_boundaries(country,admin_level_)
            climateRegionPcodes=pcodes[f'{admin_level_}']
            filtered_gdf = geofile[geofile[f'adm{admin_level_}_pcode'].isin(climateRegionPcodes)]
            filtered_gdf['placeCode']= filtered_gdf[f'adm{admin_level_}_pcode']          
            
            if filtered_gdf.empty:
                raise ValueError(f"No data matching {climateRegion} found in the geofile.")  

            # extract annomalies for a specific region 
            sub_region = get_extent_shp(filtered_gdf)
            sub_anomalies = self.subset_region(anomalies_tp, sub_region)

            # Apply weighted mean for the region
            weights = np.cos(np.deg2rad(sub_anomalies.latitude))
            regional_mean = sub_anomalies.weighted(weights).mean(['latitude', 'longitude'])

            # Create dataframe for anomalies
            regional_mean_named = regional_mean.drop_vars(['time', 'surface', 'numdays']).rename('anomaly')
            anomalies_df = regional_mean_named.to_dataframe()
            anomalies_df = anomalies_df.reset_index().drop('forecastMonth', axis=1)
            
            # Aggregate duplicates by mean to avoid unstack error
            anomalies_df = anomalies_df.groupby(['valid_time', 'number']).mean().unstack()
            anomalies_df = anomalies_df.reset_index()
            anomalies_df['valid_time'] = anomalies_df['valid_time'].dt.strftime('%b, %Y')

            # Get precalculated thresholds from CosmosDB
            threshold_dataset = self.load.get_pipeline_data(
                data_type="seasonal-rainfall-threshold",
                country=country
            )
            threshold_du = threshold_dataset.get_data_unit(
                climate_region_code=climateRegion,
                model=triggermodel
            )

            # Calculate trigger status
            dftemp=anomalies_df.anomaly        
            dftemp.index=dftemp.index + 1
            forecastQ=dftemp.to_dict(orient='index')
            forecastData={
                'climateRegion':climateRegion,
                'tercile_lower':threshold_du.thresholds['P33'],
                'tercile_upper':threshold_du.thresholds['P66'],
                'forecast':forecastQ
                }
            tercile_seasonal_prc_df = pd.Series(threshold_du.thresholds["P33"], name='p33').rename_axis('forecastMonth').to_frame()
            tercile_seasonal_prc_df = tercile_seasonal_prc_df.reset_index().drop('forecastMonth', axis=1)
            dftemp=anomalies_df.anomaly 
            tercile_seasonal_prc_df['triggerForecast'] = (dftemp.iloc[:, :51].lt(tercile_seasonal_prc_df.iloc[:, 0], axis=0).sum(axis=1) / 51) 
            tercile_seasonal_prc_df['triggerStatus'] = tercile_seasonal_prc_df['triggerForecast'].gt(trigger_on_minimum_probability)
            tercile_seasonal_prc_df.index = range(1, len(tercile_seasonal_prc_df)+1 )
            data_dict = tercile_seasonal_prc_df[['triggerForecast','triggerStatus']].to_dict(orient="index")  

            for month in forecastData['tercile_lower'].keys():
                if not isinstance(month, int):
                    month_int = int(month)
                lead_time = month_int - 1
                lower_tercile_file = f"{self.outputPathGrid}/rlower_tercile_probability_{lead_time}-month_{country}.tif"   

                # Open the TIF file as an xarray object
                rlower_tercile_probability = rioxarray.open_rasterio(lower_tercile_file)
                gdf1 = filtered_gdf
                clipped_regional_mean = rlower_tercile_probability.rio.clip(gdf1.geometry, gdf1.crs, drop=True, all_touched=True)
                likelihood = round(np.nanmedian(clipped_regional_mean.values),2)
                binary_clipped_regional_mean = (
                    clipped_regional_mean > trigger_on_minimum_probability
                    ).astype(int)
                anomalies_df = binary_clipped_regional_mean.to_dataframe(name='anomaly')
                percentage_greater_than_zero = (anomalies_df.anomaly.values > 0).sum() / anomalies_df.anomaly.values.size  

                if percentage_greater_than_zero > trigger_on_minimum_admin_area_in_drought_extent:
                    triggered=1
                else:
                    triggered=0

                logging.info(f"upserting data for climate region {climateRegion} for month {month} trigger status {triggered} likelihood {likelihood}" )
                self.data.rainfall_climateregion.timestamp = data_timestamp
                self.data.rainfall_climateregion.upsert_data_unit(
                        ForecastDataUnit(
                            climate_region_code=climateRegion,
                            climate_region_name=climateRegionName,
                            lead_time=lead_time,# theck this -1
                            tercile_lower=forecastData['tercile_lower'][month], #data from CosmosDB, keys must be string
                            tercile_upper=forecastData['tercile_upper'][month], #data from CosmosDB, keys must be string
                            forecast=forecastData['forecast'][month_int],
                            triggered=triggered,# data_dict[month]['triggerStatus'],
                            likelihood=likelihood,# data_dict[month]['triggerForecast'],
                        )
                    )
            logging.info(f"finished extraction of rainfall forecast for climate region{climateRegion}")
    
    @staticmethod
    def __hindcast_list_to_xarray(hindcast_du):
        # Flatten all points from all HindcastDataUnit objects
        points = []
        # for hdu in hindcast_du_list:
        if hindcast_du.seasonal_rainfall:
            points.extend(hindcast_du.seasonal_rainfall)
        lats = sorted(set(p["lat"] for p in points))
        lons = sorted(set(p["lon"] for p in points))
        nlat = len(lats)
        nlon = len(lons)
        nens = len(points[0]["hindcast_ensemble"])
        # Create empty arrays
        ensemble = np.full((nlat, nlon, nens), np.nan)
        mean = np.full((nlat, nlon), np.nan)
        # Fill arrays
        lat_idx = {v: i for i, v in enumerate(lats)}
        lon_idx = {v: i for i, v in enumerate(lons)}
        for p in points:
            i = lat_idx[p["lat"]]
            j = lon_idx[p["lon"]]
            ensemble[i, j, :] = p["hindcast_ensemble"]
            mean[i, j] = p["hindcast_mean"]
        # Build xarray Dataset
        ds = xr.Dataset(
            {
                "hindcast_ensemble": (["lat", "lon", "ensemble"], ensemble),
                "hindcast_mean": (["lat", "lon"], mean),
            },
            coords={
                "lat": lats,
                "lon": lons,
            }
        )
        return ds
