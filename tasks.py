import os
import uuid
import zipfile
import json
import logging
from PIL import Image, UnidentifiedImageError
import redis

# It’s a good idea to set up logging in this module as well
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# If needed, you can import the Redis connection from your configuration
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_conn = redis.from_url(redis_url)

def optimize_image(input_path, output_path, job_id, jpeg_quality=85, convert_png=False):
    """Optimize single image and update progress in Redis"""
    try:
        original_size = os.path.getsize(input_path)
        
        with Image.open(input_path) as img:
            original_format = img.format
            status = "optimized"
            
            if convert_png and original_format == "PNG":
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    status = "skipped"
                else:
                    img = img.convert("RGB")
                    output_path = os.path.splitext(output_path)[0] + ".jpg"
                    original_format = "JPEG"
                    status = "converted"

            if original_format == "JPEG":
                img.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)
            elif original_format == "PNG":
                img.save(output_path, format="PNG", optimize=True)
            else:
                img.save(output_path, format=original_format)

        optimized_size = os.path.getsize(output_path)
        saving_percentage = ((original_size - optimized_size) / original_size) * 100 if original_size > 0 else 0

        return {
            "file_name": os.path.basename(input_path),
            "original_size": original_size,
            "optimized_size": optimized_size,
            "saving_percentage": saving_percentage,
            "status": status
        }
    except Exception as e:
        logging.error(f"Error processing {input_path}: {str(e)}")
        return {
            "file_name": os.path.basename(input_path),
            "original_size": original_size if 'original_size' in locals() else 0,
            "optimized_size": 0,
            "saving_percentage": 0,
            "status": "error"
        }

def process_images_task(input_dir, output_dir, job_id, jpeg_quality, convert_png):
    """Background task for processing images"""
    image_extensions = {'.jpg', '.jpeg', '.png'}
    results = []
    total_files = sum(1 for root, _, files in os.walk(input_dir) 
                      for f in files if os.path.splitext(f)[1].lower() in image_extensions)
    processed = 0

    for root, _, files in os.walk(input_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                input_path = os.path.join(root, file)
                rel_path = os.path.relpath(root, input_dir)
                out_dir = os.path.join(output_dir, rel_path)
                os.makedirs(out_dir, exist_ok=True)
                output_path = os.path.join(out_dir, file)
                
                result = optimize_image(input_path, output_path, job_id, jpeg_quality, convert_png)
                results.append(result)
                
                processed += 1
                progress = (processed / total_files) * 100
                # Update progress in Redis hash for this job (if needed)
                redis_conn.hset(f"job:{job_id}", "progress", json.dumps({
                    "type": "progress",
                    "progress": progress,
                    "current": processed,
                    "total": total_files
                }))

    # Create ZIP file from the output directory
    downloads_dir = os.path.join(os.getcwd(), 'downloads')
    os.makedirs(downloads_dir, exist_ok=True)
    zip_filename = f"{uuid.uuid4().hex}.zip"
    zip_path = os.path.join(downloads_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zip_out.write(file_path, arcname)

    return {"results": results, "zip_filename": zip_filename}
