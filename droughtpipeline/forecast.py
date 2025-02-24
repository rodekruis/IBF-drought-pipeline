from droughtpipeline.secrets import Secrets
from droughtpipeline.settings import Settings
from droughtpipeline.data import (
    PipelineDataSets,
    ForecastDataUnit,
    DroughtForecast
)

from droughtpipeline.load import Load
from datetime import datetime, date, timedelta
from typing import List
from shapely import Polygon
from shapely.geometry import shape
import pandas as pd
from rasterstats import zonal_stats
import os
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
from rasterio.features import shapes
import shutil


def merge_rasters(raster_filepaths: list) -> tuple:
    """Merge rasters into a single one, return the merged raster and its metadata"""
    if len(raster_filepaths) > 0:
        with rasterio.open(raster_filepaths[0]) as src:
            out_meta = src.meta.copy()
    mosaic, out_trans = merge(raster_filepaths)
    out_meta.update(
        {
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_trans,
        }
    )
    return mosaic, out_meta


def clip_raster(
    raster_filepath: str, shapes: List[Polygon], invert: bool = False
) -> tuple:
    """Clip raster with a list of polygons, return the clipped raster and its metadata"""
    crop = True if not invert else False
    with rasterio.open(raster_filepath) as src:
        outImage, out_transform = mask(src, shapes, crop=crop, invert=invert)
        outMeta = src.meta.copy()
    outMeta.update(
        {
            "driver": "GTiff",
            "height": outImage.shape[1],
            "width": outImage.shape[2],
            "transform": out_transform,
            "compress": "lzw",
        }
    )
    return outImage, outMeta


def classify_alert(
    triggered: str,
    likelihood,
    classify_alert_on: str, 
    alert_on_minimum_probability,
) -> str:
    """
    Classify alert based on configuration:
    - 'probability': Classify based on minimum probability thresholds.
    - 'disable': Classify based on triggered flag and highest probability threshold.
    """
    alert_class = "no"

    if classify_alert_on == "probability":
        if not isinstance(alert_on_minimum_probability, dict):
            raise ValueError(
                "For classification by probability, 'alert_on_minimum_probability' must be a dictionary."
            )

        # Sort probabilities from smallest to largest
        sorted_probabilities = dict(
            sorted(alert_on_minimum_probability.items(), key=lambda item: item[1])
        )

        # Determine alert class based on probability thresholds
        probability = likelihood#_per_return_period.get(alert_on_return_period)
        if probability is None:
            raise ValueError(
                "likelihood data missing ."
            )

        for class_, min_probability in sorted_probabilities.items():
            if probability >= min_probability:
                alert_class = class_

    elif classify_alert_on == "disable":
        if triggered and isinstance(alert_on_minimum_probability, dict):
            # Return the class with the highest minimum probability
            alert_class = max(
                alert_on_minimum_probability, key=alert_on_minimum_probability.get
            )

    else:
        raise ValueError(
            "Invalid value for 'classify_alert_on'. Expected 'probability' or 'disable'."
        )

    return alert_class


class Forecast:
    """
    Forecast flood events based on river discharge data
    """

    def __init__(
        self,
        settings: Settings = None,
        secrets: Secrets = None,
        data: PipelineDataSets = None,
    ):
        self.secrets = None
        self.settings = None
        self.set_settings(settings)
        self.set_secrets(secrets)
        self.load = Load(settings=self.settings, secrets=self.secrets)
        self.input_data_path: str = "data/input"
        self.output_data_path: str = "data/output"
        self.drought_extent_raster: str = self.output_data_path + "/drought_extent.tif" # changed to drought_extent_raster     
        self.pop_raster: str = self.input_data_path + "/population_density.tif"
        self.aff_pop_raster: str = self.output_data_path + "/affected_population.tif"
        self.data = data

    def set_settings(self, settings):
        """Set settings"""
        if not isinstance(settings, Settings):
            raise TypeError(f"invalid format of settings, use settings.Settings")
        #settings.check_settings(["global_flood_maps_url"]) #not needed for drought pipeline 
        self.settings = settings

    def set_secrets(self, secrets):
        """Set secrets based on the data source"""
        if not isinstance(secrets, Secrets):
            raise TypeError(f"invalid format of secrets, use secrets.Secrets")
        secrets.check_secrets([])
        self.secrets = secrets

    def compute_forecast(self):
        """
        Forecast floods based on river discharge data
        """
        os.makedirs(self.input_data_path, exist_ok=True)
        os.makedirs(self.output_data_path, exist_ok=True)
        self.compute_forecast_admin()
        

    def compute_forecast_admin(self):
        """
        Forecast drought per climate region based on different models for now ecmwf seasonal rainfall forecast is implmented  
        1. determine if trigger level is reached, with which probability, and alert class
        2. compute drought extent
        3. compute people affected
        """
        self.__compute_triggers()
        if self.data.forecast_admin.is_any_triggered():
            self.__compute_affected_pop()

    def __compute_triggers(self):
        """Determine if trigger level is reached, its probability, and the alert class"""

        country = self.data.threshold_climateregion.country

        # remove this line if we are uploading for mulltiple triggers 

        trigger_on_lead_time = self.settings.get_country_setting(country, "trigger-on-lead-time" )

        #trigger_on_return_period = self.settings.get_country_setting(country, "trigger-on-return-period")

        trigger_on_minimum_probability = self.settings.get_country_setting(     country, "trigger_model")['trigger-on-minimum-probability']

        classify_alert_on = self.settings.get_country_setting(country, "classify-alert-on")

        ''' 

        alert_on_return_period = self.settings.get_country_setting(
            country, "alert-on-return-period"
        )

        '''        

        alert_on_minimum_probability = self.settings.get_country_setting(
            country, "alert-on-minimum-probability"
        )

        climate_regions= {}

        current_month = date.today().strftime('%b')  # 'Feb' for February check if this can be passed from settings 
 
 
        
        for entry in self.settings.get_country_setting(country,"Climate_Region"):
 
            climateRegionCode=entry['climate-region-code'] 
            for key, value in entry['leadtime'][current_month][0].items():
                if climateRegionCode is not None:
                    climate_regions[climateRegionCode] = {
                            'climateregionname': entry['name'],
                            'season': key,
                            'leadtime': int(value.split('-')[0])}
                else:
                    raise ValueError("climate region not defined in config file ")
 
 


        #for climateregion in self.data.rainfall_climateregion.get_climateregions(): #change to rainfall_climateregion
        adm_level_= self.settings.get_country_setting(country, "admin-levels") 
        adm_level=adm_level_ #if multiple admin levels are defined in cofig file reflect the change here 
   

        for climateregion,climateregionVars in climate_regions.items():
            lead_time=climateregionVars['leadtime']
            season=climateregionVars['season']
            
            
            pcodes=self.data.threshold_climateregion.get_data_unit(climate_region_code=climateregion).pcodes

            #climateRegionName= self.data.threshold_climateregion.get_data_unit(climate_region_code=climateRegion).climate_region_name	

            climateRegionPcodes=pcodes[f'{adm_level_}']
            
            #rainfall_data_unit = self.data.forecast_admin.get_data_unit( climateregion, lead_time)
            #rainfall_data_unit1 = self.data.rainfall_admin.get_data_unit(climateregion, lead_time)
            
            
            for pcode in climateRegionPcodes:# rainfall_data_unit.get_pcodes():
                rainfall_data_unit = self.data.rainfall_admin.get_data_unit(pcode, lead_time+1)
                print(rainfall_data_unit)
                print("###################")
                print(pcode)
                rain_data_unit = rainfall_data_unit#.get_data_unit(pcode)   
                tercile_lower=rain_data_unit.tercile_lower 
                #rainfall_forecast=rain_data_unit.rainfall_forecast
                likelihood=rain_data_unit.likelihood
                triggered=rain_data_unit.triggered,       
                #adm_level = rain_data_unit.adm_level

                print(adm_level,tercile_lower,likelihood,triggered)

                alert_class = classify_alert(
                    triggered,
                    likelihood,
                    classify_alert_on,
                    alert_on_minimum_probability,
                )

                forecast_data_unit = ForecastDataUnit(
                    pcode=pcode,
                    adm_level=adm_level,
                    climate_region_code=climateregion,
                    season=season,
                    lead_time=lead_time,                
                    triggered=triggered,
                    alert_class=alert_class,
                    likelihood=likelihood,
                    tercile_lower=tercile_lower,
                    #rainfall_forecast=rainfall_forecast,

                )
                self.data.forecast_admin.upsert_data_unit(forecast_data_unit)



    def __compute_affected_pop_raster(self):
        """Compute affected population raster given a flood extent"""
        country = self.data.forecast_admin.country
        # get population density raster
        self.load.get_population_density(country, self.pop_raster)

        flood_shapes = []
        for lead_time in self.data.forecast_admin.get_lead_times():
            flood_raster_lead_time = self.output_data_path + f"/drought_extent_{lead_time}_month.tif" 
            
            aff_pop_raster_lead_time = self.aff_pop_raster.replace(
                ".tif", f"_{lead_time}.tif"
            )
            if os.path.exists(aff_pop_raster_lead_time):
                os.remove(aff_pop_raster_lead_time)

            with rasterio.open(flood_raster_lead_time) as dataset:
                # Read the dataset's valid data mask as a ndarray.
                image = dataset.read(1).astype(np.float32)
                image[image >= self.settings.get_setting("minimum_for_drought_extent")] = 1
                rasterio_shapes = shapes(
                    image, transform=dataset.transform
                )  # convert flood extent raster to vector (list of shapes)
                for geom, val in rasterio_shapes:
                    if val >= self.settings.get_setting("minimum_for_drought_extent"):
                        flood_shapes.append(shape(geom))
            # clip population density raster with flood shapes and save the result
            if len(flood_shapes) > 0:
                affected_pop_raster, affected_pop_meta = clip_raster(
                    self.pop_raster, flood_shapes
                )
                with rasterio.open(
                    aff_pop_raster_lead_time, "w", **affected_pop_meta
                ) as dest:
                    dest.write(affected_pop_raster)

    def __compute_affected_pop(self):
        """Compute affected population given a flood extent"""

        # calculate affected population raster
        self.__compute_affected_pop_raster()

        # calculate affected population per admin division
        for adm_lvl in [self.data.forecast_admin.adm_levels]:
            # get adm boundaries
            gdf_adm = self.load.get_adm_boundaries(
                self.data.forecast_admin.country, adm_lvl
            )
            gdf_aff_pop, gdf_pop = pd.DataFrame(), pd.DataFrame()

            for lead_time in self.data.forecast_admin.get_lead_times():
                aff_pop_raster_lead_time = self.aff_pop_raster.replace(
                    ".tif", f"_{lead_time}.tif"
                )
                if os.path.exists(aff_pop_raster_lead_time):
                    # perform zonal statistics on affected population raster
                    with rasterio.open(aff_pop_raster_lead_time) as src:
                        raster_array = src.read(1)
                        raster_array[raster_array < 0.0] = 0.0
                        transform = src.transform

                    stats = zonal_stats(
                        gdf_adm,
                        raster_array,
                        affine=transform,
                        stats=["sum"],
                        all_touched=True,
                        nodata=0.0,
                    )
                    gdf_aff_pop = pd.concat([gdf_adm, pd.DataFrame(stats)], axis=1)
                    gdf_aff_pop.index = gdf_aff_pop[f"adm{adm_lvl}_pcode"]

                    # perform zonal statistics on population density raster (to compute % aff pop)
                    with rasterio.open(self.pop_raster) as src:
                        raster_array = src.read(1)
                        raster_array[raster_array < 0.0] = 0.0
                        transform = src.transform
                    stats = zonal_stats(
                        gdf_adm,
                        raster_array,
                        affine=transform,
                        stats=["sum"],
                        all_touched=True,
                        nodata=0.0,
                    )
                    gdf_pop = pd.concat([gdf_adm, pd.DataFrame(stats)], axis=1)
                    gdf_pop.index = gdf_pop[f"adm{adm_lvl}_pcode"]

                # add affected population to forecast data units
                for forecast_data_unit in self.data.forecast_admin.get_data_units(
                    adm_level=adm_lvl, lead_time=lead_time
                ):
                    if forecast_data_unit.triggered:
                        try:
                            pop_affected = int(
                                gdf_aff_pop.loc[forecast_data_unit.pcode, "sum"]
                            )
                        except (ValueError, TypeError, KeyError):
                            pop_affected = 0
                        forecast_data_unit.pop_affected = pop_affected
                        try:
                            forecast_data_unit.pop_affected_perc = (
                                float(
                                    pop_affected
                                    / gdf_pop.loc[forecast_data_unit.pcode, "sum"]
                                )
                                * 100.0
                            )

                        except (ValueError, TypeError, KeyError):
                            forecast_data_unit.pop_affected_perc = 0.0

