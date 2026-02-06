from calendar import monthrange
from datetime import datetime
import geopandas
import xarray as xr
import numpy as np

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
    
    # Get the month and year from the dataset (handle scalar or 0-d arrays)
    time_months = np.atleast_1d(ds_hindcast.time.dt.month.values)
    time_years = np.atleast_1d(ds_hindcast.time.dt.year.values)
    month = int(time_months[0])
    year = int(time_years[0])
    
    # Calculate the number of days in each forecast month
    days_in_month = [monthrange(year, ((month + int(fcmonth) - 1) - 1) % 12 + 1)[1] for fcmonth in ds_hindcast.forecastMonth.values]
    
    # Assign the number of days as a coordinate to the dataset
    ds = ds_hindcast.assign_coords(numdays=('forecastMonth', days_in_month))
    # ds2 = ds_forecast.assign_coords(numdays=('forecastMonth', days_in_month))
    
    # Convert the precipitation rate from m/s to mm/month
    ds = ds * ds.numdays * 24 * 60 * 60 * 1000
    # ds2 = ds2 * ds2.numdays * 24 * 60 * 60 * 1000
    
    return ds#,ds2

def get_extent_shp(filtered_gdf: geopandas.GeoDataFrame):
    # Get the extent of the filtered geofile
    lon_min, lat_min, lon_max, lat_max = filtered_gdf.total_bounds  # [minx, miny, maxx, maxy]
    return (lat_max, lon_min, lat_min, lon_max)

def subset_region(ds, region, latname='latitude', lonname='longitude'):
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


def dataarray_to_dict(da: xr.DataArray) -> dict:
    """Convert a 1-D `xarray.DataArray` (commonly indexed by `forecastMonth`) to a
    plain Python dict. The returned dict maps forecast month (int) to a small
    dict containing the value and any extra coordinates (e.g. `numdays`,
    `surface`).

    Example output:
      {1: {'value': 99.39, 'numdays': 31, 'surface': 0.0}, ...}

    This function is intentionally conservative: missing or NaN values are
    converted to `None` and numeric numpy types are converted to native Python
    types so the result is JSON-serializable.
    """
    # Aim to match: .drop_vars(['quantile']).to_series().to_dict()
    # If a Dataset is passed, pick the first data variable
    if isinstance(da, xr.Dataset):
        first_var = list(da.data_vars)[0]
        da = da[first_var]

    # If a 'quantile' dim exists (result of quantile()), select the first entry
    if 'quantile' in da.dims:
        try:
            da = da.isel(quantile=0)
        except Exception:
            da = da.squeeze('quantile', drop=True)

    # Also try to drop any coordinate named 'quantile' if present
    try:
        if 'quantile' in da.coords:
            da = da.drop_vars('quantile')
    except Exception:
        pass

    da = da.squeeze()
    try:
        series = da.to_series()
        raw_dict = series.to_dict()
        # convert numpy scalar types and NaN -> None
        out = {}
        for k, v in raw_dict.items():
            try:
                key = int(k)
            except Exception:
                key = k
            if isinstance(v, float) and np.isnan(v):
                out[key] = None
            elif isinstance(v, (np.integer,)):
                out[key] = int(v)
            elif isinstance(v, (np.floating,)):
                out[key] = float(v)
            else:
                out[key] = v
        return out
    except Exception:
        # Fallbacks: scalar or array
        try:
            raw = da.values
            if np.ndim(raw) == 0:
                if isinstance(raw, float) and np.isnan(raw):
                    return {'value': None}
                try:
                    return {'value': raw.item()}
                except Exception:
                    return {'value': raw}
            else:
                return {'values': raw.tolist()}
        except Exception:
            return {}