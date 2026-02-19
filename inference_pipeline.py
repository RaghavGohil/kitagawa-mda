import subprocess
from prefect import flow, task
import os

# -------------------------------------------------------------------
# Model inferencing
# -------------------------------------------------------------------
@task(name="Run SAR (synthetic aperture radar) inference")
def run_inference_SAR():
    subprocess.run(
        ["python", "inference/imagery/SAR/inference.py"], check=True)


@task(name="Run EO (electro-optical) inference")
def run_inference_EO():
    subprocess.run(["python", "inference/imagery/EO/inference.py"], check=True)


# -------------------------------------------------------------------
# Filtering predictions
# -------------------------------------------------------------------
@task(name="Run NMS filter for both SAR and EO")
def run_nms_filter():
    subprocess.run(["python", "inference/filter/nms_filter.py"], check=True)


@task(name="Run landmask filter for both SAR and EO")
def run_landmask_filter():
    subprocess.run(["python", "inference/filter/landmask_filter.py"], check=True)


@task(name="Run cloudmask filter for EO")
def run_cloudmask_filter():
    subprocess.run(
        ["python", "inference/filter/cloudmask_filter.py"], check=True)


# -------------------------------------------------------------------
# Detection datetime generation
# -------------------------------------------------------------------
@task(name="Generate detection datetime for both SAR")
def generate_detection_datetime_SAR():
    subprocess.run(
        ["python", "inference/imagery/SAR/generate_detection_datetime_SAR.py"],
        check=True,
    )


@task(name="Generate detection datetime for both EO")
def generate_detection_datetime_EO():
    subprocess.run(
        ["python", "inference/imagery/EO/generate_detection_datetime_EO.py"],
        check=True,
    )


# -------------------------------------------------------------------
# Generation of result files
# -------------------------------------------------------------------
@task(name="Generate detection json file")
def generate_detection_json_file():
    subprocess.run(
        ["python", "inference/imagery/generate_detection_json_file.py"],
        check=True,
    )


@task(name="Generate detection shape files")
def generate_detection_shape_files():
    subprocess.run(
        ["python", "inference/imagery/generate_detection_shape_files.py"],
        check=True,
    )


@task(name="Generate interpolated AIS tracks")
def generate_AIS_interpolation_file():
    subprocess.run(
        ["python", "inference/AIS/generate_AIS_interpolated_file.py"],
        check=True
    )


@task(name="Generate AIS image correlation files")
def generate_AIS_correlation_file():
    subprocess.run(
        ["python", "inference/AIS/generate_AIS_correlation_file.py"],
        check=True
    )


# -------------------------------------------------------------------
# Visualization
# -------------------------------------------------------------------
@task(name="Generate SAR visualizations")
def generate_SAR_visualizations():
    subprocess.run(
        [
            "python",
            "inference/imagery/SAR/generate_inference_visualizations.py"
        ],
        check=True
    )


@task(name="Generate EO visualizations")
def generate_EO_visualizations():
    subprocess.run(
        [
            "python",
            "inference/imagery/EO/generate_inference_visualizations.py"
        ],
        check=True,
    )


@task(name="Generate bbox visualizations")
def generate_bbox_visualizations():
    subprocess.run(
        ["python", "inference/imagery/generate_bbox_visualizations.py"],
        check=True
    )


@task(name="Generate AIS interpolation visualization")
def generate_AIS_interpolation_visualization():
    subprocess.run(
        [
            "python",
            "inference/AIS/generate_AIS_interpolation_visualization.py"
        ],
        check=True,
    )


@task(name="Generate AIS correlation visualizations")
def generate_AIS_correlation_visualizations():
    subprocess.run(
        ["python", "inference/AIS/generate_AIS_correlation_visualizations.py"],
        check=True,
    )

@task(name="Generate AIS track visualizations")
def generate_AIS_track_visualizations():
    subprocess.run(
        ["python", "inference/AIS/generate_AIS_track_visualizations.py"],
        check=True,
    )



# -------------------------------------------------------------------
# Flow definition
# -------------------------------------------------------------------
@flow(name="Inference pipeline flow")
def inference_pipeline():

    run_inference_SAR()
    run_inference_EO()

    run_nms_filter()
    run_landmask_filter()
    run_cloudmask_filter()

    generate_detection_datetime_SAR()
    generate_detection_datetime_EO()

    generate_detection_json_file()
    generate_detection_shape_files()
    generate_AIS_interpolation_file()
    generate_AIS_correlation_file()

    generate_SAR_visualizations()
    generate_EO_visualizations()
    generate_bbox_visualizations()
    generate_AIS_interpolation_visualization()
    generate_AIS_correlation_visualizations()
    generate_AIS_track_visualizations()


if __name__ == "__main__":
    os.makedirs(os.path.join("mnt", "data"), exist_ok=True)
    inference_pipeline()
