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
    "--month",
    help="year-month in ISO 8601",
    default=date.today().strftime("%Y-%m"),
)
@click.option(
    "--debug",
    help="debug mode: process data from last month",
    default=False,
    is_flag=True,
) # TODO: define proper debug mode


def run_drought_pipeline(
    country, prepare, extract, forecast, send, save, month, debug
):
    datestart = format_date(month)
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

def format_date(month: str) -> datetime:
    today_day = date.today().day
    year, month = map(int, month.split('-'))
    # Create the new date using year, month, and today's day
    try:
        datestart = date(year, month, today_day)
    except ValueError:
        # Handle case where the day doesn't exist in that month (e.g., Feb 30)
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        datestart = date(year, month, last_day)
    return datestart


if __name__ == "__main__":
    run_drought_pipeline()
