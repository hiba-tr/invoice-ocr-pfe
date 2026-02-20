from PIL import Image

def crop_image(image: Image, bbox):
    return image.crop((bbox.x1, bbox.y1, bbox.x2, bbox.y2))