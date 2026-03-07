import xml.etree.ElementTree as ET
import glob
import sys

def check_manifest(safe_dir):
    manifest = f"{safe_dir}/manifest.safe"
    try:
        tree = ET.parse(manifest)
        root = tree.getroot()
        # Find footprint
        ns = {'gml': 'http://www.opengis.net/gml'}
        coords = root.find('.//gml:coordinates', ns)
        if coords is not None:
            print(f"Footprint for {safe_dir}:")
            print(coords.text)
        else:
            print("No footprint found in manifest.")
    except Exception as e:
        print(f"Error parsing {manifest}: {e}")

if __name__ == "__main__":
    search_path = "/home/TheLowEnd/Documents/projects/kitagawa-backend/inference_images/*5F2A*.SAFE"
    matches = glob.glob(search_path)
    if matches:
        check_manifest(matches[0])
    else:
        print("Folder not found.")
