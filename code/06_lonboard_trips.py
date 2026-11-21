import duckdb
import geopandas as gpd
import matplotlib as mpl
import numpy as np
import pyarrow as pa
import shapely
from ipywidgets import jsdlink
from ipywidgets.embed import embed_minimal_html
from lonboard import ArcLayer, Map, ScatterplotLayer
from lonboard.basemap import CartoStyle, MaplibreBasemap
from lonboard.layer_extension import BrushingExtension

from taxi_panel import TEMPLATE, Panel, gradient_css

DB_FILE = "data/taxi.duckdb"
N_TRIPS = 100_000  
ARC_OPACITY = 0.1  # starting values of the sliders
BRUSH_RADIUS = 1500  # meters

JITTER = False

rng = np.random.default_rng(42)

# Step 1: random sample of trips from DuckDB, with zone names for tooltips.
con = duckdb.connect(DB_FILE, read_only=True)
trips = con.execute(
    f"""
    SELECT t.PULocationID, t.DOLocationID, t.total_amount, t.trip_distance,
           pz.Zone AS pickup_zone, dz.Zone AS dropoff_zone
    FROM trips_clean t
    JOIN zones pz ON pz.LocationID = t.PULocationID
    JOIN zones dz ON dz.LocationID = t.DOLocationID
    WHERE t.PULocationID <> t.DOLocationID
      AND t.total_amount > 0 AND t.trip_distance > 0
    ORDER BY random()
    LIMIT {N_TRIPS}
    """
).fetchdf()

total = con.execute("SELECT count(*) FROM trips_clean").fetchone()[0]

first, last = con.execute(
    "SELECT min(tpep_pickup_datetime), max(tpep_pickup_datetime) FROM trips_clean"
).fetchone()

con.close()
print("trips sampled:", len(trips), "of", total)

# Step 2: zone centroids. Dissolve first: if a LocationID is split over
# several rows in the shapefile, a plain join would duplicate its trips.
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

pu_xy = np.column_stack([a["pu_x"], a["pu_y"]]).astype("float64")
do_xy = np.column_stack([a["do_x"], a["do_y"]]).astype("float64")


def random_points_in_zones(zone_ids, zones):
    """One random point inside each trip's zone polygon, as an (n, 2) array."""
    poly_by_id = zones.set_index("LocationID").geometry
    out = np.empty((len(zone_ids), 2))
    for zid in np.unique(zone_ids):
        idx = np.flatnonzero(zone_ids == zid)
        poly = poly_by_id[zid]
        minx, miny, maxx, maxy = poly.bounds
        xs, ys = np.empty(0), np.empty(0)
        while len(xs) < len(idx):  # rejection sampling inside the bounding box
            cx = rng.uniform(minx, maxx, 2 * len(idx) + 10)
            cy = rng.uniform(miny, maxy, 2 * len(idx) + 10)
            ok = shapely.contains_xy(poly, cx, cy)
            xs = np.concatenate([xs, cx[ok]])
            ys = np.concatenate([ys, cy[ok]])
        out[idx, 0] = xs[: len(idx)]
        out[idx, 1] = ys[: len(idx)]
    return out


if JITTER:
    pu_xy = random_points_in_zones(a["PULocationID"].to_numpy(), polygons)
    do_xy = random_points_in_zones(a["DOLocationID"].to_numpy(), polygons)

# Step 4: colours from total fare, $1 to $50+, like the original example.
norm = np.clip((a["total_amount"].to_numpy() - 1) / (50 - 1), 0, 1)
rgba = (mpl.colormaps["BrBG"](norm) * 255).astype(np.uint8)
rgba[:, 3] = 180

# Step 5: layers. Arcs need no geometry column, the positions are passed
# separately; the table only carries the attributes for tooltips.
table = pa.Table.from_pandas(
    a[["pickup_zone", "dropoff_zone", "total_amount", "trip_distance"]],
    preserve_index=False,
)
arc_layer = ArcLayer(
    table,
    get_source_position=pu_xy,
    get_target_position=do_xy,
    get_source_color=rgba,
    get_target_color=rgba,
    get_width=a["trip_distance"].to_numpy(),
    width_units="meters",
    width_min_pixels=0.2,
    opacity=ARC_OPACITY,
    auto_highlight=True,
    extensions=[BrushingExtension()],
)

pickups = gpd.GeoDataFrame(
    a[["pickup_zone", "total_amount"]].reset_index(drop=True),
    geometry=gpd.points_from_xy(pu_xy[:, 0], pu_xy[:, 1]),
    crs=4326,
)
pickup_layer = ScatterplotLayer.from_geopandas(
    pickups,
    get_fill_color=rgba,
    get_radius=norm * 90,
    radius_units="meters",
    radius_min_pixels=0.1,
    auto_highlight=True,
    extensions=[BrushingExtension()],
)
for layer in (arc_layer, pickup_layer):
    layer.brushing_enabled = False
    layer.brushing_radius = BRUSH_RADIUS

m = Map(
    [arc_layer, pickup_layer],
    basemap=MaplibreBasemap(style=CartoStyle.Positron),
    view_state={
        "longitude": -73.92655,
        "latitude": 40.70598,
        "zoom": 10,
        "pitch": 44.7,
        "bearing": 60.6,
    },
    height="76vh",
)

# Step 6: info text and controls, linked to the layers in the browser.
ends = (
    "random points inside the pickup and dropoff zones (not the real positions)"
    if JITTER
    else "the centre of the pickup and dropoff zones"
)
info = f"""
<h1>NYC yellow taxi trips: pickup to dropoff</h1>
<p>Each arc is one trip, from its pickup to its dropoff. Random sample of
{len(a):,} of the {total:,} trips in the database
({first:%Y-%m-%d} to {last:%Y-%m-%d}). The data has zone IDs, not GPS
positions, so arc ends sit at {ends}.</p>
<p>Colour of arcs and pickup dots = total fare: $1
<span class="tp-legend" style="background: {gradient_css('BrBG')}"></span> $50+.
Arc width = trip distance. Hover an arc or dot for details.
With brushing on, only trips near the mouse pointer are shown.</p>
"""

panel = Panel(
    info=info,
    controls=[
        {"id": "show_arcs", "kind": "checkbox", "label": "Render trips"},
        {"id": "show_pickups", "kind": "checkbox", "label": "Render pickups"},
        {"id": "brushing", "kind": "checkbox", "label": "Brushing (hover the map)"},
        {"id": "arc_opacity", "kind": "slider", "label": "Arc opacity",
         "min": 0, "max": 1, "step": 0.01},
        {"id": "brush_radius", "kind": "slider", "label": "Brushing radius (m)",
         "min": 200, "max": 5000, "step": 100},
    ],
    arc_opacity=ARC_OPACITY,
    brush_radius=float(BRUSH_RADIUS),
)
links = [
    jsdlink((panel, "show_arcs"), (arc_layer, "visible")),
    jsdlink((panel, "show_pickups"), (pickup_layer, "visible")),
    jsdlink((panel, "brushing"), (arc_layer, "brushing_enabled")),
    jsdlink((panel, "brushing"), (pickup_layer, "brushing_enabled")),
    jsdlink((panel, "arc_opacity"), (arc_layer, "opacity")),
    jsdlink((panel, "brush_radius"), (arc_layer, "brushing_radius")),
    jsdlink((panel, "brush_radius"), (pickup_layer, "brushing_radius")),
]

embed_minimal_html(
    "outputs/taxi_trips_explorer.html",
    views=[panel, m],
    title="NYC taxi trips explorer",
    template=TEMPLATE,
    drop_defaults=False,
)
print("Saved outputs/taxi_trips_explorer.html")
