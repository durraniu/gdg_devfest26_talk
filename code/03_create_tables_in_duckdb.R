library(DBI)
library(duckdb)

con <- dbConnect(
  duckdb::duckdb(),
  dbdir = "data/taxi.duckdb",
  config = list(storage_compatibility_version = "v1.5.6")
)

src <- "read_parquet(
  'data/parquet_files/**/*.parquet',
  hive_partitioning = true,
  union_by_name = true
)"


# Create clean trips table
dbListTables(con) # character(0)
dbExecute(
  con,
  sprintf(
    "
  CREATE OR REPLACE TABLE trips_clean AS
  SELECT
    VendorID,
    tpep_pickup_datetime,
    tpep_dropoff_datetime,
    pickup_year, 
    pickup_month,
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
    congestion_surcharge,
    airport_fee,
    date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) AS trip_minutes,
    extract(hour  FROM tpep_pickup_datetime) AS pickup_hour,
    extract(dow   FROM tpep_pickup_datetime) AS pickup_dow,
    date_trunc('month', tpep_pickup_datetime) AS pickup_month_ts
  FROM %s
  WHERE passenger_count >= 1  AND passenger_count <= 6
    AND date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) BETWEEN 1 AND 180
",
    src
  )
)

dbListTables(con) # [1] "trips_clean"


# Create monthly table
dbExecute(
  con,
  "
  CREATE OR REPLACE TABLE monthly AS
  SELECT
    pickup_month,               
    pickup_year,                
    count(*)                    AS n_trips,
    round(avg(total_amount), 2) AS mean_fare,
    round(avg(trip_distance), 2) AS mean_miles,
    round(avg(trip_minutes), 1) AS mean_minutes
  FROM trips_clean
  GROUP BY pickup_year, pickup_month
  ORDER BY pickup_year, pickup_month
"
)

# Hourly
dbExecute(
  con,
  "
  CREATE OR REPLACE TABLE hourly AS
  SELECT pickup_hour,
         count(*)                    AS n_trips,
         round(avg(total_amount), 2) AS mean_fare
  FROM trips_clean
  GROUP BY pickup_hour
  ORDER BY pickup_hour
"
)

# Zones and zone pickups
dbExecute(
  con,
  "
  CREATE OR REPLACE TABLE zones AS
  SELECT * FROM read_csv('data/csv_files/taxi_zone_lookup.csv')
"
)

dbExecute(
  con,
  "
  CREATE OR REPLACE TABLE zone_pickups AS
  SELECT
    t.PULocationID AS LocationID,
    z.Borough,
    z.Zone,
    count(*)                    AS n_trips,
    round(avg(t.total_amount), 2) AS mean_fare,
    round(avg(t.trip_distance), 2) AS mean_miles
  FROM trips_clean t
  LEFT JOIN zones z ON t.PULocationID = z.LocationID
  GROUP BY t.PULocationID, z.Borough, z.Zone
  ORDER BY n_trips DESC
"
)

dbListTables(con) # [1] "hourly"       "monthly"      "trips_clean"  "zone_pickups" "zones"
