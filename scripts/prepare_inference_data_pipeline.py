import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# -------------------------------------------------------------------
# Task functions
# -------------------------------------------------------------------

def extract_data_from_input():
    print("Running extract_data_from_input.py...")
    subprocess.run(["python", "extract_data_from_input.py"], check=True)

def download_AIS_data(retries=3, retry_delay_seconds=10):
    for attempt in range(1, retries + 1):
        try:
            print("Downloading AIS data...")
            subprocess.run(["python", "download_AIS_data.py"], check=True)
            return
        except subprocess.CalledProcessError as e:
            print(f"Attempt {attempt} failed for AIS data: {e}")
            if attempt < retries:
                time.sleep(retry_delay_seconds)
            else:
                raise

def download_image_data(retries=3, retry_delay_seconds=10):
    for attempt in range(1, retries + 1):
        try:
            print("Downloading image data...")
            subprocess.run(["python", "download_image_data.py"], check=True)
            return
        except subprocess.CalledProcessError as e:
            print(f"Attempt {attempt} failed for image data: {e}")
            if attempt < retries:
                time.sleep(retry_delay_seconds)
            else:
                raise

def download_landmask(retries=3, retry_delay_seconds=10):
    for attempt in range(1, retries + 1):
        try:
            print("Downloading landmask data...")
            subprocess.run(["python", "download_landmask.py"], check=True)
            return
        except subprocess.CalledProcessError as e:
            print(f"Attempt {attempt} failed for landmask data: {e}")
            if attempt < retries:
                time.sleep(retry_delay_seconds)
            else:
                raise

# -------------------------------------------------------------------
# Pipeline
# -------------------------------------------------------------------

def prepare_inference_data_pipeline():
    # Step 1: Extract data
    extract_data_from_input()

    # Step 2: Run download tasks concurrently
    tasks = [download_AIS_data, download_image_data, download_landmask]

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(task) for task in tasks]
        for future in as_completed(futures):
            # Raises exception if task failed
            future.result()

# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs('../mnt/data', exist_ok=True)
    prepare_inference_data_pipeline()
