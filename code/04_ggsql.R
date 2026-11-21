library(ggsql)

# Create DuckDB reader
reader <- duckdb_reader("data/taxi.duckdb")

# What tables are available
ggsql_table_names(reader) # [1] "hourly"       "monthly"      "trips_clean"  "zone_pickups" "zones"

# Visualize it with a query
p1 <- ggsql_execute(
  reader,
  "
VISUALISE pickup_hour AS x, n_trips AS y FROM hourly
DRAW line
"
)

p2 <- ggsql_execute(
  reader,
  "
VISUALISE pickup_month AS x, mean_fare AS y, pickup_year AS color FROM monthly
DRAW point
"
)

ggsql_save(p1, "outputs/02_hourly.png")
ggsql_save(p2, "outputs/03_monthly.png")
