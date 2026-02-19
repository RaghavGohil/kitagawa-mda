# non maximal suppression filter
import os
import glob
import pandas as pd
import torch
from torchvision.ops import nms

# ---------------------------
# Base path
# ---------------------------
detections_dir = os.path.join("mnt", "data", "detections")

# ---------------------------
# List all CSVs
# ---------------------------
csv_paths = glob.glob(os.path.join(detections_dir, "*.csv"))

if not csv_paths:
    raise RuntimeError(f"No CSV files found in {detections_dir}")


# ---------------------------
# NMS helper (no warnings)
# ---------------------------
def do_nms(df):
    """
    Performs NMS per image_name.
    """
    # Select only bbox + score columns once (no group-level warnings)
    groups = df.groupby("image_name")

    kept_rows = []

    for _ , group in groups:
        boxes = torch.tensor(group[['xmin', 'ymin', 'xmax', 'ymax']].values, dtype=torch.float32)
        scores = torch.tensor(group['confidence'].values, dtype=torch.float32)

        keep_idx = nms(boxes, scores, 0).numpy()
        kept_rows.append(group.iloc[keep_idx])

    if kept_rows:
        return pd.concat(kept_rows, ignore_index=True)
    else:
        return pd.DataFrame(columns=df.columns)


# ---------------------------
# Process and overwrite each CSV
# ---------------------------
for path in csv_paths:
    df = pd.read_csv(path)
    before_count = len(df)

    filtered = do_nms(df)
    after_count = len(filtered)
    removed = before_count - after_count

    # Overwrite file
    filtered.to_csv(path, index=False)

    print(
        f"{os.path.basename(path)}: "
        f"original={before_count}, kept={after_count}, removed={removed}"
    )

print("\nAll detection CSVs updated with NMS.")