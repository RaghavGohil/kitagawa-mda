import geopandas as gpd
import os

shp_path = "/home/TheLowEnd/Documents/projects/kitagawa-backend/mask_temp/GSHHS_f_L1.shp"
if not os.path.exists(shp_path):
    print("Shapefile not extracted. Extracting...")
    import zipfile
    with zipfile.ZipFile("/tmp/gshhg.zip", 'r') as z:
        z.extractall("/home/TheLowEnd/Documents/projects/kitagawa-backend/mask_temp")

gdf = gpd.read_file("/home/TheLowEnd/Documents/projects/kitagawa-backend/mask_temp/GSHHS_shp/c/GSHHS_c_L1.shp")
print("CRS:", gdf.crs)
print("Bounds:", gdf.total_bounds)
print(f"Sample polygons: {gdf.head(2).geometry}")
