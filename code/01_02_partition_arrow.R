library(arrow)
library(tidyverse)

# Filter and create new cols
trips <- open_dataset("data/parquet_files", format = "parquet") |>
  filter(
    tpep_pickup_datetime >= as.POSIXct("2021-01-01"),
    tpep_pickup_datetime < as.POSIXct("2025-01-01"),
    trip_distance > 0,
    trip_distance < 100,
    total_amount > 0,
    total_amount < 500
  ) |>
  mutate(
    pickup_year = year(tpep_pickup_datetime),
    pickup_month = month(tpep_pickup_datetime)
  )

# Save data by pick up year and month
write_dataset(
  trips,
  path = "data/parquet_files",
  format = "parquet",
  partitioning = c("pickup_year", "pickup_month")
)

# Delete the raw parquet files

# Read it back, Arrow finds year and month from the folders.
open_dataset("data/parquet_files", format = "parquet")
