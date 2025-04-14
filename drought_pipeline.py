from droughtpipeline.pipeline import Pipeline
from droughtpipeline.secrets import Secrets
from droughtpipeline.settings import Settings
from datetime import date, datetime, timedelta
import click



@click.command()
@click.option("--country", help="country ISO3", default="LSO")
@click.option("--prepare", help="prepare ECMWF data", default=False, is_flag=True)
@click.option("--extract", help="extract ECMWF data", default=False, is_flag=True)
@click.option("--forecast", help="forecast drought", default=False, is_flag=True)
@click.option("--send", help="send to IBF", default=False, is_flag=True)
@click.option("--save", help="save to storage", default=False, is_flag=True)
@click.option(
    "--datestart",
    help="datetime start ISO 8601",
    default=date.today().strftime("%Y-%m-%d"),
)
@click.option(
    "--debug",
    help="debug mode: process data from last month",
    default=False,
    is_flag=True,
) # TODO: define proper debug mode

def run_drought_pipeline(
    country, prepare, extract, forecast, send, save, datestart, debug
):
    datestart = datetime.strptime(datestart, "%Y-%m-%d")
    pipe = Pipeline(
        country=country,
        settings=Settings("config/config.yaml"),
        secrets=Secrets(".env"),
    )
    pipe.run_pipeline(
        prepare=prepare,
        extract=extract,
        forecast=forecast,
        send=send,
        save=save,
        debug=debug,
        datestart=datestart
    )


if __name__ == "__main__":
    run_drought_pipeline()
