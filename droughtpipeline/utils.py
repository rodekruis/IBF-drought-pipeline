from calendar import monthrange
from datetime import datetime
import xarray as xr

#TODO: consider formalising utils

def replace_year_month(dt: datetime, new_year: int, new_month: int):
    '''Replace the year and month of a datetime object.
    ''' 
    try:
        return dt.replace(year=new_year, month=new_month)
    except ValueError:
        # Fallback to the last valid day in the new month
        last_day = monthrange(new_year, new_month)[1]
        return dt.replace(year=new_year, month=new_month, day=last_day)
    

def slice_netcdf_file(nc_file: xr.Dataset, country_bounds: list):
    """Slice the netcdf file to the bounding box"""
    min_lon = country_bounds[0]  # Minimum longitude
    max_lon = country_bounds[2]  # Maximum longitude
    min_lat = country_bounds[1]  # Minimum latitude
    max_lat = country_bounds[3]  # Maximum latitude
    var_data = nc_file.sel(lon=slice(min_lon, max_lon), lat=slice(max_lat, min_lat))
    return var_data


def convert_to_mm_per_month(xr_dataset: xr.Dataset):
    """
    Reads a file and returns the raster dataset converted to mm/month from m/s.
    """
    # Load hindcast dataset
    ds_hindcast = xr.open_dataset(xr_dataset, engine='cfgrib', backend_kwargs={'time_dims': ('forecastMonth', 'time')})
    # ds_forecast = xr.open_dataset(forecast, engine='cfgrib', backend_kwargs={'time_dims': ('forecastMonth', 'time')})
    
    # Get the month and year from the dataset
    month = ds_hindcast.time.dt.month.values[0]
    year = ds_hindcast.time.dt.year.values[0]
    
    # Calculate the number of days in each forecast month
    days_in_month = [monthrange(year, ((month + fcmonth - 1) - 1) % 12 + 1)[1] for fcmonth in ds_hindcast.forecastMonth.values]
    
    # Assign the number of days as a coordinate to the dataset
    ds = ds_hindcast.assign_coords(numdays=('forecastMonth', days_in_month))
    # ds2 = ds_forecast.assign_coords(numdays=('forecastMonth', days_in_month))
    
    # Convert the precipitation rate from m/s to mm/month
    ds = ds * ds.numdays * 24 * 60 * 60 * 1000
    # ds2 = ds2 * ds2.numdays * 24 * 60 * 60 * 1000
    
    return ds#,ds2