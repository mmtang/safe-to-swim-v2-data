"""
Processing FIB data for the Safe to Swim map (v2)

Introduction
The following code processes fecal indicator bacteria data (FIB) for the Safe to Swim map (v2), which is currently in development. It sources FIB data from the BeachWatch (https://beachwatch.waterboards.ca.gov/) and California Environmental Data Exchange Network (CEDEN) (https://ceden.org/) databases, both of which are managed by the State Water Resources Control Board (https://www.waterboards.ca.gov/). It also sources data from the Lower American River Recreational Water Quality Web App (https://experience.arcgis.com/experience/47e27f245e044ac2a8e15083307e75f6/?draft=true&org=waterboards), which is managed by the Central Valley Regional Water Board. This script combines the three datasets and calculates the 30-day and 6-week geometric mean values for each sample data point. The FIB data used in this script includes sampling data for *E. coli*, Enterococcus, Fecal Coliform, and Total Coliform.
"""


#------------------------------------------------------------------------------
# Requirements
#------------------------------------------------------------------------------

# To run the following code, you will need Python 3.x installed along with the Python
# packages, pandas and pyodbc. You will also need access to the internal BeachWatch and
# CEDEN data tables via internal data mart or some other access point.


#------------------------------------------------------------------------------
# Instructions
#------------------------------------------------------------------------------

# Run the following code cells in sequential order. You can run them manually cell by cell
# or run them all in one go. Do not skip any steps or cells. The generated data files are
# saved in the main directory.


#------------------------------------------------------------------------------
# 1. Import the required Python packages
#------------------------------------------------------------------------------


from datetime import date, datetime, timedelta
import numpy as np
import os
import pandas as pd
import pyodbc # Used for connecting to the internal data marts
import requests
from scipy.stats.mstats import gmean
import time


# Record start time
start_time = datetime.now()
print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")


#------------------------------------------------------------------------------
# 2. Download FIB data from BeachWatch, CEDEN, and the Lower American River E. coli map
#------------------------------------------------------------------------------


# 2.1 BeachWatch

# Define the variables for connecting to BeachWatch. These are private login credentials.
# The code block below will not run unless the environment variables on your machine are
# set up similarly.


BW_SERVER1 = os.environ.get('S2S_Server')
BW_DATABASE = os.environ.get('S2S_DB')
BW_TABLE = os.environ.get('S2S_Table')
BW_UID = os.environ.get('S2S_User')
BW_PWD = os.environ.get('S2S_Pass')


# Define and run a function for connecting to BeachWatch, querying all data records from
# BeachWatch, and returning the data as a pandas dataframe.


# Define the date columns for both BeachWatch and CEDEN to ensure that date values get parsed correctly
date_cols = ['SampleDate', 'CalibrationDate', 'CollectionTime', 'PrepPreservationDate', 'DigestExtractDate', 'AnalysisDate']

def get_bw_data():
    cnxn = pyodbc.connect(Driver='SQL Server', Server=BW_SERVER1, Database=BW_DATABASE, uid=BW_UID, pwd=BW_PWD)
    sql =  "SELECT * FROM %s" % BW_TABLE
    df = pd.read_sql_query(sql, cnxn, parse_dates=date_cols, dtype={'Result': np.float64, 'ResultReplicate': np.int16, 'CollectionReplicate': np.int16})
    return df

bw_df = get_bw_data() 
print("Count of rows:", bw_df.shape[0])

# Add a field for identifying the database source of the data
bw_df['DataSource'] = 'BeachWatch'

pd.set_option('display.max_columns', None)
bw_df.head()


# Some of the BeachWatch columns have slightly different names compared to the CEDEN
# columns. Because we will be joining these two datasets, we want all of the column names
# to match.


# Dictionary for mapping the names of BeachWatch fields to CEDEN fields
bw_to_ceden_fields = {
    'ProgramName': 'Program',
    'ParentProjectName': 'ParentProject',
    'ProjectName': 'Project',
    'UnitName': 'Unit',
    'ResQualCode': 'ResultQualCode',
    'BatchVerificationCode': 'BatchVerification',
    'LabCollectionComments': 'CollectionComments',
    'LabResultComments': 'ResultsComments',
    'AgencyCode': 'SampleAgency',
    'CollectionDeviceName': 'CollectionDeviceDescription',
    'LabSubmissionCode': 'SubmissionCode',
    'ResultReplicate': 'ResultsReplicate'
}

bw_df = bw_df.rename(columns=bw_to_ceden_fields)
bw_df.head()


# 2.2 CEDEN

# Define the variables for connecting to CEDEN. Like for the BeachWatch data above, these
# are private login credentials.


CEDEN_SERVER1 = os.environ.get('SERVER1')
CEDEN_UID = os.environ.get('UID')
CEDEN_PWD = os.environ.get('PWD')
CEDEN_TABLE = os.environ.get('TABLE')
CEDEN_SITE_DATUM_TABLE = os.environ.get('SITE_DATUM_TABLE') # Used for getting site datum data
CEDEN_SITE_TABLE = os.environ.get('SITE_TABLE') # Used for getting site region number


# Define and run a function for connecting to the CEDEN data mart and returning the data
# as a pandas dataframe. This query includes all data for E. coli, Enterococcus, Fecal
# Coliform, and Total Coliform, but at the same time it excludes all records where Program
# == BeachWatch. There is a lot of duplicate BeachWatch data in CEDEN from the time when
# BeachWatch data was copied over into CEDEN. We want to exclude the duplicate BeachWatch
# data from our query.


def get_ceden_data():
    cnxn = pyodbc.connect(Driver='SQL Server', Server=CEDEN_SERVER1, uid=CEDEN_UID, pwd=CEDEN_PWD)
    sql = "SELECT * FROM %s WHERE (Analyte in ('E. coli', 'Enterococcus', 'Coliform, Total', 'Coliform, Fecal') AND Program != 'BeachWatch')" % CEDEN_TABLE
    df = pd.read_sql_query(sql, cnxn, parse_dates=date_cols, dtype={'Result': np.float64, 'ResultsReplicate': np.int16, 'CollectionReplicate': np.int16})
    return df

ceden_df = get_ceden_data()
print("Count of rows:", ceden_df.shape[0])

# Add data source field
ceden_df['DataSource'] = 'CEDEN'

ceden_df.head()


# 2.3 Central Valley Regional Water Board - Lower American River E. coli Monitoring Results

# Get the Region 5 data from the open data portal (https://data.ca.gov/dataset/central-
# valley-water-board-e-coli-monitoring-results) and transform it to the BeachWatch/CEDEN
# format.


# Use the open data portal API to fetch the data
cv_url = 'https://data.ca.gov/api/3/action/datastore_search?resource_id=fc450fb6-e997-4bcf-b824-1b3ed0f06045&limit=10000'
cv_response = requests.get(cv_url)
cv_text = cv_response.json()['result']['records']
cv_df = pd.DataFrame(pd.json_normalize(cv_text))

print("Count of rows:", cv_df.shape[0])
cv_df.head()


# Drop ID column
cv_df = cv_df.drop('_id', axis=1)

# Rename columns to match CEDEN format
cv_df = cv_df.rename(columns={'Latitude': 'TargetLatitude', 'Longitude': 'TargetLongitude'})

# Define data types
cv_df['SampleDate'] = pd.to_datetime(cv_df['SampleDate'])
cv_df['TargetLatitude'] = cv_df['TargetLatitude'].astype(float)
cv_df['TargetLongitude'] = cv_df['TargetLongitude'].astype(float)

# Add replicate fields
cv_df['CollectionReplicate'] = 1
cv_df['ResultsReplicate'] = 1

# Add matrix field
cv_df['MatrixName'] = 'samplewater'

# Add data source field
cv_df['DataSource'] = 'Central Valley Water Board'

cv_df.head()


#------------------------------------------------------------------------------
# 3. Combine the BeachWatch, CEDEN, R5 datasets
#------------------------------------------------------------------------------

# The BeachWatch and CEDEN datasets have similar data structures, allowing us to combine
# the two datasets and work on both of them at the same time. The R5 dataset is missing a
# lot of columns but should still combine with the other two datasets without issue.


combined_df = pd.concat([bw_df, ceden_df, cv_df],  ignore_index=True)
print("Count of rows:", combined_df.shape[0])

# Fill NaN values in the Central Valley records with None
combined_df.fillna("", inplace=True)

combined_df.tail()


#------------------------------------------------------------------------------
# 4. Create the SampleDateTime column
#------------------------------------------------------------------------------

# For CEDEN, the sample date and collection time are stored in two different columns,
# SampleDate and CollectionTime, respectively. CollectionTime has a recorded date along
# with a time, but the paired date is not usable. Create a new column by separating out
# the time value from the CollectionTime column and combine it with the date value in the
# SampleDate column.


# Extract the time value from CollectionTime field and copy to a new field
combined_df['CollectionTimeOnly'] = combined_df['CollectionTime'].dt.time

# If the extracted time value is null or NaT, replace the empty value with 00:00:00
combined_df['CollectionTimeOnly'] = combined_df['CollectionTimeOnly'].fillna(pd.Timestamp('2025-01-01T00').time())

# Combine the date and time values into a new SampleDateTime field
combined_df['SampleDateTime'] = pd.to_datetime(combined_df['SampleDate']) + pd.to_timedelta(combined_df['CollectionTimeOnly'].astype(str))

combined_df.head()


#------------------------------------------------------------------------------
# 5. Dropping duplicate records
#------------------------------------------------------------------------------

# Even though we excluded BeachWatch records when pulling data from CEDEN (Step 2.2),
# there are still some duplicate BeachWatch records in CEDEN because these records are
# submitted to CEDEN under a different program name (i.e., not BeachWatch).
#
# An example of this is StationCode == 'Wharf-East' for Total coliform, sample taken on
# 9/5/2019. There are three data points for the same result, one in BeachWatch and two in
# CEDEN. They mostly have the same values in every column except for Program,
# ResultQualCode, and QACode. The Program value in BeachWatch is "BeachWatch" whereas the
# Program values in CEDEN are "BeachWatch" and "Santa Cruz City Environmental Program".
# The BeachWatch record was copied over into CEDEN from the BeachWatch database, and the
# other record was submitted to CEDEN under a different program name. Because the SQL
# query used in Step 2.2 only excludes records that have a Program value of "BeachWatch",
# the latter record would still make it into the combined dataset.
#
# A list of columns, defined below in the variable "duplicate_cols", is used to identify
# and drop the remaining duplicate records. When comparing one record to another, the code
# is looking for at least one unique value across all of these columns. If the values for
# both records across all columns are the same, then it is considered a duplicate record.
# This list of columns can be changed, as needed.


# Sort the dataframe by the DataSource column so that all BeachWatch records are positioned before the CEDEN records. 
# This is to ensure that BeachWatch records are kept by default if there happens to be the same record from both BeachWatch and CEDEN
combined_df = combined_df.sort_values(by='DataSource')

# Convert Result field to numeric before removing duplicates. Duplicated and drop_duplicates don't work properly without the type conversion
# Ex. 519SAC104, E. coli, 10/13/20 CEDN + R5
combined_df['Result'] = pd.to_numeric(combined_df['Result'])

combined_df.head()


# Define the columns used to identify duplicate records
# 10/1/24 - I removed 'QACode' and 'ResultQualCode' from this list because it appears that some duplicate records across BeachWatch and CEDEN have different QACode and ResultQualCode values 
# See StationCode == 'Wharf-East' for Total coliform, samples taken on 9/5/2019 (QACode) and 9/23/2019 (ResultQualCode)
# 2/21/25 - I changed SampleDateTime to SampleDate and removed MethodName. This is to address issue with there being duplicate records between the R5 data and CEDEN. Ex. 519SAC104, E. coli, 10/13/2020
duplicate_cols = ['StationCode', 'Analyte', 'MatrixName', 'SampleDateTime', 'CollectionReplicate', 'ResultsReplicate', 'Result', 'Unit']

# Select the identified duplicate records from the combined dataset and copy them to a new dataframe
# These records will later be added to the excluded_records csv file output
duplicates_df = combined_df.loc[combined_df.duplicated(subset=duplicate_cols, keep='first')]
duplicates_df['Comments'] = 'Duplicate record'

print('Count of duplicate records:', duplicates_df.shape[0])
duplicates_df.head()


print('Count of rows before dropping duplicates:', combined_df.shape[0])

# Drop the duplicate records from the combined dataset; if there are duplicates, keep the first duplicate record found (BeachWatch)
combined_df = combined_df.drop_duplicates(subset=duplicate_cols, keep='first')

print('Count of rows after removing duplicates:', combined_df.shape[0])


#------------------------------------------------------------------------------
# 6. Clean and process data
#------------------------------------------------------------------------------


# 6.1 Strip special characters and whitespace characters. Check null/missing values for compatability with the open data portal (data.ca.gov).


# Strip special characters from text fields. These characters can cause issues when reading, parsing, or writing the data
text_cols = combined_df.select_dtypes(include=['object', 'string']).columns

special_char_map = {
    r'\t': ' ', # tab
    r'\r': ' ', # carriage return
    r'\n': ' ', # newline
    r'\f': ' ', # formfeed
    r'\v': ' ', # vertical tab
    r'\|': ' ', # pipe
    r'"': ' ' # quotes
}

combined_df[text_cols] = combined_df[text_cols].replace(special_char_map, regex=True)

# Process the data to make sure the fields are compatible with the portal’s data type definition. 
# For numeric, make sure that all values can be recognized as a number. Missing values have to be encoded as "NaN". 
# For dates, the data has to be formatted as YYYY-MM-DD (you can also add a time to that - YYYY-MM-DD HH:MM:SS), and missing values have to be encoded as an empty text string ("").
# Check numeric columns

numeric_cols = ['CollectionDepth', 'CollectionReplicate', 'ResultsReplicate', 'Result']
for col in numeric_cols:
    try:
        combined_df[col].fillna('NaN')
    except:
        print('%s field does not exist for dataframe' % col)

# Cast data type for Result and MDL columns to numeric. Must be done here, not in the import data section
combined_df['Result'] = pd.to_numeric(combined_df['Result'], errors='coerce')
combined_df['MDL'] = pd.to_numeric(combined_df['MDL'], errors='coerce')


# 6.2 Check latitude and longitude values.


lat = pd.to_numeric(combined_df['TargetLatitude'], errors='coerce')
long = pd.to_numeric(combined_df['TargetLongitude'], errors='coerce')

# Sometimes longitude gets entered as positive (e.g., 119 instead of -119)
long = long.mask((long > 0) & (long < 180), -long)

# Missing/non-numeric values should be encoded as 'NaN' for the open data portal numeric type handling
combined_df['TargetLatitude'] = np.where(lat.notna(), lat, 'NaN')
combined_df['TargetLongitude'] = np.where(long.notna(), long, 'NaN')


# 6.3 Drop records that do not have valid Result and MDL values

# These records cannot be used even if we try to substitute the original value with 1/2
# the MDL.


# Copy non-ND records that have a negative, null, or zero Result and a negative, null, or zero MDL value to a new dataframe
# These records will later be added to the excluded_records csv file output
dropped_result_df = combined_df[((combined_df['Result'].isnull()) | (combined_df['Result'] <= 0)) & ((combined_df['MDL'].isnull()) | (combined_df['MDL'] <= 0))]
dropped_result_df['Comments'] = 'Result is null, negative, or zero; MDL is null, negative, or zero'
print('Count of unusable records to be dropped:', dropped_result_df.shape[0])

# Drop the records from the dataset
combined_df = combined_df.drop(dropped_result_df.index)


# 6.4 Drop replicate records


# Copy replicate records to a new dataframe
# These records will later be added to the excluded_records csv file output
replicate_df = combined_df[(combined_df['ResultsReplicate'] != 1) | (combined_df['CollectionReplicate'] != 1)]
replicate_df['Comments'] = 'Replicate data'
print('Count of replicate records to be dropped:', replicate_df.shape[0])

combined_df = combined_df.drop(replicate_df.index)


# 6.5 Standardize unit values and drop unneeded records

# There is inconsistency, mainly in the CEDEN database, with how the unit values are
# named. Later on, when calculating the geomeans, we will want to be able to group records
# by common unit values, so these values should match exactly.


# Rename units with abbreviations to have all capitalized letters
combined_df['Unit'] = combined_df['Unit'].replace('cfu/100mL', 'CFU/100 mL') 
combined_df['Unit'] = combined_df['Unit'].replace('mpn/100mL', 'MPN/100 mL') 

# Filter for specific units to be included in the dataset; copy all other records to new dataframe
units_keep = ['MPN/100 mL', 'CFU/100 mL', 'copies/100 mL']
dropped_units_df = combined_df[~combined_df['Unit'].isin(units_keep)]
print('Count of unit records to filter out:', dropped_units_df.shape[0])


# 6.6 Categorize records into unit groups based on the unit name

# This is based on the assumption that results reported in MPN (most probable number) are
# equivalent to results reported in CFU (colony forming units). Result values reported in
# "copies/100 mL" are associated with ddPCR methods. They are not equivalent to either
# MPN/CFU and should be handled separately.


# Assign a numeric value to each record based on the UnitName value
unit_map = { 'MPN/100 mL': 1, 'CFU/100 mL': 1, 'copies/100 mL': 2}
combined_df['UnitGroup'] = combined_df['Unit'].map(unit_map)  

combined_df.head()


#------------------------------------------------------------------------------
# 7. Add Datum column to the dataset
#------------------------------------------------------------------------------

# The data quality estimator tool (used in Step 8) requires the Datum field. This field is
# not included with the BeachWatch and CEDEN datasets by default, so we must get it from
# another CEDEN table and then join the values to the working dataset.


# Define a function used to get all records from the CEDEN table with datum data
def get_datum_data():
    try:
        sql = "SELECT StationCode, Datum FROM %s ;" % CEDEN_SITE_DATUM_TABLE
        cnxn = pyodbc.connect(Driver='SQL Server', Server=CEDEN_SERVER1, uid=CEDEN_UID, pwd=CEDEN_PWD)
        df = pd.read_sql(sql, cnxn)
        return df
    except:
        print("Couldn't connect to %s." % CEDEN_SERVER1)

datum_df = get_datum_data()
datum_df.head()


# Join the datum data to the combined dataset on common StationCode IDs
data_df = pd.merge(combined_df, datum_df, on='StationCode', how='left')

# Fill empty datum values with 'NR'. This is an important step for the data quality estimator, used later
data_df = data_df.fillna(value={'Datum': 'NR'})

data_df.head()


#------------------------------------------------------------------------------
# 8. Add a RegionNumber column to the dataset
#------------------------------------------------------------------------------

# This is a requested column to identify the Regional Board area where the site is
# located. We have to get data from another CEDEN stations table and join it to this
# dataset. This CEDEN table is a different table than the one used in Step 7.
# Unfortunately, the RB number values from this table are not complete. There will be some
# null values and other non-standard values in the dataset.


# Define a function that gets all records from the CEDEN station table, used to join region values.
def get_ceden_site_data():
    cnxn = pyodbc.connect(Driver='SQL Server', Server=CEDEN_SERVER1, uid=CEDEN_UID, pwd=CEDEN_PWD)
    sql = "SELECT StationLUCode, rb_number FROM %s" % CEDEN_SITE_TABLE
    df = pd.read_sql_query(sql, cnxn)
    return df

site_data = get_ceden_site_data()
site_data.head()


# Join the Region number to the combined dataset
data_df = data_df.merge(site_data, how='left', left_on='StationCode', right_on='StationLUCode')
data_df = data_df.rename(columns={'rb_number': 'RegionNumber'})

data_df.head()


#------------------------------------------------------------------------------
# 9. Add data quality columns to the dataset
#------------------------------------------------------------------------------

# The OIMA data quality estimator tool adds two columns, DataQuality and
# DataQualityIndicator, to the dataset.
#
# DataQuality: Describes the overall quality of the record by taking the QACode,
# ResulualQACode, ComplicanceCode, BatchVerificationCode, and special circumstances into
# account to assign it to one of the following categories: Passed, Some review needed,
# Spatial accuracy unknown, Extensive review needed, Unknown data quality, Reject record,
# Error in data, Metadata. The assignments and categories are provisional. A working
# explanation of the data quality ranking can be found this Google Doc file: https://docs.
# google.com/spreadsheets/d/1q-tGulvO9jyT2dR9GGROdy89z3W6xulYaci5-ezWAe0/edit?usp=sharing
#
# DataQualityIndicator - Explains the reason for the DataQuality value by indicating which
# quality assurance check the data did not pass (e.g. BatchVerificationCode, ResultQACode,
# etc.).
#
# The function "add_data_quality" used to add these two columns is imported into this
# notebook from another Python script file (below).


# The code for the data quality estimator is hosted on GitHub here:
# https://github.com/mmtang/data-quality-estimator.
# - The function *add_data_quality*: https://github.com/mmtang/data-quality-
#   estimator/blob/master/data_quality.py
# - The dictionaries for QACodes, ResultQualCodes, ComplianceCodes, etc. and their
#   associated data quality values: https://github.com/mmtang/data-quality-
#   estimator/blob/master/dq_constants.py


# Import Python file with the data quality estimator functions
import sys
sys.path.append('../data-quality-estimator')  # Path contains data_quality_utils.py

import data_quality


# Add the DataQuality and DataQualityIndicator columns
data_df = data_quality.add_data_quality(data_df, 'chemistry')

data_df.head()


#------------------------------------------------------------------------------
# 10. Drop records with a DataQuality score of "Reject record" or "Metadata"
#------------------------------------------------------------------------------


# Copy records with a DataQuality score of 'Reject record' or 'MetaData to a new dataframe
# These records will later be added to the excluded_records csv file output
dq_filter = ['Reject record', 'MetaData']
dropped_dq_df = data_df[data_df['DataQuality'].isin(dq_filter)]

# Drop these records from the dataset
data_df = data_df[~data_df['DataQuality'].isin(dq_filter)]

data_df.head()


#------------------------------------------------------------------------------
# 11. Drop records with invalid sample dates
#------------------------------------------------------------------------------

# Some records with sample year values 1950 or older are not being flagged. Also, there
# are some records with sample date values in the future (likely data entry error). Drop
# these records and add them to the excluded_records csv file output.


tomorrow = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
dropped_date_df = data_df[(data_df['SampleDate'].dt.year <= 1950) | (data_df['SampleDate'].dt.normalize() > tomorrow)]
dropped_date_df['Comments'] = 'Sample date is not valid'
print('Count of sample date records to be dropped:', dropped_date_df.shape[0])

# Drop the records from the dataset
data_df = data_df.drop(dropped_date_df.index)


#------------------------------------------------------------------------------
# 12. Clean null values
#------------------------------------------------------------------------------

# For compatability with the open data portal


# We have to make a distinction between None, 'None', and ''
# 'None' and '' are used specifically in the datasets, but None gets translated to 'None' unless we replace it with '' explicitly
data_df.fillna('')

data_df.head()


#------------------------------------------------------------------------------
# 13. Export a CSV file of all the dropped records. This includes:
#------------------------------------------------------------------------------

#
# - Step 5: Dropped duplicate records (duplicates_df)
# - Step 6.3: Dropped records with unusable Result and MDL values (dropped_result_df)
# - Step 6.4: Dropped replicate records (replicate_df)
# - Step 6.5: Dropped records with unit values we are not using (dropped_units_df)
# - Step 10: Dropped data quality records (dropped_dq_df)
# - Step 11: Dropped records with invalid sample dates/years (dropped_date_df)


# Define fields to be included in file export
exclude_export_fields = [
    'Program',
    'ParentProject',
    'Project',
    'StationName',
    'StationCode',
    'SampleDate',
    'CollectionTime',
    'LocationCode',
    'CollectionDepth',
    'UnitCollectionDepth',
    'SampleTypeCode',
    'CollectionReplicate',
    'ResultsReplicate',
    'LabBatch',
    'LabSampleID',
    'MatrixName',
    'MethodName',
    'Analyte',
    'Unit',
    'Result',
    'Observation',
    'MDL',
    'RL',
    'ResultQualCode',
    'QACode',
    'BatchVerification',
    'ComplianceCode',
    'SampleComments',
    'CollectionComments',
    'ResultsComments',
    'BatchComments',
    'EventCode',
    'ProtocolCode',
    'SampleAgency',
    'GroupSamples',
    'CollectionMethodName',
    'TargetLatitude',
    'TargetLongitude',
    'CollectionDeviceDescription',
    'CalibrationDate',
    'PositionWaterColumn',
    'PrepPreservationName',
    'PrepPreservationDate',
    'DigestExtractMethod',
    'DigestExtractDate',
    'AnalysisDate',
    'DilutionFactor',
    'ExpectedValue',
    'LabAgency',
    'SubmittingAgency',
    'SubmissionCode',
    'OccupationMethod',
    'StartingBank',
    'DistanceFromBank',
    'UnitDistanceFromBank',
    'StreamWidth',
    'UnitStreamWidth',
    'StationWaterDepth',
    'UnitStationWaterDepth',
    'HydroMod',
    'HydroModLoc',
    'LocationDetailWQComments',
    'ChannelWidth',
    'UpstreamLength',
    'DownStreamLength',
    'TotalReach',
    'LocationDetailBAComments',
    'SampleID',
    'DW_AnalyteName',
    'UnitGroup',
    'Datum',
    'DataSource',
    'SampleDateTime',
    'RegionNumber',
    'DataQuality',
    'DataQualityIndicator',
    'Comments'
]

# Merge all dataframes into a single dataframe
all_dropped_records_df = pd.concat([duplicates_df, dropped_result_df, replicate_df, dropped_units_df, dropped_dq_df, dropped_date_df], ignore_index=True)
all_dropped_records_df = all_dropped_records_df[exclude_export_fields]

all_dropped_records_df.head()


# Export all rejected records as a CSV file
all_dropped_records_df.to_csv('SafeToSwim_excluded_records.csv', index=False)


#------------------------------------------------------------------------------
# 13. Handle non-detect (ND) records and assign substitute Result values
#------------------------------------------------------------------------------

# If a record is flagged as non-detect (ResultQualCode == 'ND'), substitute the Result
# value with either half the original Result value (if the Result > 0) or half the MDL (if
# the Result <= 0 or Result is null).
#
# Also substitute half the MDL for records that are not flagged as non-detect but for some
# reason have a zero, null, or negative Result value. There shouldn't be very many (if
# any) of these records at this point, but I've left the code here just in case any slip
# through.


# Vectorized logic for handling ND results
result = pd.to_numeric(data_df['Result'], errors='coerce')
mdl = pd.to_numeric(data_df['MDL'], errors='coerce')
is_nd = data_df['ResultQualCode'].eq('ND')
is_bad_result = result.isna() | (result <= 0)

cond_nd_result = is_nd & (result > 0)
cond_nd_mdl = is_nd & ~(result > 0) & (mdl > 0)
cond_non_nd_mdl = ~is_nd & is_bad_result & (mdl > 0)

data_df['ResultSub'] = np.select(
    [cond_nd_result, cond_nd_mdl, cond_non_nd_mdl],
    [0.5 * result, 0.5 * mdl, 0.5 * mdl],
    default = result
)

data_df['ResultSubComments'] = np.select(
    [cond_nd_result, cond_nd_mdl, cond_non_nd_mdl],
    [
        'Nondetect: result substituted with half the result value',
        'Nondetect: result substituted with half the MDL',
        'Result substituted with half the MDL'
    ],
    default = 'No substitution'
)

data_df.head()


'''
# Define a function for assigning substitute Result values
def subResult(row):
    if (row['ResultQualCode'] == 'ND'):
        if (row['Result'] > 0):
            return pd.Series([(0.5 * row['Result']), 'Nondetect: result substituted with half the result value'])
        elif (row['MDL'] > 0):
            return pd.Series([(0.5 * row['MDL']), 'Nondetect: result substituted with half the MDL'])
        else:
            return pd.Series([row['Result'], 'No substitution'])
    elif ((row['Result'] == 0) or (pd.isna(row['Result'])) or (row['Result'] < 0)):
        if (row['MDL'] > 0):
            return pd.Series([(0.5 * row['MDL']), 'Result substituted with half the MDL'])
        else:
            return pd.Series([row['Result'], 'No substitution'])
    else:
        return pd.Series([row['Result'], 'No substitution'])

# Apply the function to the entire dataframe and save the subbed and non-subbed Result values to a new dataframe
sub_values = data_df.apply(lambda x: subResult(x), axis=1)

# Copy over the values and comments to the original dataframe as a new column "ResultSub". The original "Result" column is left untouched for reference.
data_df['ResultSub'], data_df['ResultSubComments'] = sub_values[0], sub_values[1]

data_df.head()
'''


#------------------------------------------------------------------------------
# 14. Calculate the geometric mean values
#------------------------------------------------------------------------------


# 14.1 Required data prep before calculating the geometric mean


# Ensure that SampleDateTime values are cast as datetime objects
data_df['SampleDateTime'] = data_df['SampleDateTime'].astype('datetime64[ns]')

# Set SampleDateTime as the index. This is more efficient for the grouping operations
data_df.set_index('SampleDateTime', inplace=True) 

# Drop records that have a null/NaT SampleDate value. As of 6-18-24, this is just one record.
data_df = data_df.loc[data_df.index.notnull()] 

# Sort records based on ascending SampleDateTime. A bit counterintuitive, but this is the setup for calculating 
# the rolling geometric starting from the most recent sample date working backwards using the rolling function
data_df.sort_index(ascending=True, inplace=True) 

data_df.head()


# 14.2 Group records and calculate the geometric mean

# This code block adds six new columns:
#
# - 30DayCutoffDate: The cutoff date used to determine which results fall within the 30
#   day range for calculating the rolling geometric mean.
# - 30DayGeoMean: The rolling geometric mean value looking back 30 days from the
#   recorded sample date.
# - 30DayCount: The number of distinct sample result values included in the 30 day date
#   range and used in the geometric mean calculation.
# - 6WeekCutoffDate: The cutoff date used to determine which results fall within the 6
#   week range for calculating the rolling geometric mean.
# - 6WeekGeoMean: The rolling geometric mean value looking back 6 weeks (42 days) from
#   the recorded sample date.
# - 6WeekCount: The number of distinct sample result values included in the 6 week date
#   range and used in the geometric mean calculation.


# Pre-aggregate records that represent the same exact sample event
# Same date but different times remain distinct because SampleDateTime includes the time component
group_cols = ['Analyte', 'StationCode', 'UnitGroup']
event_cols = group_cols + ['SampleDateTime']
event_df = data_df.reset_index().copy()

# Average ResultSub values for records with the same exact SampleDateTime within each station/analyte/unit group
agg_spec = {col: 'last' for col in event_df.columns if col not in event_cols + ['ResultSub']}
agg_spec['ResultSub'] = 'mean'

event_df = (
    event_df
        .groupby(event_cols, as_index=False, sort=False)
        .agg(agg_spec)
        .sort_values(event_cols, kind='stable')
)

def add_rolling_geomeans(df):
    # Work on one station/analyte/unit group at a time, preserving distinct sample times
    df = df.sort_values('SampleDateTime', kind='stable').copy()
    times = df['SampleDateTime'].to_numpy(dtype='datetime64[ns]').astype('int64')
    values = pd.to_numeric(df['ResultSub'], errors='coerce').to_numpy(dtype='float64')

    # Geometric mean is only defined for positive finite values
    valid = np.isfinite(values) & (values > 0)
    valid_counts = valid.astype(np.int64)
    
    # Keep track of cumulative sum of valid values, add leading zero for start indexing/offsets
    prefix_count = np.concatenate(([0], np.cumsum(valid_counts)))

    # Build a prefix sum of logs
    # Avoid taking the log of invalid (non-positive) numbers, which would produce -inf or nan
    log_values = np.zeros(len(df), dtype='float64') # Initialize array of zeros
    log_values[valid] = np.log(values[valid]) # Compute log values for valid numbers only
    prefix_log = np.concatenate(([0.0], np.cumsum(log_values))) # Calculate the cumulative sum of the logs, add leading zero

    for label, days in [('30Day', 30), ('6Week', 42)]:
        window_ns = np.int64(pd.Timedelta(days=days).value) # Convert day-based window into nanoseconds
        window_start = times - window_ns
    
        # Include samples that fall exactly on cutoff timestamp 
        start_idx = np.searchsorted(times, window_start, side='left') # Ensures the start is inclusive
        end_idx = np.arange(len(df)) + 1
    
        counts = prefix_count[end_idx] - prefix_count[start_idx]
        sum_logs = prefix_log[end_idx] - prefix_log[start_idx]

        # Calculate geomean
        geomean = np.full(len(df), np.nan, dtype='float64')
        has_values = counts > 0
        geomean[has_values] = np.exp(sum_logs[has_values] / counts[has_values])
    
        df[f'{label}GeoMean'] = np.round(geomean, 3)
        df[f'{label}Count'] = counts

    return df


# Split event_df into sub dfs ("groups") based on the columns in group_cols
group_frames = []
for _, group in event_df.groupby(group_cols, sort=False):
    group_frames.append(add_rolling_geomeans(group)) # Compute rolling geomeans within each group df
    
grouped_df = pd.concat(group_frames, ignore_index=True) if group_frames else event_df.copy()
grouped_df.head()


# Add the cutoff dates for the geometric mean calculations - for reference/documentation mainly
print(grouped_df.dtypes)
grouped_df['30DayCutoffDate'] = grouped_df['SampleDateTime'] - timedelta(days=30)
grouped_df['6WeekCutoffDate'] = grouped_df['SampleDateTime'] - timedelta(days=42)


#------------------------------------------------------------------------------
# 15. Export the geomean dataset as a CSV file
#------------------------------------------------------------------------------


# 15.1 Export the full dataset with all columns


all_fields = [
    'Program',
    'ParentProject',
    'Project',
    'StationName',
    'StationCode',
    'SampleDate',
    'CollectionTime',
    'LocationCode',
    'CollectionDepth',
    'UnitCollectionDepth',
    'SampleTypeCode',
    'CollectionReplicate',
    'ResultsReplicate',
    'LabBatch',
    'LabSampleID',
    'MatrixName',
    'MethodName',
    'Analyte',
    'Unit',
    'Result',
    'Observation',
    'MDL',
    'RL',
    'ResultQualCode',
    'QACode',
    'BatchVerification',
    'ComplianceCode',
    'SampleComments',
    'CollectionComments',
    'ResultsComments',
    'BatchComments',
    'EventCode',
    'ProtocolCode',
    'SampleAgency',
    'GroupSamples',
    'CollectionMethodName',
    'TargetLatitude',
    'TargetLongitude',
    'CollectionDeviceDescription',
    'CalibrationDate',
    'PositionWaterColumn',
    'PrepPreservationName',
    'PrepPreservationDate',
    'DigestExtractMethod',
    'DigestExtractDate',
    'AnalysisDate',
    'DilutionFactor',
    'ExpectedValue',
    'LabAgency',
    'SubmittingAgency',
    'SubmissionCode',
    'OccupationMethod',
    'StartingBank',
    'DistanceFromBank',
    'UnitDistanceFromBank',
    'StreamWidth',
    'UnitStreamWidth',
    'StationWaterDepth',
    'UnitStationWaterDepth',
    'HydroMod',
    'HydroModLoc',
    'LocationDetailWQComments',
    'ChannelWidth',
    'UpstreamLength',
    'DownStreamLength',
    'TotalReach',
    'LocationDetailBAComments',
    'SampleID',
    'DW_AnalyteName',
    #'UnitGroup',
    'Datum',
    #'CollectionTimeOnly',
    'DataSource',
    'SampleDateTime',
    'RegionNumber',
    'DataQuality',
    'DataQualityIndicator',
    'ResultSub',
    'ResultSubComments',
    #'ResultAvg',
    '30DayGeoMean',
    '30DayCount',
    '30DayCutoffDate',
    '6WeekGeoMean',
    '6WeekCount',
    '6WeekCutoffDate'
]

# Order columns
grouped_df_full = grouped_df[all_fields]

# Export dataframe as a CSV file
grouped_df_full.to_csv('SafeToSwim_geomeans_full.csv', index=False)


# 15.2 Export the full dataset as multiple files

# Export a version of the dataset for upload to the open data portal (data.ca.gov). The
# portal has a file size limit, so we will split the dataset into multiple files based on
# sample date.


data_before_2010 = grouped_df_full[grouped_df_full['SampleDate'] < '2010-01-01']
data_2010_2020 = grouped_df_full[(grouped_df_full['SampleDate'] >= '2010-01-01') & (grouped_df_full['SampleDate'] < '2020-01-01')]
data_2020_present = grouped_df_full[grouped_df_full['SampleDate'] >= '2020-01-01']

data_before_2010.to_csv('SafeToSwim_geomeans_before-2010.csv', index=False)
data_2010_2020.to_csv('SafeToSwim_geomeans_2010-2020.csv', index=False)
data_2020_present.to_csv('SafeToSwim_geomeans_2020-present.csv', index=False)


# 15.2 Dataset with select columns (for testing)

# Export an shortened version of the dataset (fewer columns) for testing.


'''
test_fields = [
    'Program',
    'ParentProject',
    'Project',
    'StationName',
    'StationCode',
    'SampleDate',
    'CollectionTime',
    #'LocationCode',
    #'CollectionDepth',
    #'UnitCollectionDepth',
    #'SampleTypeCode',
    #'CollectionReplicate',
    #'ResultsReplicate',
    'LabBatch',
    #'LabSampleID',
    'MatrixName',
    'MethodName',
    'Analyte',
    'Unit',
    'Result',
    #'Observation',
    'MDL',
    'RL',
    'ResultQualCode',
    #'QACode',
    #'BatchVerification',
    #'ComplianceCode',
    #'SampleComments',
    #'CollectionComments',
    #'ResultsComments',
    #'BatchComments',
    #'EventCode',
    #'ProtocolCode',
    #'SampleAgency',
    #'GroupSamples',
    #'CollectionMethodName',
    #'TargetLatitude',
    #'TargetLongitude',
    #'CollectionDeviceDescription',
    #'CalibrationDate',
    #'PositionWaterColumn',
    #'PrepPreservationName',
    #'PrepPreservationDate',
    #'DigestExtractMethod',
    #'DigestExtractDate',
    #'AnalysisDate',
    #'DilutionFactor',
    #'ExpectedValue',
    #'LabAgency',
    #'SubmittingAgency',
    #'SubmissionCode',
    #'OccupationMethod',
    #'StartingBank',
    #'DistanceFromBank',
    #'UnitDistanceFromBank',
    #'StreamWidth',
    #'UnitStreamWidth',
    #'StationWaterDepth',
    #'UnitStationWaterDepth',
    #'HydroMod',
    #'HydroModLoc',
    #'LocationDetailWQComments',
    #'ChannelWidth',
    #'UpstreamLength',
    #'DownStreamLength',
    #'TotalReach',
    #'LocationDetailBAComments',
    #'SampleID',
    #'DW_AnalyteName',
    #'Datum',
    #'CollectionTimeOnly',
    'DataSource',
    'SampleDateTime',
    'RegionNumber',
    'DataQuality',
    'DataQualityIndicator',
    'ResultSub',
    'ResultSubComments',
    #'ResultAvg',
    '30DayGeoMean',
    '30DayCount',
    '30DayCutoffDate',
    '6WeekGeoMean',
    '6WeekCount',
    '6WeekCutoffDate'
]

# Order columns
grouped_df_test = grouped_df[test_fields]

# Export dataframe as a CSV file
grouped_df_test.to_csv('SafeToSwim_geomeans_short.csv', index=False)
'''


# Record end time
end_time = datetime.now()
print(f'End time: {end_time.strftime("%Y-%m-%d %H:%M:%S")}')

# Calculate elapsed time
elapsed = end_time - start_time

# Convert to total seconds and format
total_seconds = int(elapsed.total_seconds())
hours, remainder = divmod(total_seconds, 3600)
minutes, seconds = divmod(remainder, 60)

print(f'Elapsed time: {hours:02}:{minutes:02}:{seconds:02}')
