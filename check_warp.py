from rasterio import warp
xs, ys = warp.transform("EPSG:4326", "EPSG:4326", [-82.0], [38.0])
print("Rasterio transform returned xs:", xs, "ys:", ys)
