# If this doesn't work, try 01_01_download.sh and 01_02_partition_arrow.R
library(DBI)
library(duckdb)
library(glue)

# Create an in-memory connection
con <- dbConnect(duckdb())

# Install and load the httpfs duckdb extension
## This allows downloading the NYC Taxi Trips parquet files:
## (https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
## Yello trips data dictionary: https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf
dbExecute(con, "INSTALL httpfs")
dbExecute(con, "LOAD httpfs")

# Example: Get data for 2021:
dat_2021 <- dbGetQuery(
  con,
  "SELECT * FROM read_parquet('https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2021-05.parquet')"
)


# Get all data and save to data folder
years <- rep(2021:2024, each = 12)
months <- sprintf("%02d", rep(1:12, times = length(unique(years))))
urls <- paste0(
  "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_",
  years,
  "-",
  months,
  ".parquet"
)
query <- glue_sql(
  "
  COPY (
    SELECT
      VendorID,
      tpep_pickup_datetime,
      tpep_dropoff_datetime,
      passenger_count,
      trip_distance,
      RatecodeID,
      PULocationID,
      DOLocationID,
      payment_type,
      fare_amount,
      tip_amount,
      tolls_amount,
      total_amount,
      airport_fee,
      date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) AS trip_minutes,
      extract(hour  FROM tpep_pickup_datetime) AS pickup_hour,
      extract(dow   FROM tpep_pickup_datetime) AS pickup_dow,
      extract(year  FROM tpep_pickup_datetime) AS pickup_year,
      extract(month FROM tpep_pickup_datetime) AS pickup_month
    FROM read_parquet([{urls*}], union_by_name = true)
    WHERE trip_distance   > 0   AND trip_distance  < 100
      AND total_amount    > 0   AND total_amount   < 500
      AND passenger_count >= 1  AND passenger_count <= 6
      AND date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) BETWEEN 1 AND 180
  ) TO 'data' (
    FORMAT PARQUET,
    PARTITION_BY (pickup_year, pickup_month)
  )
",
  .con = con
)

dbExecute(con, query)
