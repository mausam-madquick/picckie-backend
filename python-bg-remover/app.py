"""Imagify python image-processing service.

This service performs background removal and optional border/sticker augmentation.
It is called by the Node/Express server via `POST /remove-bg`.

Outputs:
- Single-image flow: returns a JPEG file.
- Multi-variation flow: returns JSON containing base64-encoded JPEG data-URLs.
"""

print("[*] Initializing Image Processing Service...")
print("   - Importing FastAPI...")

from fastapi import FastAPI, File, Form, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, PlainTextResponse

print("   - Importing rembg...")
from rembg import remove

print("   - Importing Pillow/Numpy...")
from PIL import Image, ImageDraw
import numpy as np

import io
import base64
import colorsys
import random
import os
import glob

print("[OK] Imports complete. Setting up API...")

app = FastAPI(title="Image Processing API")

# Allow Next.js / Node server to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sticker assets are stored in the client repository and loaded at runtime.
STICKER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "stickers")
)
STICKER_PATHS = glob.glob(os.path.join(STICKER_DIR, "*.png"))


def _overlay_random_stickers(
    base_rgba: Image.Image, *, max_stickers: int = 2
) -> Image.Image:
    """Overlay 1–2 random stickers onto an RGBA image.

    Uses PNG alpha, places stickers in corners with a safe margin.
    If no stickers are available, returns the image unchanged.
    """

    if not STICKER_PATHS:
        return base_rgba

    image = base_rgba.convert("RGBA")
    sticker_count = 1 if max_stickers <= 1 else random.choice([1, 2])

    for _ in range(sticker_count):
        sticker_path = random.choice(STICKER_PATHS)
        try:
            sticker = Image.open(sticker_path).convert("RGBA")
        except Exception:
            continue

        # Keep sticker reasonably sized relative to the base image.
        scale = random.uniform(0.15, 0.28)
        target_w = max(40, int(image.width * scale))
        ratio = sticker.height / max(1, sticker.width)
        target_h = max(40, int(target_w * ratio))
        target_w = min(target_w, image.width)
        target_h = min(target_h, image.height)

        try:
            sticker = sticker.resize((target_w, target_h), Image.Resampling.LANCZOS)
        except Exception:
            continue

        margin = 20
        x_min = margin
        y_min = margin
        x_max = max(margin, image.width - target_w - margin)
        y_max = max(margin, image.height - target_h - margin)

        positions = [
            (x_min, y_min),
            (x_max, y_min),
            (x_min, y_max),
            (x_max, y_max),
        ]
        x, y = random.choice(positions)

        image.paste(sticker, (x, y), sticker)

    return image


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "image-processor"}


@app.post("/remove-bg")
@app.post("/remove-background")
async def remove_bg(
    request: Request,
    file: UploadFile | None = File(None),
    remove_bg: str | None = Form(None),
    add_border: str | None = Form(None),
    multi_border: str | None = Form(None),
    num_variations: str | None = Form(None),
    stickers: str | None = Form(None),
    sticker_probability: str | None = Form(None),
):
    """Process an uploaded image and return either a JPEG or JSON variations.

    Request:
    - multipart/form-data with a `file` field (preferred), or raw bytes.
    - form fields:
      - remove_bg: "true"/"false"
      - add_border: "true"/"false"
      - multi_border: "true"/"false" (when true, returns JSON variations)
      - num_variations: int (only for multi_border)
      - stickers: "true"/"false"
      - sticker_probability: float in [0, 1]
    """
    try:
        if file is not None:
            input_bytes = await file.read()
            if not input_bytes:
                return PlainTextResponse("Missing file", status_code=400)
            input_image = Image.open(io.BytesIO(input_bytes))
        else:
            body = await request.body()
            if not body:
                return PlainTextResponse("Missing file", status_code=400)
            input_image = Image.open(io.BytesIO(body))

        remove_bg_flag = True
        add_border_flag = True
        multi_border_flag = multi_border == "true" or (num_variations is not None and num_variations != "1")
        stickers_enabled = True
        parsed_probability = 0.9

        if stickers_enabled and not STICKER_PATHS:
            print(
                f"Stickers enabled but none found. STICKER_DIR={STICKER_DIR}",
                flush=True,
            )

        try:
            parsed_variations = int(num_variations) if num_variations is not None else 4
        except (TypeError, ValueError):
            parsed_variations = 4

        if remove_bg_flag:
            output_image = remove(input_image)
        else:
            output_image = input_image

        if multi_border_flag:
            output_image = output_image.convert("RGBA")

            # Compute dominant color once for the first 40% of images
            arr = np.array(output_image)
            pixels = arr.reshape(-1, 4)
            valid_pixels = pixels[pixels[:, 3] > 200]

            dominant_color = (255, 255, 255)
            if len(valid_pixels) > 0:
                rgb_pixels = valid_pixels[:, :3]
                binned_pixels = (rgb_pixels // 32) * 32 + 16
                unique_colors, counts = np.unique(
                    binned_pixels, axis=0, return_counts=True
                )
                most_frequent_idx = np.argmax(counts)
                dominant_color = tuple(int(c) for c in unique_colors[most_frequent_idx])

            # Generate variations with different border hues
            colors: list[tuple[int, int, int]] = []
            for i in range(parsed_variations):
                hue = i / parsed_variations if parsed_variations > 0 else 0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
                colors.append((int(r * 255), int(g * 255), int(b * 255)))

            total_images = len(colors)
            dominant_limit = int(total_images * 0.4)
            small_count = int(total_images * 0.3)
            small_indices = set(random.sample(range(total_images), small_count))

            # Find the optimal quality using the first image so we don't recalculate for every image
            first_bg_rgba = output_image.copy()
            if 0 in small_indices:
                scale = random.uniform(0.7, 0.9)
                new_w = int(first_bg_rgba.width * scale)
                new_h = int(first_bg_rgba.height * scale)
                resized_img = first_bg_rgba.resize(
                    (new_w, new_h), Image.Resampling.LANCZOS
                )
                new_canvas = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
                x = (1000 - new_w) // 2
                y = (1000 - new_h) // 2
                new_canvas.paste(resized_img, (x, y))
                first_bg_rgba = new_canvas

            first_thickness = random.randint(0, 20)
            if first_thickness > 0:
                draw = ImageDraw.Draw(first_bg_rgba)
                # First image (index 0) will always use the dominant color
                draw.rectangle(
                    [0, 0, first_bg_rgba.width - 1, first_bg_rgba.height - 1],
                    outline=dominant_color,
                    width=first_thickness,
                )

            bg = Image.new("RGB", first_bg_rgba.size, (255, 255, 255))
            bg.paste(first_bg_rgba, mask=first_bg_rgba)
            first_final = bg

            quality = 90
            img_io = io.BytesIO()
            while True:
                img_io.seek(0)
                img_io.truncate(0)
                first_final.save(img_io, format="JPEG", quality=quality)
                size = img_io.tell()
                if size <= 50 * 1024 or quality <= 5:
                    break
                quality -= 5

            # Now generate all images
            encoded_images: list[str] = []

            sticker_indices: set[int] = set()
            if stickers_enabled and STICKER_PATHS and total_images > 0:
                if parsed_probability > 0.0:
                    target = int(round(total_images * parsed_probability))
                    target = max(1, min(total_images, target))
                    sticker_indices = set(random.sample(range(total_images), target))

            for i, color in enumerate(colors):
                bg_rgba = output_image.copy()

                if i in small_indices:
                    scale = random.uniform(0.7, 0.9)
                    new_w = int(bg_rgba.width * scale)
                    new_h = int(bg_rgba.height * scale)
                    resized_img = bg_rgba.resize(
                        (new_w, new_h), Image.Resampling.LANCZOS
                    )
                    new_canvas = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
                    x = (1000 - new_w) // 2
                    y = (1000 - new_h) // 2
                    new_canvas.paste(resized_img, (x, y))
                    bg_rgba = new_canvas

                thickness = random.randint(0, 20)
                if thickness > 0:
                    draw = ImageDraw.Draw(bg_rgba)
                    border_color = dominant_color if i < dominant_limit else color
                    draw.rectangle(
                        [0, 0, bg_rgba.width - 1, bg_rgba.height - 1],
                        outline=border_color,
                        width=thickness,
                    )

                # Add stickers on a fixed fraction of the generated images.
                if i in sticker_indices:
                    bg_rgba = _overlay_random_stickers(bg_rgba, max_stickers=2)

                bg = Image.new("RGB", bg_rgba.size, (255, 255, 255))
                bg.paste(bg_rgba, mask=bg_rgba)

                buf = io.BytesIO()
                bg.save(buf, format="JPEG", quality=quality)
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                encoded_images.append(f"data:image/jpeg;base64,{b64}")

            return JSONResponse({"images": encoded_images})

        # Single image flow
        output_image = output_image.convert("RGBA")

        # 1. Random resizing (chhoti/badi product size)
        scale = random.uniform(0.7, 0.9)
        new_w = int(output_image.width * scale)
        new_h = int(output_image.height * scale)
        resized_img = output_image.resize(
            (new_w, new_h), Image.Resampling.LANCZOS
        )
        new_canvas = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
        x = (1000 - new_w) // 2
        y = (1000 - new_h) // 2
        new_canvas.paste(resized_img, (x, y))
        output_image = new_canvas

        # 2. Extract dominant color and draw border
        if add_border_flag:
            arr = np.array(output_image)
            pixels = arr.reshape(-1, 4)
            valid_pixels = pixels[pixels[:, 3] > 200]

            dominant_color = (255, 255, 255)
            if len(valid_pixels) > 0:
                rgb_pixels = valid_pixels[:, :3]
                binned_pixels = (rgb_pixels // 32) * 32 + 16
                unique_colors, counts = np.unique(
                    binned_pixels, axis=0, return_counts=True
                )
                most_frequent_idx = np.argmax(counts)
                dominant_color = tuple(
                    int(c) for c in unique_colors[most_frequent_idx]
                )

            thickness = random.randint(8, 20)  # Always visible border
            draw = ImageDraw.Draw(output_image)
            draw.rectangle(
                [0, 0, output_image.width - 1, output_image.height - 1],
                outline=dominant_color,
                width=thickness,
            )

        # 3. Apply stickers
        if stickers_enabled and STICKER_PATHS:
            if random.random() < parsed_probability:
                output_image = _overlay_random_stickers(
                    output_image, max_stickers=2
                )

        # Convert to RGB on a solid white background because JPEG does not support transparency
        output_image = output_image.convert("RGBA")
        background = Image.new("RGB", output_image.size, (255, 255, 255))
        background.paste(output_image, mask=output_image)
        output_image = background

        quality = 90
        img_io = io.BytesIO()
        while True:
            img_io.seek(0)
            img_io.truncate(0)
            output_image.save(img_io, format="JPEG", quality=quality)
            size = img_io.tell()

            if size <= 50 * 1024 or quality <= 5:
                break

            quality -= 5

        return Response(content=img_io.getvalue(), media_type="image/jpeg")

    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        print("Error in remove-bg:", e, flush=True)
        print(tb, flush=True)
        return PlainTextResponse(
            "Internal server error\n" + str(e) + "\n" + tb, status_code=500
        )


if __name__ == "__main__":
    import uvicorn

    print("Starting Uvicorn server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
