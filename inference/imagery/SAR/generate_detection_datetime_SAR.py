# get the detection datetime
import os
import csv
import sys
from datetime import datetime, timedelta
import numpy as np
import xml.etree.ElementTree as ET

# ------------------- Config -------------------
root_data_dir = os.path.join("mnt", "data", "inference_images")
csv_file = os.path.join("mnt", "data",
                        "detections", "detections_s1.csv")

# ------------------- Calibration cache -------------------
_calib_cache = {}  # safe_name -> interpolator function or None


def _find_safe_folder(image_name: str) -> str:
    safe_path = os.path.join(root_data_dir, image_name)
    if os.path.isdir(safe_path):
        return safe_path
    for f in os.listdir(root_data_dir):
        if f.startswith(image_name) and f.endswith(".SAFE"):
            cand = os.path.join(root_data_dir, f)
            if os.path.isdir(cand):
                return cand
    return None


def _build_line_time_interpolator(safe_folder: str):
    annot_calib_dir = os.path.join(safe_folder, "annotation", "calibration")
    if not os.path.isdir(annot_calib_dir):
        return None

    calib_xml = None
    for f in os.listdir(annot_calib_dir):
        if f.lower().startswith("calibration-s1a-iw-grd-vv-") and f.lower().endswith(".xml"):
            calib_xml = os.path.join(annot_calib_dir, f)
            break
    if calib_xml is None:
        return None

    try:
        tree = ET.parse(calib_xml)
    except Exception as e:
        print(
            f"[WARN] Failed to parse calibration XML for {safe_folder}: {e}", file=sys.stderr)
        return None

    root = tree.getroot()
    ns = {}
    if "}" in root.tag:
        ns["s1"] = root.tag.split("}")[0].strip("{")

    lines = []
    times = []

    for cv in root.findall(".//calibrationVectorList/calibrationVector", ns):
        az_el = cv.find("azimuthTime", ns)
        line_el = cv.find("line", ns)
        if az_el is None or line_el is None:
            continue
        try:
            t = datetime.fromisoformat(az_el.text)
            num_l = int(line_el.text)
        except Exception:
            continue
        lines.append(num_l)
        times.append(t)

    if len(lines) < 2:
        print(
            f"[WARN] Not enough calibration vectors in {calib_xml}", file=sys.stderr)
        return None

    order = np.argsort(lines)
    lines = np.array(lines, dtype=np.float64)[order]
    times = [times[i] for i in order]

    base = times[0]
    time_seconds = np.array([(t - base).total_seconds()
                            for t in times], dtype=np.float64)

    def line_to_time(line_idx_float: float) -> str:
        num_l = float(line_idx_float)
        if num_l <= lines[0]:
            dt_sec = time_seconds[0]
        elif num_l >= lines[-1]:
            dt_sec = time_seconds[-1]
        else:
            idx = np.searchsorted(lines, num_l)
            l1, l2 = lines[idx - 1], lines[idx]
            t1, t2 = time_seconds[idx - 1], time_seconds[idx]
            if l2 == l1:
                dt_sec = t1
            else:
                w = (num_l - l1) / (l2 - l1)
                dt_sec = t1 + w * (t2 - t1)

        dt = timedelta(seconds=float(dt_sec))
        t_interp = base + dt
        return t_interp.strftime("%Y-%m-%dT%H:%M:%S")

    return line_to_time


def get_line_time_interpolator_for_safe(safe_name: str):
    if safe_name in _calib_cache:
        return _calib_cache[safe_name]

    safe_folder = _find_safe_folder(safe_name)
    if safe_folder is None:
        print(f"[WARN] SAFE folder not found for {safe_name}", file=sys.stderr)
        _calib_cache[safe_name] = None
        return None

    interp = _build_line_time_interpolator(safe_folder)
    _calib_cache[safe_name] = interp
    return interp


def main():
    if not os.path.exists(csv_file):
        print(f"[ERR] CSV file not found: {csv_file}", file=sys.stderr)
        sys.exit(1)

    with open(csv_file, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames if reader.fieldnames else []
        if "detection_datetime" not in fieldnames:
            fieldnames.append("detection_datetime")

    n_with_time = 0
    # Compute detection_datetime for each row
    for row in rows:
        try:
            safe_name = row["image_name"]
            ymin = float(row["ymin"])
            ymax = float(row["ymax"])
            line_idx = 0.5 * (ymin + ymax)
        except Exception:
            row["detection_datetime"] = ""
            continue

        interp = get_line_time_interpolator_for_safe(safe_name)
        if interp is None:
            row["detection_datetime"] = ""
        else:
            try:
                row["detection_datetime"] = interp(line_idx)
                n_with_time += 1
            except Exception:
                row["detection_datetime"] = ""

    # Overwrite the original CSV with the new column and values
    with open(csv_file, "w", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"✅ Updated {csv_file} with detection_datetime for {n_with_time} rows.")


if __name__ == "__main__":
    main()
