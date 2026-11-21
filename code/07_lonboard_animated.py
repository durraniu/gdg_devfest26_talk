import os
from datetime import timedelta
import duckdb
import geopandas as gpd
import matplotlib as mpl
import numpy as np
import pyarrow as pa
import shapely
from ipywidgets import jsdlink
from ipywidgets.embed import embed_minimal_html
from lonboard import Map, PolygonLayer, TripsLayer
from lonboard.basemap import CartoStyle, MaplibreBasemap
from taxi_panel import TEMPLATE, Panel, gradient_css

DB_FILE = os.environ.get("DB_FILE", "data/taxi.duckdb")
DAY = os.environ.get("DAY")  # e.g. DAY=2024-01-17, default: busiest day
N_TRIPS = 40_000  

os.makedirs("outputs", exist_ok=True)

# Step 1: one day of trips from DuckDB. Each trip needs its own timestamps,
# so sample instead of aggregating.
con = duckdb.connect(DB_FILE, read_only=True)
if DAY is None:
    DAY = str(
        con.execute(
            """
            SELECT CAST(tpep_pickup_datetime AS DATE) AS d
            FROM trips_clean GROUP BY d ORDER BY count(*) DESC LIMIT 1
            """
        ).fetchone()[0]
    )
print("day:", DAY)

n_day = con.execute(
    "SELECT count(*) FROM trips_clean WHERE CAST(tpep_pickup_datetime AS DATE) = ?",
    [DAY],
).fetchone()[0]

trips = con.execute(
    f"""
    SELECT PULocationID, DOLocationID,
           tpep_pickup_datetime, tpep_dropoff_datetime, trip_distance
    FROM trips_clean
    WHERE CAST(tpep_pickup_datetime AS DATE) = ?
      AND PULocationID <> DOLocationID            -- same zone = zero-length line
      AND tpep_dropoff_datetime > tpep_pickup_datetime
      AND tpep_dropoff_datetime < tpep_pickup_datetime + INTERVAL 3 HOUR
    ORDER BY random()
    LIMIT {N_TRIPS}
    """,
    [DAY],
).fetchdf()
con.close()
print("trips sampled:", len(trips))

# Step 2: zone centroids. Dissolve first: if a LocationID is split over
# several rows in the shapefile, a plain join would duplicate its trips.
# Centroid in EPSG:2263, then to EPSG:4326.
polygons = (
    gpd.read_file("data/csv_files/taxi_zones/taxi_zones.shp")
    .to_crs(2263)
    .dissolve(by="LocationID", as_index=False)
)
c = polygons.geometry.centroid.to_crs(4326)
cent = polygons[["LocationID"]].copy()
cent["x"] = c.x.to_numpy()
cent["y"] = c.y.to_numpy()
polygons = polygons.to_crs(4326)

# Step 3: attach centroids to both ends (inner join drops zones 264/265).
a = trips.merge(cent.add_prefix("pu_"), left_on="PULocationID", right_on="pu_LocationID")
a = a.merge(cent.add_prefix("do_"), left_on="DOLocationID", right_on="do_LocationID")
print("trips with both centroids:", len(a))

# Step 4: two-vertex LineStrings, one per trip.
coords = np.stack(
    [a[["pu_x", "pu_y"]].to_numpy(), a[["do_x", "do_y"]].to_numpy()], axis=1
)
lines = gpd.GeoDataFrame(
    {"distance": a["trip_distance"].to_numpy()},
    geometry=shapely.linestrings(coords),
    crs=4326,
)

# Step 5: one timestamp per vertex, same nesting as the geometry:
# [pickup, dropoff] for every trip.
pu = a["tpep_pickup_datetime"].to_numpy("datetime64[s]")
do = a["tpep_dropoff_datetime"].to_numpy("datetime64[s]")
ts = np.column_stack([pu, do]).ravel()
offsets = pa.array(np.arange(0, 2 * len(a) + 1, 2, dtype=np.int32))
timestamps = pa.ListArray.from_arrays(offsets, pa.array(ts, type=pa.timestamp("s")))

# Colour by trip distance, log scale.
d = np.log1p(lines["distance"].to_numpy())
norm = (d - d.min()) / (d.max() - d.min())
rgb = (mpl.colormaps["plasma"](norm)[:, :3] * 255).astype(np.uint8)

trips_layer = TripsLayer.from_geopandas(
    lines,
    get_timestamps=timestamps,
    get_color=rgb,
    width_min_pixels=2,
    trail_length=600,  # in data seconds: a 10 minute fading tail
    fade_trail=True,
    cap_rounded=True,
    pickable=False,  # faster, tooltips are not needed here
)

# Flat zone outlines underneath. Not extruded: tall columns would hide
# the trails, which are drawn at ground level.
base_layer = PolygonLayer.from_geopandas(
    polygons[["zone", "geometry"]],
    get_fill_color=[30, 40, 60, 255],
    get_line_color=[90, 110, 140],
    line_width_min_pixels=0.5,
    pickable=False,
)

m = Map(
    [base_layer, trips_layer],
    basemap=MaplibreBasemap(style=CartoStyle.DarkMatter),
    view_state={"longitude": -73.95, "latitude": 40.72, "zoom": 10.3, "pitch": 0},
    height="76vh",
)

# Step 6: time axis for the panel.
# animate() links a Play widget to the layer in the browser. The Play widget
# is not shown; we only read its range (start value and length in data
# seconds) and let our own panel drive it.
play = trips_layer.animate(step=timedelta(seconds=1)).children[0]
base = float(play.min)
duration = float(play.max) - base

t0 = ts.min()
expected = float((ts.max() - t0) / np.timedelta64(1, "s"))
if abs(expected - duration) > 1:
    print(f"WARNING: clock may be off (play range {duration:.0f} s, data {expected:.0f} s)")

# Trips in progress for every minute of the day (for the counter).
step_min = np.timedelta64(60, "s")
s_idx = ((pu - t0) // step_min).astype(int)
e_idx = ((do - t0) // step_min).astype(int)
n_min = int(expected // 60) + 2
diff = np.zeros(n_min + 1, dtype=int)
np.add.at(diff, s_idx, 1)
np.add.at(diff, e_idx + 1, -1)
active = np.cumsum(diff)[:n_min].tolist()

info = f"""
<h1>NYC yellow taxis on {DAY}</h1>
<p>Each streak is one taxi trip moving from its pickup zone to its dropoff zone,
for exactly as long as the trip lasted. The data has zone IDs, not GPS positions,
so streaks run in straight lines between zone centres, not along streets.
Showing a random sample of {len(a):,} of the {n_day:,} trips that started that day.</p>
<p>Colour = trip distance: short
<span class="tp-legend" style="background: {gradient_css('plasma')}"></span> long</p>
"""

panel = Panel(
    info=info,
    player={
        "base": base,
        "duration": duration,
        "t0_ms": int(t0.astype("datetime64[ms]").astype("int64")),
        "counts": active,
    },
    time=base,
)
link = jsdlink((panel, "time"), (play, "value"))  # panel clock -> Play -> layer

embed_minimal_html(
    "outputs/taxi_day_animation.html",
    views=[panel, m],
    title=f"NYC taxi day {DAY}",
    template=TEMPLATE,
    drop_defaults=False,
)
print("Animation saved to outputs/taxi_day_animation.html")
