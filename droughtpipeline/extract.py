from droughtpipeline.secrets import Secrets
from droughtpipeline.settings import Settings
from droughtpipeline.data import (
    PipelineDataSets,
    ForecastDataUnit,
    RainfallDataUnit,
    RainfallClimateRegionDataUnit,
)
from droughtpipeline.load import Load
 
import os
from datetime import datetime, timedelta
import time
import geopandas as gpd
import pandas as pd
import xarray as xr
from rasterstats import zonal_stats
from rasterio.transform import from_origin
import rasterio
import logging
import itertools
from typing import List
import urllib.request
import ftplib
import copy
from dateutil.relativedelta import relativedelta
import json
from calendar import monthrange

import numpy as np

supported_sources = ["ECMWF"]


def slice_netcdf_file(nc_file: xr.Dataset, country_bounds: list):
    """Slice the netcdf file to the bounding box"""
    min_lon = country_bounds[0]  # Minimum longitude
    max_lon = country_bounds[2]  # Maximum longitude
    min_lat = country_bounds[1]  # Minimum latitude
    max_lat = country_bounds[3]  # Maximum latitude
    var_data = nc_file.sel(lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat))
    return var_data


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

    def prepare_ecmwf_data(self, country: str = None, debug: bool = False):
        """
        download ecmwf data to the extent of the country
        """
        if country is None:
            country = self.country
        logging.info(f"start preparing ECMWF seasonal forecast data for country {country}") 
        currentYear=datetime.today().strftime("%Y")
        currentMonth=datetime.today().strftime("%m")

        if debug:       
            currentYear=(datetime.today() - timedelta(days=31)).strftime("%Y")
            currentMonth=(datetime.today() - timedelta(days=31)).strftime("%m")
        # Download netcdf file
        logging.info(f"downloading ecmwf data ")
        

        #download_ecmwf_forecast(self,country, DATADIR, currentYear, currentMonth)
        try:
            self.load.download_ecmwf_forecast(
                country,
                self.inputPathGrid,
                currentYear, 
                currentMonth,
            )
        except FileNotFoundError:
            logging.warning(
                f"downloading ECMWF file failed"
            )     

        logging.info("finished downloading ECMWF data")

    def calculate_percentage_below_zero(self,ds, threshold):
        percentage = (ds.where(ds < 0).notnull().sum(dim='number') / ds.sizes['number']) 
        return (percentage > threshold).astype(int)

    def save_to_geotiff(self,data_array,country: str = None):
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
            output_file = f"{self.outputPathGrid}/drought_extent_{month}_month_{country}.tif"
            data = data_array.sel(forecastMonth=month).values

            with rasterio.open(
                output_file,
                'w',
                driver='GTiff',
                height=data.shape[0],
                width=data.shape[1],
                count=1,
                dtype=data.dtype,
                crs='+proj=latlong',
                transform=transform,
            ) as dst:
                dst.write(data, 1)
            # If month is 1, also write a file for month 0 we probably should not be doing this here. 
            # we discussed with IBF team that we will not upload 
            if month == 1:
                output_file_zero = f"{self.outputPathGrid}/drought_extent_0_month_{country}.tif"
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


   
    def extract_ecmwf_data(self, country: str = None, debug: bool = False):
        """
        extract seasonal rainfall forecastand extract it per climate region
        """
        if country is None:
            country = self.country   


        ### admin_level 
        logging.info(f"Extract ecmwf data for country {country}")
        
        admin_level_= self.settings.get_country_setting(country, "admin-levels")
 
        triggermodel=self.settings.get_country_setting(country, "trigger_model")['model']

        #trigger-on-minimum-probability: 0.6 # based on ensamble member probability compared against lower tercile 
        #trigger-on-minimum-probability-drought-extent: 0.6  # for drought extent using below average sesonal rain as a proxy
        #trigger-on-minimum-admin-area-in-drought-extent: 0.5 #for drought extent(grid) overlap with  admin polygons 
    
        trigger_probability=self.settings.get_country_setting(country, "trigger_model")["trigger-on-minimum-probability-drought-extent"] # for the ensamble mebers below average to define drought extent
        trigger_level=self.settings.get_country_setting(country, "trigger_model")["trigger-on-minimum-probability"] # for the ensamble mebers below tercile to define trigger status

        

        # the climate analysis might be happenig at admin level 1 or 2 
        '''
        filename_local = f"{self.confgPath}/{country}_climate_region_district_mapping.csv"          
        csv_data = pd.read_csv(filename_local)
        if admin_level_==1:
            merged_data = geofile.merge(csv_data, left_on='adm1_pcode', right_on='placeCode')  
        else:            
            merged_data = geofile.merge(csv_data, left_on='adm2_pcode', right_on='placeCode')
        '''
        logging.info("Extract seasonal forecast for each climate region")
                
                
        # get climate regions for each country         
        climateRegions=self.data.threshold_climateregion.get_climate_region_codes()

        #climateRegionPcodes=self.data.threshold_climateregion.get_data_unit(climate_region_code=1).pcodes
        
        
 

        for climateRegion in climateRegions:#merged_data['Climate_Region_code'].unique().tolist():
            pcodes=self.data.threshold_climateregion.get_data_unit(climate_region_code=climateRegion).pcodes
            admin_level_=self.data.threshold_climateregion.get_data_unit(climate_region_code=climateRegion).adm_level
            climateRegionName= self.data.threshold_climateregion.get_data_unit(climate_region_code=climateRegion).climate_region_name

            geofile=self.load.get_adm_boundaries(country,admin_level_)
            climateRegionPcodes=pcodes[f'{admin_level_}']

            filtered_gdf = geofile[geofile[f'adm{admin_level_}_pcode'].isin(climateRegionPcodes)]
            filtered_gdf['placeCode']= filtered_gdf[f'adm{admin_level_}_pcode']             
                      
                
                
            
            #filtered_gdf = merged_data[merged_data['Climate_Region_code'] == climateRegion]
            if filtered_gdf.empty:
                raise ValueError(f"No data matching {climateRegion} found in the geofile.")  
        
            # Get the extent of the filtered geofile    
            try:
                lon_min, lat_min, lon_max, lat_max = filtered_gdf.total_bounds  # [minx, miny, maxx, maxy]
          
            except ValueError as e:
                logging.error(f"Error in extracting extent of the filtered geofile: {e}")
             
            #sub_region (tuple): Subregion coordinates (North, West, South, East).
            
            sub_region = (lat_max, lon_min, lat_min, lon_max)

            

            # Load hindcast dataset and calculate mean
            ds_hindcast = xr.open_dataset(
                f'{self.inputPathGrid}/ecmwf_seas5_hindcast_monthly_tp.grib',
                engine='cfgrib',
                backend_kwargs={'time_dims': ('forecastMonth', 'time')}
            )
        
            # Load forecast data
            ds_forecast = xr.open_dataset(
                f'{self.inputPathGrid}/ecmwf_seas5_forecast_monthly_tp.grib',
                engine='cfgrib',
                backend_kwargs={'time_dims': ('forecastMonth', 'time')}
            )


            if triggermodel=='seasonal_rainfall_forecast':
                tprate_hindcast = ds_hindcast['tprate']
                tprate_hindcast_mean = tprate_hindcast.mean(['number', 'time'])
                    # Calculate anomalies
                anomalies = ds_forecast['tprate'] - tprate_hindcast_mean

                # Convert lead time into valid dates
                valid_time = [
                    pd.to_datetime(anomalies.time.values) + relativedelta(months=fcmonth - 1)
                    for fcmonth in anomalies.forecastMonth
                ]
                anomalies = anomalies.assign_coords(valid_time=('forecastMonth', valid_time))

                # Convert precipitation rates to accumulation
                numdays = [monthrange(dd.year, dd.month)[1] for dd in valid_time]
                anomalies = anomalies.assign_coords(numdays=('forecastMonth', numdays))

                anomalies_tp = anomalies * anomalies.numdays * 24 * 60 * 60 * 1000
                anomalies_tp.attrs['units'] = 'mm'
                anomalies_tp.attrs['long_name'] = 'Total precipitation anomaly'

            elif triggermodel=='seasonal_rainfall_forecast_3m':
                ########## for 3 month rolling mean
                seas5_forecast_3m = (
                    ds_forecast.shift(forecastMonth=-2)  # Shift data by 2 steps forward
                    .rolling(forecastMonth=3, min_periods=1)  # Apply rolling
                    .sum()  # Calculate mean for the rolling window
                )
                #ds_hindcast_3m = ds_hindcast.rolling(forecastMonth=3).mean()

                ds_hindcast_3m = (
                    ds_hindcast.shift(forecastMonth=-2)  # Shift data by 2 steps forward
                    .rolling(forecastMonth=3, min_periods=1)  # Apply rolling
                    .sum()  # Calculate mean for the rolling window
                )
                ds_hindcast_3m_hindcast_mean = ds_hindcast_3m.mean(['number','time'])
                anomalies = seas5_forecast_3m.tprate - ds_hindcast_3m_hindcast_mean.tprate  

                # Calculate number of days for each forecast month and add it as coordinate information to the data array
                vt = [ pd.to_datetime(anomalies.time.values) + relativedelta(months=fcmonth+1) for fcmonth in anomalies.forecastMonth]
                vts = [[thisvt+relativedelta(months=-mm) for mm in range(3)] for thisvt in vt]

                numdays = [np.sum([monthrange(dd.year,dd.month)[1] for dd in d3]) for d3 in vts]
                anomalies = anomalies.assign_coords(numdays=('forecastMonth',numdays))

                # Define names for the 3-month rolling archives, that give an indication over which months the average was built
                vts_names = ['{}{}{} {}'.format(d3[2].strftime('%b')[0],d3[1].strftime('%b')[0],d3[0].strftime('%b')[0], d3[0].strftime('%Y'))  for d3 in vts]
                anomalies = anomalies.assign_coords(valid_time=('forecastMonth',vts_names))        

                # Convert the precipitation accumulations based on the number of days
                anomalies_tp = anomalies * anomalies.numdays * 24 * 60 * 60 * 1000

                # Add updated attributes
                anomalies_tp.attrs['units'] = 'mm'
                anomalies_tp.attrs['long_name'] = 'SEAS5 3-monthly total precipitation ensemble mean anomaly for 6 lead-time months'

            else:
                raise ValueError(f"Trigger model {triggermodel} not supported")

            # extract annomalies for a specific region 

            sub_anomalies = self.subset_region(anomalies_tp, sub_region)

            #to determin aresas where the forecasted rain is below average for 70% of the ensemble members
            #percentage_below_average_per_gridcell = self.calculate_percentage_below_zero(sub_anomalies,trigger_probability)     
            percentage_below_average_per_gridcell = self.calculate_percentage_below_zero(anomalies_tp,trigger_probability)

            self.save_to_geotiff(percentage_below_average_per_gridcell,country)


            # Apply weighted mean for the region
            weights = np.cos(np.deg2rad(sub_anomalies.latitude))
            regional_mean = sub_anomalies.weighted(weights).mean(['latitude', 'longitude'])

            # Create dataframe for anomalies
            anomalies_df = regional_mean.drop_vars(['time', 'surface', 'numdays']).to_dataframe(name='anomaly')

            anomalies_df = anomalies_df.reset_index().drop('forecastMonth', axis=1).set_index(['valid_time', 'number']).unstack()

            anomalies_df = anomalies_df.reset_index()
            anomalies_df['valid_time'] = anomalies_df['valid_time'].dt.strftime('%b, %Y')


            # Calculate thresholds
            hindcast_sub = self.subset_region(tprate_hindcast, sub_region)
            hindcast_mean = hindcast_sub.weighted(weights).mean(['latitude', 'longitude'])
            hindcast_anomalies = hindcast_mean - hindcast_mean.mean(['number', 'time'])


            #convert precipitation accumulations in m/s to total precipitation in m.

            valid_time = [ pd.to_datetime(hindcast_anomalies.time.values[0]) + relativedelta(months=fcmonth-1) for fcmonth in hindcast_anomalies.forecastMonth]
            numdays = [monthrange(dd.year,dd.month)[1] for dd in valid_time]
            hindcast_anomalies = hindcast_anomalies.assign_coords(numdays=('forecastMonth',numdays))
            hindcast_anomalies_tp = hindcast_anomalies * hindcast_anomalies.numdays * 24 * 60 * 60 * 1000   

            thresholds = {
                'P0': hindcast_anomalies_tp.min(['number', 'time']),
                'P33': hindcast_anomalies_tp.quantile(1 / 3., ['number', 'time']),
                'P66': hindcast_anomalies_tp.quantile(2 / 3., ['number', 'time']),
                'P100': hindcast_anomalies_tp.max(['number', 'time'])
            }

            # Calculate trigger status
            dftemp=anomalies_df.anomaly 

            dftemp=anomalies_df.anomaly 
            dftemp.index=dftemp.index + 1
            forecastQ=dftemp.to_dict(orient='index')          


            forecastData={
                'çlimateRegion':climateRegion,
                'tercile_lower':thresholds['P33'].drop_vars(['quantile','numdays']).to_series().to_dict(),
                'tercile_upper':thresholds['P66'].drop_vars(['quantile','numdays']).to_series().to_dict(),
                'forecast':forecastQ
                }
                      

            tercile_seasonal_prc_df = thresholds['P33'].drop_vars(['quantile', 'numdays']).to_dataframe(name='p33')
        
            tercile_seasonal_prc_df = tercile_seasonal_prc_df.reset_index().drop('forecastMonth', axis=1)

            dftemp=anomalies_df.anomaly 

            tercile_seasonal_prc_df['triggerForecast'] = (dftemp.iloc[:, :51].lt(tercile_seasonal_prc_df.iloc[:, 0], axis=0).sum(axis=1) / 51) 

            tercile_seasonal_prc_df['triggerStatus'] = tercile_seasonal_prc_df['triggerForecast'].gt(trigger_level)

            # Add the lead time index as months (e.g., Month 1, Month 2, etc.)
            #tercile_seasonal_prc_df.index = [f"Month {i+1}" for i in tercile_seasonal_prc_df.index]

            # Convert to dictionary
            tercile_seasonal_prc_df.index = range(1, len(tercile_seasonal_prc_df) + 1)
            data_dict = tercile_seasonal_prc_df[['triggerForecast','triggerStatus']].to_dict(orient="index")

                        # Save to JSON
            json_file_path = f"{self.outputPathGrid}/climateregion_{climateRegion}.json"

            with open(json_file_path, "w") as json_file:
                json.dump(data_dict, json_file, indent=4)
            logging.info(f"finished extraction of rainfall forecast for climate region{climateRegion}")

            for leadtime in forecastData['tercile_lower'].keys():

                
                for pcode in filtered_gdf.placeCode.unique():
                    self.data.rainfall_admin.upsert_data_unit(
                        ForecastDataUnit(
                            climate_region_code=climateRegion,
                            climate_region_name=climateRegionName,
                            pcode=pcode,
                            lead_time=leadtime,
                            tercile_lower=forecastData['tercile_lower'][leadtime],
                            tercile_upper=forecastData['tercile_upper'][leadtime],
                            forecast=forecastData['forecast'][leadtime],
                            triggered=data_dict[leadtime]['triggerStatus'],
                            likelihood=data_dict[leadtime]['triggerForecast'],
                        )
                    )
                    # 
                    #If LEADTIME is 1, also write a file for month 0 we probably should not be doing this here. 
                    # we discussed with IBF team that we will not upload  FOR NOW CREATING A FILE FOR LEADTIME 0
                    if leadtime == 1:
                        self.data.rainfall_admin.upsert_data_unit(
                        ForecastDataUnit(
                            climate_region_code=climateRegion,
                            climate_region_name=climateRegionName,
                            pcode=pcode,
                            lead_time=0,
                            tercile_lower=forecastData['tercile_lower'][leadtime],
                            tercile_upper=forecastData['tercile_upper'][leadtime],
                            forecast=forecastData['forecast'][leadtime],
                            triggered=data_dict[leadtime]['triggerStatus'],
                            likelihood=data_dict[leadtime]['triggerForecast'],
                        )
                    )
 





        

