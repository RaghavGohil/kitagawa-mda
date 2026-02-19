sudo docker save -o ./kitagawa-inference.tar kitagawa-inference
zip kitagawa-inference.zip kitagawa-inference.tar
sha256sum kitagawa-inference.zip