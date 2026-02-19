import warnings
from scipy.interpolate import CubicHermiteSpline, interp1d
import numpy as np
import pandas as pd
import os
warnings.filterwarnings('ignore')

INPUT_BASE_DIR = os.path.join("mnt", "input", "inference_sample_data")
OUTPUT_DIR = os.path.join("mnt", "results", "submissions")

# Read CSV
df = pd.read_csv(f"{INPUT_BASE_DIR}/Test_data_for_interpolation.csv")
df['time_stamp'] = pd.to_datetime(df['time_stamp'], format='mixed')
df = df.sort_values(['path_id', 'time_stamp']).reset_index(drop=False)

print(
    f"Data sorted by time. Time range: {df['time_stamp'].min()} to {df['time_stamp'].max()}")
print(f"Unique path_ids: {df['path_id'].unique()}")

# Convert columns to numeric
cols_to_interpolate = ['point_latitude',
                       'point_longitude', 'speed_on_ground', 'course_on_ground']
df[cols_to_interpolate] = df[cols_to_interpolate].apply(
    pd.to_numeric, errors='coerce')


def calculate_velocity_components(lat, lon, sog, cog):
    """
    Calculate velocity components from SOG and COG for physics-based interpolation
    """
    sog_ms = sog * 0.514444  # knots to m/s
    cog_rad = np.radians(cog)
    v_north = sog_ms * np.cos(cog_rad)
    v_east = sog_ms * np.sin(cog_rad)
    v_lat = v_north / 111320.0  # degrees/second
    v_lon = v_east / (111320.0 * np.cos(np.radians(lat)))  # degrees/second
    return v_lat, v_lon


def interpolate_path_full(group):
    """
    Physics-based interpolation that fills ALL rows regardless of time gaps
    """
    group = group.copy()
    valid_mask = group['point_latitude'].notna(
    ) & group['point_longitude'].notna()
    valid_points = group[valid_mask].copy()

    if len(valid_points) < 2:
        return group

    # Interpolate across entire trajectory (no segmentation)
    seg_start = valid_points['time_stamp'].min()
    t_valid = (valid_points['time_stamp'] -
               seg_start).dt.total_seconds().values
    t_all = (group['time_stamp'] - seg_start).dt.total_seconds().values

    lat_valid = valid_points['point_latitude'].values
    lon_valid = valid_points['point_longitude'].values
    sog_valid = valid_points['speed_on_ground'].fillna(
        method='ffill').fillna(method='bfill').fillna(0).values
    cog_valid = valid_points['course_on_ground'].fillna(
        method='ffill').fillna(method='bfill').fillna(0).values

    # Calculate velocity components at each valid point
    v_lat = np.zeros_like(lat_valid)
    v_lon = np.zeros_like(lon_valid)

    for i in range(len(lat_valid)):
        v_lat[i], v_lon[i] = calculate_velocity_components(
            lat_valid[i], lon_valid[i], sog_valid[i], cog_valid[i])

    try:
        # Cubic Hermite spline interpolation with velocity constraints
        spline_lat = CubicHermiteSpline(t_valid, lat_valid, v_lat)
        spline_lon = CubicHermiteSpline(t_valid, lon_valid, v_lon)
        lat_interp = spline_lat(t_all)
        lon_interp = spline_lon(t_all)

        # Cubic spline for SOG
        sog_interp = interp1d(t_valid, sog_valid, kind='cubic',
                              fill_value='extrapolate')(t_all)

        # Circular interpolation for COG (handles angle wrapping)
        cog_rad = np.radians(cog_valid)
        cos_cog = np.cos(cog_rad)
        sin_cog = np.sin(cog_rad)

        cos_interp = interp1d(t_valid, cos_cog, kind='cubic',
                              fill_value='extrapolate')(t_all)
        sin_interp = interp1d(t_valid, sin_cog, kind='cubic',
                              fill_value='extrapolate')(t_all)
        cog_interp = np.degrees(np.arctan2(sin_interp, cos_interp)) % 360

        # Clip SOG to reasonable values
        sog_interp = np.clip(sog_interp, 0, max(sog_valid) * 1.5)

        # Fill ALL points (every row) with interpolated values
        group['point_latitude'] = lat_interp
        group['point_longitude'] = lon_interp
        group['speed_on_ground'] = sog_interp
        group['course_on_ground'] = cog_interp

    except Exception as e:
        print(f"  Spline interpolation failed, using linear fallback: {e}")
        # Fallback: linear interpolation
        for col, vals_valid in [('point_latitude', lat_valid), ('point_longitude', lon_valid),
                                ('speed_on_ground', sog_valid), ('course_on_ground', cog_valid)]:
            group[col] = np.interp(t_all, t_valid, vals_valid)

    return group


# Apply interpolation to each path
print("\nStarting physics-based interpolation (filling all points)...")
df_interpolated = df.groupby(
    'path_id', group_keys=False).apply(interpolate_path_full)

# Final fill: ensure no NaNs remain (for edge cases)
df_interpolated[cols_to_interpolate] = df_interpolated[cols_to_interpolate].fillna(
    method='ffill').fillna(method='bfill')

# Restore original row order
df_interpolated = df_interpolated.sort_values('index').reset_index(drop=True)

# Save results
os.makedirs(OUTPUT_DIR, exist_ok=True)
df_interpolated.to_csv(os.path.join(
    OUTPUT_DIR, 'ais_interpolated_data.csv'), index=False)

print("\n✅ Interpolation complete with all original points filled!")
print(f"Total points: {len(df_interpolated)}")
print(f"Original points in input: {len(df)}")
print(
    f"All NaNs filled: {df_interpolated[cols_to_interpolate].isna().sum().sum() == 0}")
print("\n💾 Saved to results/AIS_interpolated_data.csv")
