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
        debug: bool = False,  # debug mode with specific datestart of data
        datestart: datetime = date.today(),
    ):
        """Run the drought data pipeline"""

        if prepare:
            logging.info("prepare ecmwf data")
            self.extract.prepare_ecmwf_data(country=self.country, debug=debug, datestart=datestart)

        if extract:
            logging.info(f"extract ecmwf data")
            self.extract.extract_ecmwf_data(country=self.country, debug=debug, datestart=datestart)

        if forecast:
            logging.info("forecast drought")
            self.forecast.compute_forecast(debug=debug, datestart=datestart)
            if save:
                logging.info("save drought forecasts to storage")
                self.load.save_pipeline_data(
                    data_type="seasonal-rainfall-forecast-climate-region", 
                    dataset=self.data.forecast_climateregion,
                    replace_country=True,
                )
                self.load.save_pipeline_data(
                    data_type="seasonal-rainfall-forecast", 
                    dataset=self.data.forecast_admin,
                    replace_country=True,
                )
                logging.info("send data to 510 lake")
                self.load.upload_json_files( 
                    country=self.country,
                    local_path=self.forecast.output_data_path)

        if send:
            if not forecast:
                logging.info("get drought forecasts from storage")
                self.data.forecast_climateregion = self.load.get_pipeline_data(
                    data_type="seasonal-rainfall-forecast-climate-region",
                    country=self.country,
                    start_date=datestart,
                    end_date=datestart+timedelta(days=1), # TODO: to sync with upload vars current_month, current_year
                )
                self.data.forecast_admin = self.load.get_pipeline_data(
                    data_type="seasonal-rainfall-forecast",
                    country=self.country,
                    start_date=datestart,
                    end_date=datestart+timedelta(days=1), # TODO: to sync with upload vars current_month, current_year
                )
            logging.info("send data to IBF API")
            self.load.send_to_ibf_api(
                forecast_data=self.data.forecast_admin,
                threshold_climateregion=self.data.threshold_climateregion,
                forecast_climateregion=self.data.forecast_climateregion,
                drought_extent=self.forecast.drought_extent_raster,
                upload_time=datestart,
            )
