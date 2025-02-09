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

app = Flask(__name__)
app.secret_key =  os.environ.get('SECRET_KEY', '20bca4271a595b0dc8643deb1d9085a8bbb75c36833a4cb810c77c7a93c68d01')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Global queue for progress updates
# Global variables
progress_queue = queue.Queue()
current_output_dir = None


def optimize_image(input_path, output_path, total_files, current_file, jpeg_quality=85, convert_png=False):
    """
    Optimize and compress an image file and send progress updates.
    """
    # Calculate progress percentage
    progress = (current_file / total_files) * 100
    progress_queue.put({
        'type': 'progress',
        'progress': progress
    })

    # Get original file size
    original_size = os.path.getsize(input_path)

    try:
        with Image.open(input_path) as img:
            original_format = img.format
            status = "optimized"
            
            # Handle PNG conversion
            if convert_png and original_format == "PNG":
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    logging.info(f"Skipping PNG conversion for {input_path} due to transparency.")
                else:
                    img = img.convert("RGB")
                    output_path = os.path.splitext(output_path)[0] + ".jpg"
                    original_format = "JPEG"
                    status = "converted"

            # Save optimized image
            if original_format == "JPEG":
                img.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)
            elif original_format == "PNG":
                img.save(output_path, format="PNG", optimize=True)
            else:
                img.save(output_path, format=original_format)

    except UnidentifiedImageError:
        logging.error(f"File {input_path} is not a valid image file.")
        progress_queue.put({
            'type': 'file_complete',
            'file_name': os.path.basename(input_path),
            'original_size': original_size,
            'optimized_size': 0,
            'saving_percentage': 0,
            'status': 'error'
        })
        return

    except Exception as e:
        logging.error(f"Error processing {input_path}: {e}")
        progress_queue.put({
            'type': 'file_complete',
            'file_name': os.path.basename(input_path),
            'original_size': original_size,
            'optimized_size': 0,
            'saving_percentage': 0,
            'status': 'error'
        })
        return

    # Get optimized file size and calculate savings
    optimized_size = os.path.getsize(output_path)
    saving_percentage = ((original_size - optimized_size) / original_size) * 100 if original_size > 0 else 0

    # Send file completion update
    progress_queue.put({
        'type': 'file_complete',
        'file_name': os.path.basename(input_path),
        'original_size': original_size,
        'optimized_size': optimized_size,
        'saving_percentage': saving_percentage,
        'status': status
    })

def process_images(input_dir, output_dir, jpeg_quality, convert_png):
    """
    Process all images in the input directory and send progress updates.
    """
    image_extensions = {'.jpg', '.jpeg', '.png'}
    image_files = []
    
    # Collect all image files
    for root, _, files in os.walk(input_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                image_files.append((root, file))

    total_files = len(image_files)
    
    # Process each image
    # Process each image
    for idx, (root, file) in enumerate(image_files, 1):
        input_path = os.path.join(root, file)
        rel_path = os.path.relpath(root, input_dir)
        out_dir = os.path.join(output_dir, rel_path)
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, file)
        
        optimize_image(
            input_path,
            output_path,
            total_files,
            idx,
            jpeg_quality=jpeg_quality,
            convert_png=convert_png
        )
    
    # Signal that processing is complete
    progress_queue.put({'type': 'processing_complete'})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/optimize', methods=['POST'])
def optimize():
    """
    Handle the initial file upload and start the optimization process.
    """
    if 'zip_file' not in request.files:
        flash('No file part in the request.')
        return {'status': 'error', 'message': 'No file part'}, 400
    
    file = request.files['zip_file']
    if file.filename == '':
        flash('No file selected.')
        return {'status': 'error', 'message': 'No file selected'}, 400
    
    if not file.filename.lower().endswith('.zip'):
        flash('Please upload a ZIP file containing images.')
        return {'status': 'error', 'message': 'Invalid file type'}, 400

    try:
        jpeg_quality = int(request.form.get('jpeg_quality', 85))
    except ValueError:
        jpeg_quality = 85
    
    convert_png = bool(request.form.get('convert_png'))

    # Create temporary directories and start processing in a thread
    temp_input_dir = tempfile.mkdtemp()
    temp_output_dir = tempfile.mkdtemp()
    
    global current_output_dir
    current_output_dir = temp_output_dir
    
    zip_path = os.path.join(temp_input_dir, 'upload.zip')
    file.save(zip_path)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_input_dir)
    except zipfile.BadZipFile:
        return {'status': 'error', 'message': 'Invalid ZIP file'}, 400

    # Start processing in a separate thread
    thread = threading.Thread(
        target=process_images,
        args=(temp_input_dir, temp_output_dir, jpeg_quality, convert_png)
    )
    thread.start()

    return {'status': 'success'}

@app.route('/optimize-stream')
def optimize_stream():
    def generate():
        while True:
            try:
                # Get progress update from queue
                data = progress_queue.get(timeout=1)
                
                # When processing is complete, create the ZIP file
                if data.get('type') == 'processing_complete':
                    downloads_dir = os.path.join(os.getcwd(), 'downloads')
                    os.makedirs(downloads_dir, exist_ok=True)
                    zip_filename = f"{uuid.uuid4().hex}.zip"
                    zip_file_path = os.path.join(downloads_dir, zip_filename)
                    
                    # Use the global current_output_dir that was set in /optimize
                    global current_output_dir
                    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                        for root, _, files in os.walk(current_output_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, current_output_dir)
                                zip_out.write(file_path, arcname)
                    
                    # Send complete event with zip filename and optional full progress
                    yield f"data: {json.dumps({'type': 'complete', 'zip_file': zip_filename, 'progress': 100})}\n\n"
                    break
                
                # Otherwise, send the progress update as-is
                yield f"data: {json.dumps(data)}\n\n"
                
            except queue.Empty:
                # Send a keepalive event
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
    
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
    app.run(debug=True, threaded=True)