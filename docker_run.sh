sudo docker run --gpus all -it \
  -v $(pwd)/mnt:/app/mnt \
  -p 4200:4200 \
  kitagawa-inference:latest bash