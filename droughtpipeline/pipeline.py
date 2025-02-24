from droughtpipeline.data import AdminDataSet, ClimateRegionDataSet
from droughtpipeline.extract import Extract
from droughtpipeline.forecast import Forecast
from droughtpipeline.load import Load
from droughtpipeline.secrets import Secrets
from droughtpipeline.settings import Settings
from droughtpipeline.data import PipelineDataSets
from datetime import datetime, date, timedelta
import logging
import json

logger = logging.getLogger()
logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("requests_oauthlib").setLevel(logging.WARNING)


class Pipeline:
    """Base class for flood data pipeline"""

    def __init__(self, settings: Settings, secrets: Secrets, country: str):
        self.settings = settings
        if country not in [c["name"] for c in self.settings.get_setting("countries")]:
            raise ValueError(f"No config found for country {country}")
        self.country = country
        self.load = Load(settings=settings, secrets=secrets)
        self.data = PipelineDataSets(country=country, settings=settings)

        self.data.forecast_admin1 = self.load.get_pipeline_data(
            data_type="seasonal-rainfall-forecast", country=self.country
        )

        self.data.threshold_climateregion = self.load.get_pipeline_data(data_type="climate-region", country=self.country )
        
     


        self.extract = Extract(
            settings=settings,
            secrets=secrets,
            data=self.data,
        )

        self.forecast = Forecast(
            settings=settings,
            secrets=secrets,
            data=self.data,
        )

    def run_pipeline(
        self,
        prepare: bool = True,
        extract: bool = True,
        forecast: bool = True,
        send: bool = True,
        save: bool = False,
        debug: bool = False,  # fast extraction on yesterday's data
        datetimestart: datetime = date.today(),
        datetimeend: datetime = date.today() + timedelta(days=1),
    ):
        """Run the flood data pipeline"""

        if prepare:
            logging.info("prepare ecmwf data")
            self.extract.prepare_ecmwf_data(country=self.country, debug=debug)

        if extract:
            logging.info(f"extract ecmwf data")
            self.extract.extract_ecmwf_data(country=self.country, debug=debug)

            '''
            if save:
                logging.info("save discharge data to storage")
                self.load.save_pipeline_data(
                    data_type="ecmwf forecast", dataset=self.data.discharge_admin
                )
                self.load.save_pipeline_data(
                    data_type="discharge-station", dataset=self.data.discharge_station
                )
                ''' 
        else:
            logging.info(f"get ecmwf data from storage")
            ''' 
            self.data.discharge_admin = self.load.get_pipeline_data(
                data_type="discharge",
                country=self.country,
                start_date=datetimestart,
                end_date=datetimeend,
            )
            self.data.discharge_station = self.load.get_pipeline_data(
                data_type="discharge-station",
                country=self.country,
                start_date=datetimestart,
                end_date=datetimeend,
            )
            ''' 

        if forecast:
            logging.info("forecast drought")
            self.forecast.compute_forecast()
            if save:
                logging.info("save flood forecasts to storage")
                self.load.save_pipeline_data(
                    data_type="seasonal-rainfall-forecast", dataset=self.data.forecast_admin
                )

        if send:
            if not forecast:
                logging.info("get flood forecasts from storage")
                self.data.forecast_admin = self.load.get_pipeline_data(
                    data_type="seasonal-rainfall-forecast",
                    country=self.country,
                    start_date=datetimestart,
                    end_date=datetimeend,
                )
                ''' 
                self.data.forecast_station = self.load.get_pipeline_data(
                    data_type="forecast-station",
                    country=self.country,
                    start_date=datetimestart,
                    end_date=datetimeend,
                ) 
                '''
            logging.info("send data to IBF API")
            self.load.send_to_ibf_api(
                forecast_data=self.data.forecast_admin,
                #discharge_data=self.data.discharge_admin,
                #forecast_station_data=self.data.forecast_station,
                #discharge_station_data=self.data.discharge_station,
                flood_extent=self.forecast.flood_extent_raster,
            )
