import requests
from bs4 import BeautifulSoup
import os
from tqdm import tqdm
import re
import zipfile
import zstandard as zstd

OUTPUT_DIR = "../mnt/data/AIS"
AIS_IMAGE_CORRELATION_PATH = "../mnt/data/AIS_correlation_image_names.txt"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Read SAFE filenames
with open(AIS_IMAGE_CORRELATION_PATH, "r") as f:
    safe_files = [line.strip() for line in f if line.strip()]

dates_by_year = {}
for filename in safe_files:
    match = re.search(r"(\d{8})T\d{6}", filename)
    if match:
        yyyymmdd = match.group(1)
        year = int(yyyymmdd[:4])
        if year <= 2024:
            date_formatted = f"{yyyymmdd[:4]}_{yyyymmdd[4:6]}_{yyyymmdd[6:]}"
            extracted_filename = f"AIS_{date_formatted}.csv"
        else:
            date_formatted = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
            extracted_filename = f"ais-{date_formatted}.csv"
        dates_by_year.setdefault(year, []).append((date_formatted,
                                                   extracted_filename))


def extract_zip(zip_path, dest_dir):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
        print(f"Extracted ZIP: {zip_path}")
    except Exception as e:
        print(f"Error extracting ZIP {zip_path}: {e}")


def extract_zst(zst_path, dest_dir, csv_filename):
    try:
        output_csv_path = os.path.join(dest_dir, csv_filename)
        with open(zst_path, 'rb') as compressed, open(output_csv_path, 'wb') \
                as decompressed:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(compressed) as reader:
                for chunk in iter(lambda: reader.read(16384), b''):
                    decompressed.write(chunk)
        print(f"Decompressed ZST: {zst_path} -> {output_csv_path}")
    except Exception as e:
        print(f"Error decompressing ZST {zst_path}: {e}")


for year, year_dates in dates_by_year.items():
    base_url = f"https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/index.html"
    print(f"\nYear {year} at {base_url}")
    resp = requests.get(base_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True)]
    base_prefix = base_url.rsplit("/", 1)[0]

    for date_formatted, extracted_filename in year_dates:
        final_csv_path = os.path.join(OUTPUT_DIR, extracted_filename)
        if os.path.exists(final_csv_path):
            print(f"Skipping existing: {extracted_filename}")
            continue

        if year <= 2024:
            archive_filename = f"AIS_{date_formatted}.zip"
        else:
            archive_filename = f"ais-{date_formatted}.csv.zst"

        archive_path = os.path.join(OUTPUT_DIR, archive_filename)
        temp_path = archive_path + ".part"

        if os.path.exists(final_csv_path):
            print(
                f"Final CSV {final_csv_path} exists, \
                skipping download/extract.")
            continue

        if os.path.exists(archive_path):
            print(f"Archive already downloaded: {archive_filename}")
        else:
            # Find link in page
            file_link = None
            for link in links:
                if link.lower() == archive_filename.lower():
                    file_link = link if link.startswith(
                        "http") else f"{base_prefix}/{link}"
                    break

            if not file_link:
                print(f"File {archive_filename} not found at {base_url}")
                continue

            print(f"Downloading: {archive_filename} ...")
            try:
                with requests.get(file_link, stream=True) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0))
                    with open(temp_path, "wb") as f, tqdm(
                        total=total_size, unit="B", unit_scale=True,
                        desc=archive_filename
                    ) as bar:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))
                os.rename(temp_path, archive_path)
                print(f"Downloaded {archive_filename}")
            except Exception as e:
                print(f"Error downloading {archive_filename}: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

        # Extraction
        if archive_path.endswith(".zip"):
            extract_zip(archive_path, OUTPUT_DIR)
        elif archive_path.endswith(".zst"):
            extract_zst(archive_path, OUTPUT_DIR, extracted_filename)
        else:
            print(
                f"Unknown file type for {archive_path}, skipping extraction.")

print(f"\nAll downloads and extractions completed into {OUTPUT_DIR}")
