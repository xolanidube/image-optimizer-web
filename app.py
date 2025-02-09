#!/usr/bin/env python3
"""
app.py

A Flask web application that provides a real-time interface for optimizing images
contained in an uploaded ZIP file. It uses Server-Sent Events (SSE) for live progress updates.
This version uses Wand (ImageMagick) for image processing instead of Pillow.

Key modifications:
- Two download buttons are provided (above and below the summary table).
- Supports additional image types: JPEG, PNG, GIF, BMP, TIFF, WEBP.
- Cleans the /tmp/downloads/ folder by removing the ZIP file once it is downloaded.
- Tracks the lifetime number of optimizations performed via a global counter.
- Contains documentation for potential new features (see end of file).

Usage:
    python3 app.py
"""

import os
import uuid
import zipfile
import tempfile
import logging
import json
import queue
import threading
from flask import Flask, request, send_from_directory, render_template, flash, redirect, Response, stream_with_context
from wand.image import Image as WandImage
from wand.exceptions import WandException

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get(
    'SECRET_KEY', '20bca4271a595b0dc8643deb1d9085a8bbb75c36833a4cb810c77c7a93c68d01'
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Global queue for progress updates
progress_queue = queue.Queue()

# Global variable for tracking output directory and optimization count
current_output_dir = None
optimization_count = 0  # Lifetime optimization counter

def optimize_image(input_path, output_path, total_files, current_file, jpeg_quality=85, convert_png=False):
    """
    Optimize and compress an image file using Wand.
    Sends progress updates to the global queue.
    
    Parameters:
      - input_path: Path of the input image.
      - output_path: Path where the optimized image will be saved.
      - total_files: Total number of images being processed.
      - current_file: The current image index (for progress calculation).
      - jpeg_quality: Quality setting for JPEG images.
      - convert_png: Flag to convert PNG to JPEG if no transparency.
    """
    # Calculate and send progress update
    progress = (current_file / total_files) * 100
    progress_queue.put({'type': 'progress', 'progress': progress})

    # Get original file size
    original_size = os.path.getsize(input_path)
    status = "optimized"

    try:
        with WandImage(filename=input_path) as img:
            original_format = img.format.upper()

            # Handle PNG conversion if allowed
            if convert_png and original_format == "PNG":
                # Check for transparency; Wand uses alpha_channel property
                if img.alpha_channel:
                    logging.info(f"Skipping PNG conversion for {input_path} due to transparency.")
                else:
                    img.format = "JPEG"
                    output_path = os.path.splitext(output_path)[0] + ".jpg"
                    original_format = "JPEG"
                    status = "converted"

            # Set quality for JPEG
            if original_format == "JPEG":
                img.compression_quality = jpeg_quality

            # Save optimized image; note that Wand does not expose an explicit optimize flag
            img.save(filename=output_path)

    except WandException as e:
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

    # Calculate optimized file size and savings
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
    Process all image files in the input directory and optimize them.
    
    Supports file extensions: .jpg, .jpeg, .png, .gif, .bmp, .tiff, .webp.
    """
    # Set of supported image file extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
    image_files = []

    # Collect all image files from the input directory
    for root, _, files in os.walk(input_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() in image_extensions:
                image_files.append((root, file))

    total_files = len(image_files)
    for idx, (root, file) in enumerate(image_files, 1):
        input_path = os.path.join(root, file)
        rel_path = os.path.relpath(root, input_dir)
        out_dir = os.path.join(output_dir, rel_path)
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, file)

        optimize_image(input_path, output_path, total_files, idx,
                       jpeg_quality=jpeg_quality, convert_png=convert_png)

    # Signal that processing is complete
    progress_queue.put({'type': 'processing_complete'})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/optimize', methods=['POST'])
def optimize():
    """
    Handle file upload and start the optimization process in a separate thread.
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

    # Create temporary directories for input and output
    temp_input_dir = "/tmp/input"
    temp_output_dir = "/tmp/output"
    os.makedirs(temp_input_dir, exist_ok=True)
    os.makedirs(temp_output_dir, exist_ok=True)

    global current_output_dir
    current_output_dir = temp_output_dir

    zip_path = os.path.join(temp_input_dir, 'upload.zip')
    file.save(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_input_dir)
    except zipfile.BadZipFile:
        return {'status': 'error', 'message': 'Invalid ZIP file'}, 400

    # Start image processing in a separate thread
    thread = threading.Thread(
        target=process_images,
        args=(temp_input_dir, temp_output_dir, jpeg_quality, convert_png)
    )
    thread.start()

    return {'status': 'success'}

@app.route('/optimize-stream')
def optimize_stream():
    """
    Provides a Server-Sent Events (SSE) stream to send live progress updates.
    When processing is complete, the optimized images are zipped and the global
    optimization counter is incremented.
    """
    def generate():
        global optimization_count, current_output_dir
        while True:
            try:
                data = progress_queue.get(timeout=10)
                if data.get('type') == 'processing_complete':
                    # Increment lifetime optimization count
                    optimization_count += 1

                    downloads_dir = "/tmp/downloads"
                    os.makedirs(downloads_dir, exist_ok=True)
                    zip_filename = f"{uuid.uuid4().hex}.zip"
                    zip_file_path = os.path.join(downloads_dir, zip_filename)

                    # Create a ZIP of the optimized images
                    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                        for root, _, files in os.walk(current_output_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, current_output_dir)
                                zip_out.write(file_path, arcname)

                    yield f"data: {json.dumps({'type': 'complete', 'zip_file': zip_filename, 'progress': 100})}\n\n"
                    break
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/download/<filename>')
def download_file(filename):
    """
    Serves the ZIP file for download and cleans it up from the temporary folder
    after the download is complete.
    """
    downloads_dir = "/tmp/downloads"
    response = send_from_directory(downloads_dir, filename, as_attachment=True)
    
    # Schedule deletion of the file once the response is closed
    @response.call_on_close
    def remove_file():
        try:
            os.remove(os.path.join(downloads_dir, filename))
            logging.info(f"Cleaned up downloaded file: {filename}")
        except Exception as e:
            logging.error(f"Failed to remove downloaded file {filename}: {e}")

    return response

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
