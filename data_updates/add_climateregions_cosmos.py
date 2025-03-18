import pandas as pd

import pandas as pd
from datetime import datetime 
from azure.cosmos import CosmosClient

COSMOS_URL=" "
COSMOS_KEY=" "
 
# Initialize the CosmosClient
client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY, user_agent="ibf-flood-pipeline", user_agent_overwrite=True)

# Access a specific database
database_name = "drought-pipeline"
database = client.get_database_client(database_name)

country='ETH'
adm_level=1
 
df = pd.read_csv(f'config/{country}_climate_region_district_mapping.csv')

# Group the DataFrame by 'Climate_Region' and create a list of 'ParentPcode' for each group
climate_region_parent_codes = df.groupby(['Climate_Region','Climate_Region_code'])['placeCode'].apply(list).to_dict()
 
#strftime("%Y-%m-%dT%H:%M:%S")
 # Print the result

forecast= {
        "tercile_lower": 10.2,
        "tercile_upper": -5.5,
        "forecast": [11.33, -14.21, -10.22, -2.26, -11.35, -18.09, -5.09, -0.54, -2.14, 0.09, -15.57, -13.09, 3.04, -11.6, -14.53, -13.56, -7.06, -14.12, -11.26, -0.55, -8.64, -19.9, -8.28, 33.69, -17.23, -2.64, -9.07, 4.96, -9.77, -2.94, -8.39, -6.69, -15.02, -10.61, 2.03, -16.5, -6.35, -1.86, -17.45, -9.8, -17.6, -15.09, -1.7, -12.93, -8.12, -0.5, -6.33, 3.85, -5.04, -11.22, -10.98]
    }

for climate_region, parent_codes in climate_region_parent_codes.items():
    new_item={
        "country":country,
        "adm_level": adm_level,
        "Climate_Region":climate_region[0],
        "Climate_Region_code":climate_region[1],
        "pcodes":parent_codes,
        'timestamp': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        'id': f'{country}_{climate_region[1]}_{str(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))}',
    }
    container_name = "climate-region"
    container = database.get_container_client(container_name)
    container.upsert_item(new_item)


    for pcode in parent_codes:
        for LeadTime in range(1, 7):


            seasonalrainfallforecast={
                "adm_level": adm_level,
                "pcode": pcode,
                "Climate_Region":climate_region[0],
                "Climate_Region_code":climate_region[1],
                "lead_time": LeadTime,
                "tercile_lower": 10.2,
                "tercile_upper": -5.5,
                "rainfall_forecast": [11.33, -14.21, -10.22, -2.26, -11.35, -18.09, -5.09, -0.54, -2.14, 0.09, -15.57, -13.09, 3.04, -11.6, -14.53, -13.56, -7.06, -14.12, -11.26, -0.55, -8.64, -19.9, -8.28, 33.69, -17.23, -2.64, -9.07, 4.96, -9.77, -2.94, -8.39, -6.69, -15.02, -10.61, 2.03, -16.5, -6.35, -1.86, -17.45, -9.8, -17.6, -15.09, -1.7, -12.93, -8.12, -0.5, -6.33, 3.85, -5.04, -11.22, -10.98],
                "pop_affected": 0,
                "pop_affected_perc": 0,
                "triggered": False,
                "return_period": 0,
                "likelihood": 0,
                "alert_class": "no",
                "timestamp": str(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")),
                "country":country,
                "id": f'{country}_{pcode}_{str(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))}_{LeadTime}'
            }
            container_name = "seasonal-rainfall-forecast"
            container = database.get_container_client(container_name)
            container.upsert_item(seasonalrainfallforecast)
'''
        seasonalrainfallthreshold={
                "adm_level": adm_level,
                "pcode": pcode,
                "Climate_Region":climate_region[0],
                "Climate_Region_code":climate_region[1],
                "thresholds": [
                    {
                        "return_period": 0,
                        "threshold_value": 0
                    }
                ],
                "timestamp": str(datetime.utcnow().isoformat()),
                "country": country,
                "id": f'{country}_{pcode}_{str(datetime.utcnow().isoformat())}'
        }

        container_name = "seasonal-rainfall-threshold"
        container = database.get_container_client(container_name)
        #container.upsert_item(seasonalrainfallthreshold)
'''


import pandas as pd

import pandas as pd
from datetime import datetime 
from azure.cosmos import CosmosClient

 

 
# Initialize the CosmosClient
client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY, user_agent="ibf-flood-pipeline", user_agent_overwrite=True)

# Access a specific database
database_name = "drought-pipeline"
database = client.get_database_client(database_name)

country='ETH'
adm_level=2
 
df = pd.read_csv(f'config/{country}_climate_region_district_mapping.csv')

# Group the DataFrame by 'Climate_Region' and create a list of 'ParentPcode' for each group
climate_region_parent_codes = df.groupby(['Climate_Region','Climate_Region_code'])['placeCode'].apply(list).to_dict()
 
#strftime("%Y-%m-%dT%H:%M:%S")
 # Print the result

forecast= {
        "tercile_lower": 10.2,
        "tercile_upper": -5.5,
        "forecast": [11.33, -14.21, -10.22, -2.26, -11.35, -18.09, -5.09, -0.54, -2.14, 0.09, -15.57, -13.09, 3.04, -11.6, -14.53, -13.56, -7.06, -14.12, -11.26, -0.55, -8.64, -19.9, -8.28, 33.69, -17.23, -2.64, -9.07, 4.96, -9.77, -2.94, -8.39, -6.69, -15.02, -10.61, 2.03, -16.5, -6.35, -1.86, -17.45, -9.8, -17.6, -15.09, -1.7, -12.93, -8.12, -0.5, -6.33, 3.85, -5.04, -11.22, -10.98]
    }
gd=gpd.read_file("C:\pipelines\IBF_DROUGHT_PIPELINE\pipeline\data\other\input\ETH_adm3.geojson")

for climate_region, parent_codes in climate_region_parent_codes.items():
    gd_filtered=gd[gd['ADM2_PCODE'].isin(parent_codes)]
    adm_dict = gd_filtered[['ADM1_PCODE', 'ADM2_PCODE','ADM3_PCODE']].to_dict(orient='list')
    adm_dict = {int(1): list(set(adm_dict['ADM1_PCODE'])), int(2): list(set(adm_dict['ADM2_PCODE'])), int(3): list(set(adm_dict['ADM3_PCODE']))}

    new_item={
        "country":country,
        "adm_level": adm_level,
        "Climate_Region":climate_region[0],
        "Climate_Region_code":climate_region[1],
        "pcodes":adm_dict,
        'timestamp': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        'id': f'{country}_{climate_region[1]}_{str(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))}',
    }
    container_name = "climate-region"
    container = database.get_container_client(container_name)
    container.upsert_item(new_item)


country='LSO'
adm_level=2
 
df = pd.read_csv(f'config/{country}_climate_region_district_mapping.csv')

# Group the DataFrame by 'Climate_Region' and create a list of 'ParentPcode' for each group
climate_region_parent_codes = df.groupby(['Climate_Region','Climate_Region_code'])['placeCode'].apply(list).to_dict()
 
#strftime("%Y-%m-%dT%H:%M:%S")
 # Print the result

forecast= {
        "tercile_lower": 10.2,
        "tercile_upper": -5.5,
        "forecast": [11.33, -14.21, -10.22, -2.26, -11.35, -18.09, -5.09, -0.54, -2.14, 0.09, -15.57, -13.09, 3.04, -11.6, -14.53, -13.56, -7.06, -14.12, -11.26, -0.55, -8.64, -19.9, -8.28, 33.69, -17.23, -2.64, -9.07, 4.96, -9.77, -2.94, -8.39, -6.69, -15.02, -10.61, 2.03, -16.5, -6.35, -1.86, -17.45, -9.8, -17.6, -15.09, -1.7, -12.93, -8.12, -0.5, -6.33, 3.85, -5.04, -11.22, -10.98]
    }

import pandas as pd

# Read the Excel file and select a specific sheet
file_path = "C:\pipelines\IBF_DROUGHT_PIPELINE\pipeline\data\other\input\lso_adm_fao_mlgca_2019_fis.xls"

sheet_name = 'lso_admbnda_adm2_FAO_MLGCA_2019'  # Replace with the actual sheet name

# Read the specific sheet
df = pd.read_excel(file_path, sheet_name=sheet_name)

# Select specific columns
selected_columns = ['ADM1_PCODE', 'ADM2_PCODE']  # Replace with actual column names
df_selected = df[selected_columns]

# Convert the selected columns to a dictionary
data_dict = df_selected.to_dict(orient='list')
data_dict = {1: data_dict['ADM1_PCODE'], 2: data_dict['ADM2_PCODE']}
 
for climate_region, parent_codes in climate_region_parent_codes.items():
    gd_filtered=df_selected[df_selected['ADM1_PCODE'].isin(parent_codes)]
    adm_dict = gd_filtered.to_dict(orient='list')
 
    adm_dict = {1: list(set(adm_dict['ADM1_PCODE'])), 2: list(set(adm_dict['ADM2_PCODE']))}

    new_item={
        "country":country,
        "adm_level": adm_level,
        "Climate_Region":climate_region[0],
        "Climate_Region_code":climate_region[1],
        "pcodes":adm_dict,
        'timestamp': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        'id': f'{country}_{climate_region[1]}_{str(datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))}',
    }
    container_name = "climate-region"
    container = database.get_container_client(container_name)
    container.upsert_item(new_item)