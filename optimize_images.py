#!/usr/bin/env python3
"""
optimize_images.py - CLI tool for image optimization
"""

import argparse
import os
import zipfile
import tempfile
from PIL import Image
import sys
from tqdm import tqdm

def optimize_image(input_path, output_path, jpeg_quality=85, convert_png=False):
    """Optimize a single image"""
    try:
        with Image.open(input_path) as img:
            original_format = img.format
            
            if convert_png and original_format == "PNG":
                if not (img.mode in ("RGBA", "LA") or 
                      (img.mode == "P" and "transparency" in img.info)):
                    img = img.convert("RGB")
                    output_path = os.path.splitext(output_path)[0] + ".jpg"
                    original_format = "JPEG"

            if original_format == "JPEG":
                img.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)
            elif original_format == "PNG":
                img.save(output_path, format="PNG", optimize=True)
            else:
                img.save(output_path, format=original_format)
                
        return True
    except Exception as e:
        print(f"Error processing {input_path}: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Optimize images in a ZIP file')
    parser.add_argument('input_zip', help='Input ZIP file containing images')
    parser.add_argument('output_zip', help='Output ZIP file for optimized images')
    parser.add_argument('--quality', type=int, default=85, help='JPEG quality (1-100)')
    parser.add_argument('--convert-png', action='store_true', 
                       help='Convert PNG to JPEG if no transparency')
    
    args = parser.parse_args()
    
    with tempfile.TemporaryDirectory() as temp_input_dir, \
         tempfile.TemporaryDirectory() as temp_output_dir:
        
        # Extract input ZIP
        print("Extracting input ZIP file...")
        with zipfile.ZipFile(args.input_zip, 'r') as zip_ref:
            zip_ref.extractall(temp_input_dir)
        
        # Process images
        image_extensions = {'.jpg', '.jpeg', '.png'}
        image_files = []
        
        for root, _, files in os.walk(temp_input_dir):
            for file in files:
                if os.path.splitext(file)[1].lower() in image_extensions:
                    image_files.append((root, file))
        
        print(f"Found {len(image_files)} images to process")
        
        success_count = 0
        with tqdm(total=len(image_files), desc="Processing images") as pbar:
            for root, file in image_files:
                input_path = os.path.join(root, file)
                rel_path = os.path.relpath(root, temp_input_dir)
                out_dir = os.path.join(temp_output_dir, rel_path)
                os.makedirs(out_dir, exist_ok=True)
                output_path = os.path.join(out_dir, file)
                
                if optimize_image(input_path, output_path, args.quality, args.convert_png):
                    success_count += 1
                pbar.update(1)
        
        # Create output ZIP
        print("Creating output ZIP file...")
        with zipfile.ZipFile(args.output_zip, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for root, _, files in os.walk(temp_output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_output_dir)
                    zip_out.write(file_path, arcname)
        
        print(f"\nProcessing complete:")
        print(f"- Successfully processed: {success_count}/{len(image_files)} images")
        print(f"- Output saved to: {args.output_zip}")

if __name__ == '__main__':
    main()