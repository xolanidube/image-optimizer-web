# Image Optimizer Web Interface

This repository contains a simple web interface built with Flask that allows users to optimize images contained within a ZIP file. The tool extracts images (JPEG and PNG), optimizes them (with configurable JPEG quality and an option to convert PNG to JPEG when possible), and returns a downloadable ZIP file of the optimized images.

## Features

- **Image Optimization:** Compress JPEG images with adjustable quality and optimize PNG images.
- **PNG to JPEG Conversion:** Optionally convert PNG images (without transparency) to JPEG.
- **Simple Web Interface:** Easily upload a ZIP file, set optimization options, and download optimized images.
- **Free Hosting:** Deploy on free hosting platforms like Heroku.

## Installation

1. **Clone the Repository:**
    ```bash
    git clone https://github.com/xolanidube/image-optimizer-web.git
    cd image-optimizer-web
    ```

2. **Set Up a Virtual Environment and Install Dependencies:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3. **Run the Application Locally:**
    ```bash
    python app.py
    ```
   Open your browser and navigate to `http://127.0.0.1:5000/` to use the interface.

## Deployment

This app can be deployed on free hosting platforms such as Heroku.

1. **Log in to Heroku and Create a New App:**
    ```bash
    heroku login
    heroku create your-app-name
    ```

2. **Push the Code to Heroku:**
    ```bash
    git push heroku main
    ```

3. **Open the App in Your Browser:**
    ```bash
    heroku open
    ```

## Usage

1. **Upload a ZIP File:**  
   Select a ZIP file containing your images (JPEG and PNG) using the file picker.

2. **Set JPEG Quality:**  
   Adjust the JPEG quality (1-100). The default value is 85.

3. **Convert PNG Option:**  
   Check the box if you want to convert PNG images (without transparency) to JPEG.

4. **Optimize:**  
   Click the "Optimize Images" button. Once processing is complete, the browser will download a ZIP file of the optimized images.

## Edge Cases and Considerations

- **Invalid Files:**  
  If a non-ZIP file or an invalid ZIP is uploaded, the app will flash an error message.

- **Image Transparency:**  
  PNG images with transparency are not converted to JPEG (to prevent visual changes).

- **Large Uploads:**  
  For very large ZIP files, processing time may increase. Consider adding size limits in production.

## License

This project is open source and available under the [MIT License](LICENSE).

## Contributing

Feel free to open issues or submit pull requests to suggest improvements.
