# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "datablob",
#     "requests",
#     "shapely>=2.2.0",
#     "simple-env",
# ]
# ///
import datablob
import math
import time
from requests import get
from shapely.geometry import shape
import simple_env as se

AWS_BUCKET_NAME = se.get("AWS_BUCKET_NAME")
if not AWS_BUCKET_NAME:
    raise Exception("[dataops-hamilton-county-parcels] missing AWS_BUCKET_NAME")

AWS_BUCKET_PATH = se.get("AWS_BUCKET_PATH")
if not AWS_BUCKET_PATH:
    raise Exception("[dataops-hamilton-county-parcels] missing AWS_BUCKET_PATH")

outFields = "*"

r = get(
    "https://mapsdev.hamiltontn.gov/hcwa03/rest/services/Live_Parcels/MapServer/1/query?where=1%3D1&text=&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&relationParam=&outFields=&returnGeometry=true&returnTrueCurves=false&maxAllowableOffset=&geometryPrecision=&outSR=&having=&returnIdsOnly=true&returnCountOnly=true&orderByFields=&groupByFieldsForStatistics=&outStatistics=&returnZ=false&returnM=false&gdbVersion=&historicMoment=&returnDistinctValues=false&resultOffset=&resultRecordCount=&queryByDistance=&returnExtentOnly=false&datumTransformation=&parameterValues=&rangeValues=&quantizationParameters=&f=json"
).json()

if "count" not in r:
    print(r)
    raise Exception("[dataops-hamilton-county-parcels] missing count")

count = r["count"]

num_pages = math.ceil(count / 1000)
print("[dataops-hamilton-county-parcels] number of pages:", num_pages)


# inspired by https://github.com/danieljdufour/get-depth
# determines how many nested levels are in a list
# ex: an array of coordinate pairs [(x0, y0), (x1, y1)] has a depth of 2
def get_depth(arr):
    depth = 0
    part = arr
    while isinstance(part, list) or isinstance(part, tuple):
        depth += 1
        part = part[0]
    return depth


# remove unnecessary decimal points
def trim_precision(it, num_digits=7):
    depth = get_depth(it)
    if isinstance(it, float):
        return round(it, num_digits)
    elif depth == 1:
        return [trim_precision(n, num_digits) for n in it]
    elif depth == 2 and len(it) == 2:
        # line segment, so we need to preserve both the starting and end point
        return [trim_precision(n, num_digits) for n in it]
    elif depth == 2:
        results = []
        for i in it:
            i = trim_precision(i, num_digits)
            # don't add the trimmed result if it's the same as the preceding vertex point
            if len(results) == 0 or i != results[-1]:
                results.append(i)
        return results
    else:
        # for polygons or multipolygons, recursively trim the containing rings of coordinates
        return [trim_precision(n, num_digits) for n in it]


rows = []
for i in range(num_pages):
    print("[dataops-hamilton-county-parcels] page:", i)
    time.sleep(5)
    url = f"https://mapsdev.hamiltontn.gov/hcwa03/rest/services/Live_Parcels/MapServer/1/query?where=1%3D1&geometryType=esriGeometryEnvelope&spatialRel=esriSpatialRelIntersects&outFields={outFields}&resultOffset={(i * 1000)}&returnGeometry=true&returnTrueCurves=false&returnIdsOnly=false&returnCountOnly=false&returnZ=false&returnM=false&returnDistinctValues=false&returnExtentOnly=false&f=geojson"
    for feature in get(url).json()["features"]:
        props = feature["properties"]
        geometry = feature["geometry"]

        geometry["coordinates"] = trim_precision(geometry["coordinates"])

        row = {**props}

        geom = shape(geometry)
        row["longitude"] = geom.centroid.x
        row["latitude"] = geom.centroid.y

        row["geometry"] = geometry

        rows.append(row)

client = datablob.DataBlobClient(
    bucket_name=AWS_BUCKET_NAME, bucket_path=AWS_BUCKET_PATH
)

client.update_dataset(
    name="hamilton_county_parcels",
    description="Parcels within Hamilton County.  This is an unofficial mirror.",
    version="1",
    data=rows,
    json=True,
    jsonl=True,
    latitude_key="latitude",
    longitude_key="longitude",
    polygon_key="geometry",
    parquet=True,
    xlsx=False,
)

print(f"[dataops-hamilton-county-parcels] updated {len(rows)} rows")
