import os
import json
import folium
from shapely.geometry import Polygon, mapping

# Load full data
detection_json_path = os.path.join("mnt", "results", "submissions", "detections.json")
with open(detection_json_path, "r") as f:
    data = json.load(f)
annotations = data["annotations"]
images = data["images"]
categories = {cat['id']: cat['name'] for cat in data["categories"]}

# Build image lookup dict by id for fast access
image_lookup = {img['id']: img for img in images}

def parse_bbox_to_coords(bbox_str):
    coords_str = bbox_str.replace('POLYGON ((', '').replace('))', '')
    coords = [tuple(map(float, pt.split())) for pt in coords_str.split(', ')]
    return coords

def get_sensor_type(filename):
    # Detect sentinel type from filename prefix (S1 or S2)
    if filename.startswith('S1'):
        return 'Sentinel-1'
    elif filename.startswith('S2'):
        return 'Sentinel-2'
    else:
        return 'Unknown'

# Assign colors for Sentinel types
color_map = {
    'Sentinel-1': 'blue',
    'Sentinel-2': 'green',
    'Unknown': 'gray'
}

features = []
for ann in annotations:
    img = image_lookup.get(ann["image_id"], {})
    filename = img.get("file_name", "N/A")
    date_captured = img.get("date_captured", "N/A")
    sensor_type = get_sensor_type(filename)
    coords = parse_bbox_to_coords(ann["bbox"])
    poly = Polygon(coords)

    feature = {
        "type": "Feature",
        "geometry": mapping(poly),
        "properties": {
            "id": ann["id"],
            "score": round(ann["score"], 3),
            "category": categories.get(ann["category_id"], "N/A"),
            "image_id": ann["image_id"],
            "filename": filename,
            "date_captured": date_captured,
            "sensor_type": sensor_type,
            "color": color_map.get(sensor_type, "gray")
        }
    }
    features.append(feature)

geojson_data = {
    "type": "FeatureCollection",
    "features": features
}

# Center map based on first polygon centroid
first_poly = Polygon(parse_bbox_to_coords(annotations[0]["bbox"]))
center = [first_poly.centroid.y, first_poly.centroid.x]

m = folium.Map(location=center, zoom_start=8, tiles="CartoDB positron")

def style_function(feature):
    return {
        "color": feature['properties']['color'],
        "weight": 2,
        "fillColor": feature['properties']['color'],
        "fillOpacity": 0.4,
    }

tooltip_fields = ['id', 'score', 'category', 'sensor_type']
tooltip_aliases = ['ID', 'Score', 'Category', 'Sensor Type']

popup_fields = ['filename', 'date_captured', 'sensor_type', 'category', 'id', 'score']
popup_labels = ['Image Filename:', 'Date Captured:', 'Sensor Type:', 'Category:', 'Annotation ID:', 'Score:']

folium.GeoJson(
    geojson_data,
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=tooltip_fields,
        aliases=tooltip_aliases,
        localize=True
    ),
    popup=folium.GeoJsonPopup(
        fields=popup_fields,
        aliases=popup_labels,
        localize=True,
        labels=True,
        style="background-color: white;"
    )
).add_to(m)

# Save the map as an HTML file at your desired path
output_path = os.path.join("mnt", "results", "additional_information", "imagery", "bbox_visualizations.html")
m.save(output_path)
print(f"Map saved to {output_path}")
