import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import orbital


DB_FILE = "data/taxi.duckdb"
SAMPLE_N = 500_000

FEATURES = [
    "trip_distance",
    "passenger_count",
    "pickup_hour",
    "pickup_dow",
    "PULocationID",
    "DOLocationID"
]

con = duckdb.connect(DB_FILE, read_only=True)

# Sample Data from DB
df = con.execute(
    f"""
    SELECT trip_distance, passenger_count, pickup_hour, pickup_dow,
      PULocationID, DOLocationID, total_amount
    FROM trips_clean
    WHERE trip_distance BETWEEN 0.1 AND 30
      AND total_amount BETWEEN 3 AND 100
      AND trip_minutes BETWEEN 1 AND 120
      AND passenger_count IS NOT NULL
      AND PULocationID IS NOT NULL
      AND DOLocationID IS NOT NULL
    ORDER BY random()
    LIMIT {SAMPLE_N}
    """
).fetchdf()

con.close()

df = df.dropna()

# Split data
train = df.sample(frac=0.8, random_state=42)
test = df.drop(train.index)

# ML pipeline in python
pipeline = Pipeline(
    [
        ("scaler", StandardScaler()),
        ("model", LinearRegression()),
    ]
)
pipeline.fit(train[FEATURES], train["total_amount"])

pred_python = pipeline.predict(test[FEATURES])
print("MAE, Python:", round(mean_absolute_error(test["total_amount"], pred_python), 3))
print("RMSE, Python:", round(mean_squared_error(test["total_amount"], pred_python) ** 0.5, 3))

# Convert to Orbital, then to DuckDB SQL.
orbital_pipeline = orbital.parse_pipeline(
    pipeline,
    features={c: orbital.types.DoubleColumnType() for c in FEATURES},
)
sql = orbital.export_sql("trips_clean", orbital_pipeline, dialect="duckdb")
with open("outputs/orbital_model.sql", "w") as f:
    f.write(sql)


# Run the same SQL in DuckDB, on the test rows, and compare.
con2 = duckdb.connect()
con2.register("test_trips_df", test[FEATURES])
sql_test = orbital.export_sql("test_trips_df", orbital_pipeline, dialect="duckdb")
pred_sql = con2.execute(sql_test).fetchdf()
pred_sql_values = pred_sql.iloc[:, 0].to_numpy()
print("MAE, SQL:", round(mean_absolute_error(test["total_amount"], pred_sql_values), 3))
print("Max abs diff, Python vs SQL:", float(np.max(np.abs(pred_sql_values - pred_python))))
print("First 5, Python:", np.round(pred_python[:5], 2))
print("First 5, SQL:", np.round(pred_sql_values[:5], 2))
