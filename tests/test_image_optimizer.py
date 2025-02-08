#!/usr/bin/env python3
"""
test_image_optimizer.py

Unit tests for the image_optimizer functions in app.py.
Run these tests with:
    python -m unittest tests/test_image_optimizer.py
"""

import os
import tempfile
import unittest
from PIL import Image
from app import optimize_image, crawl_and_optimize

class TestImageOptimizer(unittest.TestCase):
    def setUp(self):
        # Create temporary directories for input and output.
        self.input_dir = tempfile.TemporaryDirectory()
        self.output_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.input_dir.cleanup()
        self.output_dir.cleanup()

    def create_test_image(self, path, mode="RGB", size=(100, 100), color=(255, 0, 0), fmt="JPEG"):
        """Helper to create a simple image file."""
        img = Image.new(mode, size, color)
        img.save(path, format=fmt)

    def test_optimize_jpeg(self):
        input_path = os.path.join(self.input_dir.name, "test.jpg")
        self.create_test_image(input_path, fmt="JPEG")
        output_path = os.path.join(self.output_dir.name, "test.jpg")
        optimize_image(input_path, output_path, jpeg_quality=50)
        self.assertTrue(os.path.exists(output_path), "Optimized JPEG should exist.")

    def test_optimize_png(self):
        input_path = os.path.join(self.input_dir.name, "test.png")
        self.create_test_image(input_path, fmt="PNG")
        output_path = os.path.join(self.output_dir.name, "test.png")
        optimize_image(input_path, output_path)
        self.assertTrue(os.path.exists(output_path), "Optimized PNG should exist.")

    def test_convert_png_to_jpeg_without_transparency(self):
        input_path = os.path.join(self.input_dir.name, "test.png")
        self.create_test_image(input_path, mode="RGB", fmt="PNG")
        output_path = os.path.join(self.output_dir.name, "test.png")
        optimize_image(input_path, output_path, convert_png=True, jpeg_quality=70)
        expected_output = os.path.splitext(output_path)[0] + ".jpg"
        self.assertTrue(os.path.exists(expected_output), "Converted JPEG file should exist.")

    def test_skip_convert_png_with_transparency(self):
        input_path = os.path.join(self.input_dir.name, "test.png")
        self.create_test_image(input_path, mode="RGBA", fmt="PNG")
        output_path = os.path.join(self.output_dir.name, "test.png")
        optimize_image(input_path, output_path, convert_png=True, jpeg_quality=70)
        self.assertTrue(os.path.exists(output_path), "Optimized PNG should exist.")
        expected_jpeg = os.path.splitext(output_path)[0] + ".jpg"
        self.assertFalse(os.path.exists(expected_jpeg), "PNG with transparency should not be converted to JPEG.")

    def test_non_image_file(self):
        input_path = os.path.join(self.input_dir.name, "not_an_image.txt")
        with open(input_path, "w") as f:
            f.write("This is not an image.")
        output_path = os.path.join(self.output_dir.name, "not_an_image.txt")
        optimize_image(input_path, output_path)
        self.assertFalse(os.path.exists(output_path), "Non-image files should not produce output.")

if __name__ == '__main__':
    unittest.main()
