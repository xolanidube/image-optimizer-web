#!/usr/bin/env python3
"""
app.py

A Flask web application that provides a real-time interface to optimize images
contained in an uploaded ZIP file. Uses Server-Sent Events (SSE) to provide
live progress updates during image optimization.
"""

import os
import uuid
import zipfile
import tempfile
import logging
import json
import queue
import threading
from flask import Flask, request, send_from_directory, render_template, flash, redirect
from flask import Response, stream_with_context
from PIL import Image, UnidentifiedImageError
import redis
from rq import Queue
from rq.job import Job

app = Flask(__name__)
app.secret_key =  os.environ.get('SECRET_KEY', '20bca4271a595b0dc8643deb1d9085a8bbb75c36833a4cb810c77c7a93c68d01')

# Configure Redis
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_conn = redis.from_url(redis_url)
job_queue = Queue(connection=redis_conn)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Global queue for progress updates
# Global variables
progress_queue = queue.Queue()
current_output_dir = None


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
                redis_conn.hset(f"job:{job_id}", "progress", json.dumps({
                    "type": "progress",
                    "progress": progress,
                    "current": processed,
                    "total": total_files
                }))

    # Create ZIP file
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



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/optimize', methods=['POST'])
def optimize():
    if 'zip_file' not in request.files:
        return {'status': 'error', 'message': 'No file part'}, 400
    
    file = request.files['zip_file']
    if file.filename == '':
        return {'status': 'error', 'message': 'No file selected'}, 400
    
    if not file.filename.lower().endswith('.zip'):
        return {'status': 'error', 'message': 'Invalid file type'}, 400

    try:
        jpeg_quality = int(request.form.get('jpeg_quality', 85))
    except ValueError:
        jpeg_quality = 85
    
    convert_png = bool(request.form.get('convert_png'))

    # Create temporary directories
    temp_input_dir = tempfile.mkdtemp()
    temp_output_dir = tempfile.mkdtemp()
    
    zip_path = os.path.join(temp_input_dir, 'upload.zip')
    file.save(zip_path)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_input_dir)
    except zipfile.BadZipFile:
        return {'status': 'error', 'message': 'Invalid ZIP file'}, 400

    # Create and queue the job
    job = job_queue.enqueue(
        process_images_task,
        args=(temp_input_dir, temp_output_dir, job.id, jpeg_quality, convert_png),
        job_timeout='1h'
    )

    return {'status': 'success', 'job_id': job.id}


@app.route('/optimize-stream')
def optimize_stream():
    def generate():
        job_id = request.args.get('job_id')
        if not job_id:
            return
        
        job = Job.fetch(job_id, connection=redis_conn)
        while not job.is_finished:
            progress = redis_conn.hget(f"job:{job_id}", "progress")
            if progress:
                yield f"data: {progress.decode('utf-8')}\n\n"
            
        result = job.result
        if result:
            yield f"data: {json.dumps({
                'type': 'complete',
                'zip_file': result['zip_filename'],
                'results': result['results']
            })}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

@app.route('/download/<filename>')
def download_file(filename):
    """
    Route to download the generated ZIP file.
    """
    return send_from_directory('downloads', filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)