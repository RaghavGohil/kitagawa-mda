import os
import pandas as pd
import folium

# Define base mount path and file paths using os.path.join
original_csv_path = os.path.join(
    "mnt", "input", "inference_sample_data", "Test_data_for_interpolation.csv")
interpolated_csv_path = os.path.join(
    "mnt", "results", "submissions", "ais_interpolated_data.csv")

# Load the data
original_df = pd.read_csv(original_csv_path)
interpolated_df = pd.read_csv(interpolated_csv_path)

# Convert time_stamp to datetime
original_df['time_stamp'] = pd.to_datetime(
    original_df['time_stamp'], format='mixed')
interpolated_df['time_stamp'] = pd.to_datetime(
    interpolated_df['time_stamp'], format='mixed')

# Filter out rows with NaN coordinates
original_df = original_df.dropna(subset=['point_latitude', 'point_longitude'])
interpolated_df = interpolated_df.dropna(
    subset=['point_latitude', 'point_longitude'])

# Sort by path_id and time_stamp
original_df = original_df.sort_values(
    ['path_id', 'time_stamp']).reset_index(drop=True)
interpolated_df = interpolated_df.sort_values(
    ['path_id', 'time_stamp']).reset_index(drop=True)

# Calculate the center point for the map
center_lat = original_df['point_latitude'].mean()
center_lon = original_df['point_longitude'].mean()

# Create the map
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=10,
    tiles='OpenStreetMap'
)

# Define colors for different paths
colors = ['black', 'blue', 'purple', 'darkgreen',
          'orange', 'darkred', 'cadetblue']

# Get unique path_ids
path_ids = interpolated_df['path_id'].unique()
print(f"Found {len(path_ids)} unique paths: {path_ids}")

# Process each path separately
for idx, path_id in enumerate(path_ids):
    path_color = colors[idx % len(colors)]

    # Get data for this specific path
    path_interpolated = interpolated_df[interpolated_df['path_id'] == path_id]
    path_original = original_df[original_df['path_id'] == path_id]

    print(f"Path {path_id}: {len(path_original)} original points, {len(path_interpolated)} interpolated points")

    # Add interpolated path as lines for THIS path only
    interpolated_coordinates = [
        [row['point_latitude'], row['point_longitude']]
        for _, row in path_interpolated.iterrows()
    ]

    if len(interpolated_coordinates) > 0:
        folium.PolyLine(
            locations=interpolated_coordinates,
            color=path_color,
            weight=2,
            opacity=0.8,
            popup=f'Path {path_id}'
        ).add_to(m)

    # Add interpolated points as small circles
    for _, row in path_interpolated.iterrows():
        folium.CircleMarker(
            location=[row['point_latitude'], row['point_longitude']],
            radius=2,
            color=path_color,
            fill=True,
            fillColor=path_color,
            fillOpacity=0.4,
            popup=f"Path {row['path_id']}<br>"
            f"Point {row['point_id']}<br>"
            f"Time: {row['time_stamp'].strftime('%H:%M:%S')}<br>"
            f"Speed: {row['speed_on_ground']} knots<br>"
            f"Course: {row['course_on_ground']}°"
        ).add_to(m)

    # Add original AIS points as red markers for THIS path
    for _, row in path_original.iterrows():
        folium.CircleMarker(
            location=[row['point_latitude'], row['point_longitude']],
            radius=6,
            color='red',
            fill=True,
            fillColor='red',
            fillOpacity=0.9,
            popup=f"<b>Original AIS Point</b><br>"
                  f"Path: {row['path_id']}<br>"
                  f"Point: {row['point_id']}<br>"
                  f"Time: {row['time_stamp'].strftime('%H:%M:%S')}<br>"
                  f"Lat: {row['point_latitude']:.5f}<br>"
                  f"Lon: {row['point_longitude']:.5f}<br>"
                  f"Speed: {row['speed_on_ground']} knots<br>"
                  f"Course: {row['course_on_ground']}°",
            tooltip=f"Path {row['path_id']}"
        ).add_to(m)

    # Add start/end markers for THIS path
    if len(path_original) > 0:
        first_point = path_original.iloc[0]
        last_point = path_original.iloc[-1]

        # Start marker (green)
        folium.Marker(
            location=[first_point['point_latitude'],
                      first_point['point_longitude']],
            popup=f"Start Path {path_id}<br>{first_point['time_stamp'].strftime('%H:%M:%S')}",
            icon=folium.Icon(color='green', icon='play', prefix='fa'),
            tooltip=f'Start Path {path_id}'
        ).add_to(m)

        # End marker (blue)
        folium.Marker(
            location=[last_point['point_latitude'],
                      last_point['point_longitude']],
            popup=f"End Path {path_id}<br>{last_point['time_stamp'].strftime('%H:%M:%S')}",
            icon=folium.Icon(color='blue', icon='stop', prefix='fa'),
            tooltip=f'End Path {path_id}'
        ).add_to(m)

# Add a legend
legend_html = '''
<div style="position: fixed; 
            bottom: 50px; right: 50px; width: 220px; height: auto; 
            background-color: white; border:2px solid grey; z-index:9999; 
            font-size:14px; padding: 10px">
<p style="margin: 0;"><b>Legend</b></p>
<p style="margin: 5px 0;">
    <span style="color: red; font-size: 20px;">●</span> Original AIS Points
</p>
<p style="margin: 5px 0;">
    <span style="color: black; font-size: 16px;">●</span> Interpolated Points
</p>
<p style="margin: 5px 0;">
    <span style="color: black;">━━</span> Interpolated Path
</p>
<p style="margin: 5px 0; font-size: 12px; color: #666;">
    Each path_id has a different color
</p>
</div>
'''
m.get_root().html.add_child(folium.Element(legend_html))

# Define output path and ensure directory exists
output_dir = os.path.join("mnt", "results",
                          "additional_information", "AIS")
os.makedirs(output_dir, exist_ok=True)

output_map_path = os.path.join(output_dir, "ais_interpolation_data.html")
m.save(output_map_path)

print(f"\n✅ Map saved as '{output_map_path}'")
print(f"Total paths: {len(path_ids)}")
print(f"Total original points: {len(original_df)}")
print(f"Total interpolated points: {len(interpolated_df)}")
