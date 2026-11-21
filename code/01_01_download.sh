# Run from the project folder: code/bash 01_01_download.sh

set -e
mkdir -p data
cd data
mkdir parquet_files
cd parquet_files

BASE="https://d37ci6vzurychx.cloudfront.net/trip-data"

for year in 2021 2022 2023 2024; do
  for month in 01 02 03 04 05 06 07 08 09 10 11 12; do
    file="yellow_tripdata_${year}-${month}.parquet"
    if [ -s "$file" ]; then
      echo "skip $file, already there"
    else
      echo "download $file"
      curl -L -C - -o "$file" "${BASE}/${file}"
    fi
  done
done

cd ..
mkdir csv_files
cd csv_files

# Zone lookup, 265 rows, LocationID to Borough and Zone name.
if [ ! -s taxi_zone_lookup.csv ]; then
  curl -L -o taxi_zone_lookup.csv https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv
fi

# Zone polygons, 263 polygons, EPSG:2263, State Plane feet.
if [ ! -s taxi_zones.zip ]; then
  curl -L -o taxi_zones.zip https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip
fi

ls -lh
du -sh .
