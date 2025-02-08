#!/usr/bin/env python3
"""
app.py

A Flask web application that provides an interface to optimize images
contained in an uploaded ZIP file. Users can adjust JPEG quality and choose
to convert PNG images (without transparency) to JPEG. The optimized images are
packaged into a ZIP file, and detailed information about each file (before and
after sizes, percentage savings, and conversion status) is displayed on a results page.

Usage:
    python app.py

Deployment:
    This app can be deployed on platforms like Heroku using the provided Procfile.
"""

import os
import uuid
import zipfile
import tempfile
import logging
from flask import Flask, request, send_from_directory, render_template, flash, redirect, url_for
from PIL import Image, UnidentifiedImageError

app = Flask(__name__)
app.secret_key = '20bca4271a595b0dc8643deb1d9085a8bbb75c36833a4cb810c77c7a93c68d01'  # Replace with a secure random key in production

# Configure logging.
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def optimize_image(input_path, output_path, jpeg_quality=85, convert_png=False, log_messages=None, file_info=None):
    """
    Optimize and compress an image file and record its info.

    Parameters:
        input_path (str): Path to the source image.
        output_path (str): Path where the optimized image will be saved.
        jpeg_quality (int): JPEG compression quality (1-100).
        convert_png (bool): Whether to convert PNG (if no transparency) to JPEG.
        log_messages (list): List to collect log messages.
        file_info (list): List to collect file optimization info.
    
    Returns:
        Tuple (log_messages, file_info)
    """
    if log_messages is None:
        log_messages = []
    if file_info is None:
        file_info = []

    # Get original file size.
    original_size = os.path.getsize(input_path)

    try:
        with Image.open(input_path) as img:
            original_format = img.format
            log_messages.append(f"Processing {input_path} (format: {original_format})")
            status = "optimized"
            # Optionally convert PNG to JPEG if eligible.
            if convert_png and original_format == "PNG":
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    log_messages.append(f"Skipping PNG conversion for {input_path} due to transparency.")
                else:
                    img = img.convert("RGB")
                    output_path = os.path.splitext(output_path)[0] + ".jpg"
                    original_format = "JPEG"
                    status = "converted"
                    log_messages.append(f"Converting PNG to JPEG for {input_path}.")
            # Save based on format.
            if original_format == "JPEG":
                img.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)
                log_messages.append(f"Saved optimized JPEG: {output_path}")
            elif original_format == "PNG":
                img.save(output_path, format="PNG", optimize=True)
                log_messages.append(f"Saved optimized PNG: {output_path}")
            else:
                img.save(output_path, format=original_format)
                log_messages.append(f"Saved image in original format: {output_path}")
    except UnidentifiedImageError:
        error_msg = f"File {input_path} is not a valid image file."
        logging.error(error_msg)
        log_messages.append(error_msg)
        return log_messages, file_info
    except Exception as e:
        error_msg = f"Error processing {input_path}: {e}"
        logging.error(error_msg)
        log_messages.append(error_msg)
        return log_messages, file_info

    # Get optimized file size.
    optimized_size = os.path.getsize(output_path)
    saving_percentage = 0.0
    if original_size > 0:
        saving_percentage = ((original_size - optimized_size) / original_size) * 100

    file_info.append({
        "file_name": os.path.basename(input_path),
        "original_size": original_size,
        "optimized_size": optimized_size,
        "saving_percentage": saving_percentage,
        "status": status
    })

    return log_messages, file_info

def crawl_and_optimize(directory, output_directory, jpeg_quality=85, convert_png=False, log_messages=None, file_info=None):
    """
    Recursively crawl a directory for images, optimize them, and record their info.

    Parameters:
        directory (str): Root directory to search for images.
        output_directory (str): Destination directory for optimized images.
        jpeg_quality (int): JPEG quality setting.
        convert_png (bool): Whether to convert eligible PNG images to JPEG.
        log_messages (list): List to collect log messages.
        file_info (list): List to collect file info dictionaries.
    
    Returns:
        Tuple (log_messages, file_info)
    """
    if log_messages is None:
        log_messages = []
    if file_info is None:
        file_info = []

    image_extensions = {'.jpg', '.jpeg', '.png'}

    for root, _, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in image_extensions:
                input_path = os.path.join(root, file)
                # Maintain relative folder structure.
                rel_path = os.path.relpath(root, directory)
                out_dir = os.path.join(output_directory, rel_path)
                os.makedirs(out_dir, exist_ok=True)
                output_path = os.path.join(out_dir, file)
                log_messages, file_info = optimize_image(
                    input_path, output_path,
                    jpeg_quality=jpeg_quality,
                    convert_png=convert_png,
                    log_messages=log_messages,
                    file_info=file_info
                )
    return log_messages, file_info

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'zip_file' not in request.files:
            flash('No file part in the request.')
            return redirect(request.url)
        file = request.files['zip_file']
        if file.filename == '':
            flash('No file selected.')
            return redirect(request.url)
        if not file.filename.lower().endswith('.zip'):
            flash('Please upload a ZIP file containing images.')
            return redirect(request.url)

        try:
            jpeg_quality = int(request.form.get('jpeg_quality', 85))
        except ValueError:
            jpeg_quality = 85
        convert_png = bool(request.form.get('convert_png'))
        log_messages = []
        file_info = []

        # Create temporary directories for extraction and output.
        with tempfile.TemporaryDirectory() as temp_input_dir, tempfile.TemporaryDirectory() as temp_output_dir:
            zip_path = os.path.join(temp_input_dir, 'upload.zip')
            file.save(zip_path)
            log_messages.append(f"Uploaded file saved to {zip_path}")
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_input_dir)
                log_messages.append("ZIP file extracted successfully.")
            except zipfile.BadZipFile:
                flash('Uploaded file is not a valid ZIP file.')
                return redirect(request.url)
            
            # Optimize images and record file details.
            log_messages, file_info = crawl_and_optimize(
                temp_input_dir, temp_output_dir,
                jpeg_quality=jpeg_quality,
                convert_png=convert_png,
                log_messages=log_messages,
                file_info=file_info
            )
            
            # Save the optimized images ZIP to a persistent downloads folder.
            downloads_dir = os.path.join(os.getcwd(), 'downloads')
            os.makedirs(downloads_dir, exist_ok=True)
            zip_filename = f"{uuid.uuid4().hex}.zip"
            zip_file_path = os.path.join(downloads_dir, zip_filename)
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
                for root, _, files in os.walk(temp_output_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_output_dir)
                        zip_out.write(file_path, arcname)
            log_messages.append(f"Optimized images zipped to {zip_file_path}")
            
            # Render a results page with a table of file info.
            return render_template("results.html", file_info=file_info, zip_file=zip_filename)
    return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    """
    Route to download the generated ZIP file from the downloads folder.
    """
    return send_from_directory('downloads', filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
