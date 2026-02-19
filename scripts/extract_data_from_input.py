# This script extracts image names from inference data and generates text
# files for downloading them.

import pandas as pd
import os

# Load CSV
image_data_csv = "../mnt/input/inference_sample_data/" \
    "Imagery_details_for_vessel_detection_and_AIS_correlation.csv"
df = pd.read_csv(image_data_csv, skip_blank_lines=True)

# Keep only rows where first column (S.No.) is numeric
df = df[pd.to_numeric(df.iloc[:, 0], errors='coerce').notna()]

# Make sure output folder exists
output_folder = "../mnt/data"

# All images (third column)
all_image_names = df.iloc[:, 2].astype(str).tolist()
with open(
    os.path.join(
        output_folder,
        "vessel_detection_image_names.txt"
    ),
    "w"
) as f:
    for name in all_image_names:
        f.write(name + "\n")

# AIS correlation images (rows where Remarks contain "For AIS correlations")
ais_image_names = df[df.iloc[:, 5].str.contains(
    "For AIS correlations", na=False)].iloc[:, 2].astype(str).tolist()
with open(
    os.path.join(
        output_folder,
        "AIS_correlation_image_names.txt"
    ),
    "w"
) as f:
    for name in ais_image_names:
        f.write(name + "\n")

print("Files created successfully!")
