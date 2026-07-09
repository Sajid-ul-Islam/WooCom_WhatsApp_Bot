import os
import io
import logging
import httpx
from PIL import Image

logger = logging.getLogger(__name__)

async def generate_collage(image_urls: list, output_path: str = "collage.jpg") -> str:
    """
    Downloads up to 4 images, resizes them, and stitches them into a 2x2 collage.
    Returns the file path of the generated collage.
    """
    if not image_urls:
        return ""
        
    # Limit to 4 images max for a 2x2 grid
    urls = image_urls[:4]
    
    images = []
    async with httpx.AsyncClient() as client:
        for url in urls:
            try:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    img = Image.open(io.BytesIO(resp.content))
                    # Convert to RGB (in case of PNG with alpha)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img)
            except Exception as e:
                logger.error(f"Failed to fetch image {url}: {e}")
                
    if not images:
        return ""
        
    # Resize all images to 300x300
    thumb_size = (300, 300)
    resized_images = []
    for img in images:
        # Crop to square first if needed to maintain aspect ratio
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) / 2
        top = (h - min_dim) / 2
        right = (w + min_dim) / 2
        bottom = (h + min_dim) / 2
        
        cropped = img.crop((left, top, right, bottom))
        resized = cropped.resize(thumb_size, Image.Resampling.LANCZOS)
        resized_images.append(resized)
        
    # Create collage canvas
    # If 1 image -> 300x300
    # If 2 images -> 600x300
    # If 3-4 images -> 600x600
    
    if len(resized_images) == 1:
        canvas_size = (300, 300)
    elif len(resized_images) == 2:
        canvas_size = (600, 300)
    else:
        canvas_size = (600, 600)
        
    collage = Image.new('RGB', canvas_size, color=(255, 255, 255))
    
    # Paste images
    positions = [(0, 0), (300, 0), (0, 300), (300, 300)]
    for i, img in enumerate(resized_images):
        collage.paste(img, positions[i])
        
    # Save the collage
    collage.save(output_path, "JPEG", quality=85)
    return output_path
