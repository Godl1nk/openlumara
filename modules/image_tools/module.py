import os
import io
import time
import base64
import hashlib
import asyncio
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageEnhance
import httpx
import ulid

import core
import channels.webui.api as webui

class ImageTools(core.module.Module):
    """
    AI Image Generation and Local Image Manipulation.
    Generate images via OpenAI DALL-E, local Stable Diffusion, or offline mock generator,
    and edit images locally (resize, crop, rotate, flip, filters, format conversions).
    """

    category = "utilities"

    settings = {
        "enabled": {
            "type": "boolean",
            "default": True,
            "description": "Enable or disable image generation and editing."
        },
        "ask_before_generate": {
            "type": "boolean",
            "default": False,
            "description": "Pause image requests and pick the model in chat each time."
        },
        "endpoint": {
            "type": "string",
            "default": "auto",
            "description": "Configured provider endpoint for image generation (or 'auto')."
        },
        "model": {
            "type": "string",
            "default": "Qwen-Image-2.1",
            "description": "Model to use for image generation."
        },
        "quality": {
            "type": "select",
            "default": "high",
            "options": {
                "high": "High (best quality)",
                "standard": "Standard",
                "hd": "HD (Ultra)"
            },
            "description": "Generation quality level."
        },
        "edit_endpoint": {
            "type": "string",
            "default": "auto",
            "description": "Endpoint for image editing (auto uses generation endpoint)."
        },
        "edit_model": {
            "type": "string",
            "default": "same",
            "description": "Model for image editing (same uses generation model)."
        },
        "backend": {
            "type": "select",
            "default": "mock",
            "description": "Image generation engine: 'mock' (offline gradient placeholder), 'openai' (DALL-E 3 / OpenAI API-compatible), 'sd_webui' (Local Stable Diffusion WebUI / Forge txt2img).",
            "options": {
                "mock": "Mock / Offline Generator (Generates stylized PNGs without external APIs)",
                "openai": "OpenAI DALL-E (DALL-E 3 / DALL-E 2 / OpenAI API-compatible)",
                "sd_webui": "Local Stable Diffusion WebUI / Forge (txt2img API)"
            }
        },
        "openai_api_key": {
            "type": "string",
            "default": "",
            "description": "API key for image generation. If empty, falls back to the OpenLumara core api.key.",
            "depends": "backend"
        },
        "openai_api_url": {
            "type": "string",
            "default": "https://api.openai.com/v1",
            "description": "Base URL for OpenAI-compatible image generations.",
            "depends": "backend"
        },
        "openai_model": {
            "type": "string",
            "default": "dall-e-3",
            "description": "Model identifier for OpenAI image generation (e.g. dall-e-3, dall-e-2).",
            "depends": "backend"
        },
        "sd_webui_url": {
            "type": "string",
            "default": "http://127.0.0.1:7860",
            "description": "Base URL of local Stable Diffusion WebUI / Forge instance.",
            "depends": "backend"
        },
        "output_directory": {
            "type": "string",
            "default": "data/images",
            "description": "Folder relative to project root where generated and edited images are stored."
        }
    }

    dependencies = ["pillow", "httpx"]

    async def on_ready(self):
        """Ensure the output directory exists."""
        out_dir = self._get_output_dir()
        os.makedirs(out_dir, exist_ok=True)

    def _get_output_dir(self) -> str:
        configured = self.config.get("output_directory") or "data/images"
        if os.path.isabs(configured):
            return configured
        return core.get_path(configured, sandbox=False)
    def _get_image_model(self) -> str:
        """Resolve active image model from module config, global core config, or fallback."""
        return self.config.get("model") or core.config.get("model", "image_model") or self.config.get("openai_model") or "Qwen-Image-2.1"


    def _safe_image_path(self, path_str: str) -> str:
        """Resolve and validate an image path."""
        p = Path(path_str)
        if not p.is_absolute():
            # Check relative to output directory first, then project root
            out_p = Path(self._get_output_dir()) / p
            if out_p.exists():
                return str(out_p.resolve())
            root_p = Path(core.get_path()) / p
            if root_p.exists():
                return str(root_p.resolve())
            return str(out_p.resolve())
        return str(p.resolve())

    # =========================================================================
    # AI Tools - Image Generation
    # =========================================================================

    async def generate(self, prompt: str, size: str = "1024x1024", style: str = "vivid", negative_prompt: str = "", filename: str = ""):
        """
        Generates an image from a text prompt using the configured backend (OpenAI DALL-E, Local SD WebUI, or Mock).

        Args:
            prompt: Detailed text description of the image to generate.
            size: Dimensions ("1024x1024", "512x512") or aspect ratio preset ("1:1", "16:9", "9:16", "4:3", "landscape", "portrait").
            style: Visual style (for DALL-E 3: "vivid" or "natural").
            negative_prompt: Optional negative prompt (used when backend is Stable Diffusion / Forge).
            filename: Optional custom base filename (without path).
        """
        if self.config.get("enabled") is False:
            return self.result("Image generation is currently disabled in settings.", success=False)

        effective_model = self._get_image_model()
        configured_endpoint = self.config.get("endpoint") or "auto"

        if self.config.get("ask_before_generate"):
            ask_mod = self.manager.modules.get("ask_user")
            if ask_mod and hasattr(ask_mod, "ask"):
                q_text = f"🎨 Image generation requested:\n- Prompt: '{prompt}'\n- Model: {effective_model}\n- Endpoint: {configured_endpoint}\n\nProceed with generation?"
                ack = await ask_mod.ask(q_text, options=["Proceed", "Cancel"], timeout=60, default_choice="Proceed")
                if ack.get("status") == "success":
                    ans = str(ack.get("content", {}).get("answer", "")).lower()
                    if ans in ("cancel", "no", "stop", "abort"):
                        return self.result("Image generation cancelled by user.", success=False)

        if not prompt or not str(prompt).strip():
            return self.result("Prompt cannot be empty.", success=False)
        backend = self.config.get("backend") or "mock"
        out_dir = self._get_output_dir()
        os.makedirs(out_dir, exist_ok=True)

        # Parse dimensions or aspect ratio preset
        size_str = str(size).lower().strip()
        aspect_presets = {
            "1:1": "1024x1024", "square": "1024x1024",
            "16:9": "1344x768", "landscape": "1344x768",
            "9:16": "768x1344", "portrait": "768x1344",
            "4:3": "1152x864", "3:4": "864x1152",
            "21:9": "1536x640"
        }
        if size_str in aspect_presets:
            size_str = aspect_presets[size_str]

        try:
            parts = size_str.split("x")
            width, height = int(parts[0]), int(parts[1])
        except Exception:
            width, height = 1024, 1024
            size_str = "1024x1024"
        clean_base = filename.strip() if filename else f"gen_{str(ulid.ULID()).lower()}"
        clean_base = Path(clean_base).stem
        target_path = os.path.join(out_dir, f"{clean_base}.png")

        effective_model = self._get_image_model()
        try:
            if backend == "openai":
                await self._generate_openai(prompt, size_str, style, target_path, model=effective_model)
            elif backend == "sd_webui":
                await self._generate_sd(prompt, width, height, target_path, negative_prompt=negative_prompt)
            else:
                self._generate_mock(prompt, (width, height), target_path)

            rel_path = os.path.relpath(target_path, core.get_path()).replace(os.sep, "/")
            inline_url = f"/api/ext/image_tools/view?file={os.path.basename(target_path)}"
            result_data = {
                "status": "generated",
                "path": target_path,
                "relative_path": rel_path,
                "filename": os.path.basename(target_path),
                "size": f"{width}x{height}",
                "backend": backend,
                "model": effective_model,
                "prompt": prompt,
                "url": inline_url,
                "markdown": f"![{prompt}]({inline_url})"
            }

            if self.channel:
                try:
                    await self.channel.push(
                        f"🎨 **Generated Image**: `{result_data['filename']}`\n\n"
                        f"![{prompt}]({inline_url})\n\n*Prompt: {prompt}*",
                        defer=False
                    )
                except Exception:
                    pass

            return self.result(result_data, success=True)
        except Exception as e:
            return self.result(f"Failed to generate image via {backend}: {core.detail_error(e)}", success=False)

    def _generate_mock(self, prompt: str, size: tuple, target_path: str):
        """Generates an attractive offline placeholder image without external API calls."""
        w, h = size
        w, h = max(64, min(w, 2048)), max(64, min(h, 2048))
        h_val = int(hashlib.md5(prompt.encode()).hexdigest()[:6], 16)
        r1, g1, b1 = (h_val >> 16) & 255, (h_val >> 8) & 255, h_val & 255
        r2, g2, b2 = (r1 + 70) % 256, (g1 + 80) % 256, (b1 + 90) % 256

        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)

        # Gradient fill
        for y in range(h):
            ratio = y / max(1, h - 1)
            r = int(r1 * (1 - ratio) + r2 * ratio)
            g = int(g1 * (1 - ratio) + g2 * ratio)
            b = int(b1 * (1 - ratio) + b2 * ratio)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # Border and caption text
        draw.rectangle([12, 12, w - 12, h - 12], outline=(255, 255, 255), width=2)
        summary = f"Prompt:\n{prompt[:120]}..." if len(prompt) > 120 else f"Prompt:\n{prompt}"
        draw.text((24, 24), summary, fill=(255, 255, 255))
        draw.text((24, h - 36), f"{w}x{h} • OpenLumara ImageTools (Mock)", fill=(230, 230, 230))
        img.save(target_path, "PNG")

    async def _generate_openai(self, prompt: str, size: str, style: str, target_path: str, model: str = None):
        """Calls OpenAI DALL-E / compatible image generation endpoint."""
        prov_url, prov_key = None, None
        if hasattr(self.manager.API, "get_image_model_provider"):
            p, _ = self.manager.API.get_image_model_provider()
            if p:
                prov_url = p.get("url")
                prov_key = p.get("key")

        api_key = prov_key or self.config.get("openai_api_key") or core.config.get("api", "key", default="")
        api_url = (prov_url or self.config.get("openai_api_url") or "https://api.openai.com/v1").rstrip("/")
        model = model or self._get_image_model()
        endpoint = f"{api_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json"
        }
        if model == "dall-e-3" and style in ("vivid", "natural"):
            payload["style"] = style

        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"OpenAI API returned HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            items = data.get("data", [])
            if not items:
                raise RuntimeError("No image data returned from image API")

            first_item = items[0]
            if "b64_json" in first_item:
                raw_bytes = base64.b64decode(first_item["b64_json"])
                with open(target_path, "wb") as f:
                    f.write(raw_bytes)
            elif "url" in first_item:
                img_resp = await client.get(first_item["url"])
                if img_resp.status_code != 200:
                    raise RuntimeError(f"Failed to download image URL: {img_resp.status_code}")
                with open(target_path, "wb") as f:
                    f.write(img_resp.content)
            else:
                raise RuntimeError("Unrecognized response payload structure")

    async def _generate_sd(self, prompt: str, width: int, height: int, target_path: str, negative_prompt: str = ""):
        """Calls local Stable Diffusion WebUI / Forge txt2img API."""
        base_url = (self.config.get("sd_webui_url") or "http://127.0.0.1:7860").rstrip("/")
        endpoint = f"{base_url}/sdapi/v1/txt2img"
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt or "",
            "width": width,
            "height": height,
            "steps": 25,
            "cfg_scale": 7.0
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(endpoint, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"SD WebUI returned HTTP {resp.status_code}: {resp.text}")

            data = resp.json()
            images = data.get("images", [])
            if not images:
                raise RuntimeError("No images returned from SD WebUI")

            img_b64 = images[0]
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            raw_bytes = base64.b64decode(img_b64)
            with open(target_path, "wb") as f:
                f.write(raw_bytes)

    # =========================================================================
    async def set_image_model(self, model_name: str):
        """
        Sets the designated image model to use for image generation and editing.

        Args:
            model_name: The name or ID of the image model (e.g. dall-e-3, dall-e-2, flux-schnell).
        """
        clean_name = str(model_name).strip()
        if not clean_name:
            return self.result("Model name cannot be empty.", success=False)
        if hasattr(self.manager.API, "set_image_model"):
            self.manager.API.set_image_model(clean_name)
        return self.result(f"Image model has been set to '{clean_name}'.", success=True)

    # AI Tools - Local Image Manipulation (Pillow)
    # =========================================================================

    async def add_text(self, image_path: str, text: str, position: str = "bottom", color: str = "white", output_path: str = ""):
        """
        Draws a text banner or caption onto an image (for watermarks, titles, labels, or memes).

        Args:
            image_path: Path to the image file.
            text: Caption or label text to overlay.
            position: "bottom", "top", or "center".
            color: "white", "black", "yellow", "red", "cyan".
            output_path: Optional destination path.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        dest = self._resolve_dest(output_path, src, suffix="_caption")
        try:
            with Image.open(src) as img:
                out = img.convert("RGB")
                draw = ImageDraw.Draw(out)
                w, h = out.size

                pos = position.lower().strip()
                if pos == "top":
                    y = 20
                elif pos == "center":
                    y = h // 2 - 15
                else:
                    y = h - 45

                draw.rectangle([(0, y - 6), (w, y + 26)], fill=(0, 0, 0))
                col_map = {"white": (255, 255, 255), "black": (0, 0, 0), "yellow": (255, 220, 0), "red": (255, 60, 60), "cyan": (0, 220, 255)}
                text_color = col_map.get(color.lower().strip(), (255, 255, 255))
                draw.text((20, y), text[:100], fill=text_color)
                out.save(dest)

            return self.result({
                "action": "add_text",
                "text": text,
                "source": src,
                "output": dest
            }, success=True)
        except Exception as e:
            return self.result(f"Failed to add text: {core.detail_error(e)}", success=False)

    async def resize(self, image_path: str, width: int, height: int, output_path: str = ""):
        """
        Resizes an image to specified width and height using high-quality Lanczos resampling.

        Args:
            image_path: Path to the image file to resize.
            width: New width in pixels.
            height: New height in pixels.
            output_path: Optional destination path. If omitted, saves as a new image in output_directory.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        width = max(1, int(width))
        height = max(1, int(height))

        dest = self._resolve_dest(output_path, src, suffix=f"_resize_{width}x{height}")
        try:
            with Image.open(src) as img:
                out = img.resize((width, height), Image.Resampling.LANCZOS)
                out.save(dest)

            return self.result({
                "action": "resize",
                "source": src,
                "output": dest,
                "dimensions": f"{width}x{height}"
            }, success=True)
        except Exception as e:
            return self.result(f"Resize failed: {core.detail_error(e)}", success=False)

    async def crop(self, image_path: str, left: int, top: int, right: int, bottom: int, output_path: str = ""):
        """
        Crops an image rectangle defined by (left, top, right, bottom) pixel coordinates.

        Args:
            image_path: Path to the image file.
            left: Left boundary pixel coordinate.
            top: Top boundary pixel coordinate.
            right: Right boundary pixel coordinate.
            bottom: Bottom boundary pixel coordinate.
            output_path: Optional destination path.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        if right <= left or bottom <= top:
            return self.result("Invalid crop coordinates: right must be > left, and bottom must be > top.", success=False)

        dest = self._resolve_dest(output_path, src, suffix="_crop")
        try:
            with Image.open(src) as img:
                w, h = img.size
                left_c = max(0, min(int(left), w - 1))
                top_c = max(0, min(int(top), h - 1))
                right_c = max(left_c + 1, min(int(right), w))
                bottom_c = max(top_c + 1, min(int(bottom), h))

                cropped = img.crop((left_c, top_c, right_c, bottom_c))
                cropped.save(dest)

            return self.result({
                "action": "crop",
                "source": src,
                "output": dest,
                "box": [left_c, top_c, right_c, bottom_c],
                "new_size": f"{cropped.width}x{cropped.height}"
            }, success=True)
        except Exception as e:
            return self.result(f"Crop failed: {core.detail_error(e)}", success=False)

    async def rotate(self, image_path: str, angle: float, expand: bool = True, output_path: str = ""):
        """
        Rotates an image counter-clockwise by a given number of degrees.

        Args:
            image_path: Path to the image file.
            angle: Rotation angle in degrees (e.g. 90, 180, 270, 45).
            expand: If True, expands the output image to fit the entire rotated shape without clipping.
            output_path: Optional destination path.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        dest = self._resolve_dest(output_path, src, suffix=f"_rot_{int(angle)}")
        try:
            with Image.open(src) as img:
                rotated = img.rotate(float(angle), expand=bool(expand), resample=Image.Resampling.BICUBIC)
                rotated.save(dest)

            return self.result({
                "action": "rotate",
                "source": src,
                "output": dest,
                "angle": angle,
                "dimensions": f"{rotated.width}x{rotated.height}"
            }, success=True)
        except Exception as e:
            return self.result(f"Rotation failed: {core.detail_error(e)}", success=False)

    async def flip(self, image_path: str, mode: str = "horizontal", output_path: str = ""):
        """
        Flips an image horizontally (mirror) or vertically.

        Args:
            image_path: Path to the image file.
            mode: "horizontal" (left-to-right mirror) or "vertical" (top-to-bottom flip).
            output_path: Optional destination path.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        mode_clean = mode.lower().strip()
        dest = self._resolve_dest(output_path, src, suffix=f"_flip_{mode_clean}")
        try:
            with Image.open(src) as img:
                if mode_clean in ("vertical", "v"):
                    flipped = ImageOps.flip(img)
                else:
                    flipped = ImageOps.mirror(img)
                flipped.save(dest)

            return self.result({
                "action": "flip",
                "mode": mode_clean,
                "source": src,
                "output": dest
            }, success=True)
        except Exception as e:
            return self.result(f"Flip failed: {core.detail_error(e)}", success=False)

    async def apply_filter(self, image_path: str, filter_type: str = "grayscale", output_path: str = ""):
        """
        Applies a visual filter or enhancement to an image.

        Args:
            image_path: Path to the image file.
            filter_type: One of: "grayscale", "blur", "sharpen", "contour", "edge_enhance", "invert", "brightness_boost", "contrast_boost".
            output_path: Optional destination path.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        f_name = filter_type.lower().strip()
        dest = self._resolve_dest(output_path, src, suffix=f"_{f_name}")

        try:
            with Image.open(src) as img:
                rgb_img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img

                if f_name in ("grayscale", "bw", "gray"):
                    out = ImageOps.grayscale(rgb_img)
                elif f_name == "blur":
                    out = rgb_img.filter(ImageFilter.GaussianBlur(radius=3))
                elif f_name == "sharpen":
                    out = rgb_img.filter(ImageFilter.SHARPEN)
                elif f_name == "contour":
                    out = rgb_img.filter(ImageFilter.CONTOUR)
                elif f_name == "edge_enhance":
                    out = rgb_img.filter(ImageFilter.EDGE_ENHANCE_MORE)
                elif f_name == "invert":
                    # Drop alpha if present for inversion
                    base = rgb_img.convert("RGB")
                    out = ImageOps.invert(base)
                elif f_name == "brightness_boost":
                    enhancer = ImageEnhance.Brightness(rgb_img)
                    out = enhancer.enhance(1.4)
                elif f_name == "contrast_boost":
                    enhancer = ImageEnhance.Contrast(rgb_img)
                    out = enhancer.enhance(1.4)
                else:
                    return self.result(f"Unsupported filter '{filter_type}'. Choose from: grayscale, blur, sharpen, contour, edge_enhance, invert, brightness_boost, contrast_boost.", success=False)

                out.save(dest)

            return self.result({
                "action": "filter",
                "filter": f_name,
                "source": src,
                "output": dest
            }, success=True)
        except Exception as e:
            return self.result(f"Filter failed: {core.detail_error(e)}", success=False)

    async def convert_format(self, image_path: str, format: str = "png", output_path: str = ""):
        """
        Converts an image to another file format (PNG, JPEG, WEBP, BMP).

        Args:
            image_path: Path to the image file.
            format: Target format extension ("png", "jpeg", "webp", "bmp").
            output_path: Optional destination path.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        fmt = format.lower().strip().replace(".", "")
        if fmt == "jpg":
            fmt = "jpeg"

        dest = output_path or os.path.splitext(src)[0] + f".{fmt}"
        dest = self._safe_image_path(dest)

        try:
            with Image.open(src) as img:
                if fmt in ("jpeg", "jpg") and img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(dest, fmt.upper())

            return self.result({
                "action": "convert_format",
                "format": fmt,
                "source": src,
                "output": dest
            }, success=True)
        except Exception as e:
            return self.result(f"Format conversion failed: {core.detail_error(e)}", success=False)

    async def get_info(self, image_path: str):
        """
        Retrieves image metadata including dimensions, format, color mode, and filesize.

        Args:
            image_path: Path to the image file.
        """
        src = self._safe_image_path(image_path)
        if not os.path.isfile(src):
            return self.result(f"File not found: {image_path}", success=False)

        try:
            stat = os.stat(src)
            with Image.open(src) as img:
                w, h = img.size
                fmt = img.format
                mode = img.mode

            ratio = round(w / max(1, h), 2)
            return self.result({
                "path": src,
                "filename": os.path.basename(src),
                "width": w,
                "height": h,
                "aspect_ratio": ratio,
                "format": fmt,
                "mode": mode,
                "size_kb": round(stat.st_size / 1024, 2)
            }, success=True)
        except Exception as e:
            return self.result(f"Failed to read image info: {core.detail_error(e)}", success=False)

    async def list_images(self, limit: int = 20):
        """
        Lists recently generated or edited images stored in the output directory.

        Args:
            limit: Maximum number of image records to return (default 20).
        """
        out_dir = self._get_output_dir()
        if not os.path.isdir(out_dir):
            return self.result([], success=True)

        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
        files = []
        for entry in os.scandir(out_dir):
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in valid_exts:
                files.append((entry.stat().st_mtime, entry.path, entry.name))

        files.sort(reverse=True, key=lambda x: x[0])
        limit_clean = max(1, min(int(limit), 100))

        items = []
        for mtime, path, name in files[:limit_clean]:
            items.append({
                "filename": name,
                "path": path,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            })
        return self.result(items, success=True)

    # -------------------------------------------------------------------------
    # Helper Paths
    # -------------------------------------------------------------------------

    def _resolve_dest(self, requested_dest: str, src_path: str, suffix: str = "") -> str:
        """Determines destination path for an edit operation."""
        if requested_dest:
            return self._safe_image_path(requested_dest)

        p = Path(src_path)
        out_dir = self._get_output_dir()
        new_name = f"{p.stem}{suffix}{p.suffix}"
        return os.path.join(out_dir, new_name)

    # =========================================================================
    # WebUI API Routes (/api/ext/image_tools/...)
    # =========================================================================

    @webui.route("list")
    async def _route_list(self, body=None, query=None):
        """Returns metadata for recent images in output directory."""
        res = await self.list_images(limit=50)
        return {"images": res.get("content", [])}

    @webui.route("view")
    async def _route_view(self, body=None, query=None):
        """Streams image binary with correct Content-Type."""
        query = query or {}
        fname = query.get("file", "")
        if not fname:
            return self.result("Missing file parameter", success=False)

        # Sanitize against directory traversal
        clean_name = os.path.basename(fname)
        full_path = os.path.join(self._get_output_dir(), clean_name)
        import fastapi
        if not os.path.isfile(full_path):
            raise fastapi.HTTPException(status_code=404, detail="Image not found")
        ext = os.path.splitext(clean_name)[1].lower()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif"
        }
        mt = media_types.get(ext, "application/octet-stream")
        return fastapi.responses.FileResponse(full_path, media_type=mt)

    @webui.route("delete", method="POST", admin_only=True)
    async def _route_delete(self, body=None, query=None):
        """Deletes an image from the gallery."""
        body = body or {}
        fname = body.get("filename", "")
        if not fname:
            return self.result("Missing filename", success=False)

        clean_name = os.path.basename(fname)
        full_path = os.path.join(self._get_output_dir(), clean_name)
        if os.path.isfile(full_path):
            os.remove(full_path)
            return self.result(f"Deleted {clean_name}", success=True)
        return self.result("File not found", success=False)
    @webui.route("settings")
    async def _route_get_settings(self, body=None, query=None):
        """Returns image generation & editing settings and available providers/models."""
        providers = []
        if hasattr(self.manager.API, "get_providers"):
            for p in self.manager.API.get_providers():
                providers.append({
                    "id": p["id"],
                    "name": p["name"],
                    "models": [m["id"] if isinstance(m, dict) else str(m) for m in p.get("models", [])]
                })

        return {
            "enabled": self.config.get("enabled", True),
            "ask_before_generate": self.config.get("ask_before_generate", False),
            "endpoint": self.config.get("endpoint", "auto"),
            "model": self._get_image_model(),
            "quality": self.config.get("quality", "high"),
            "edit_endpoint": self.config.get("edit_endpoint", "auto"),
            "edit_model": self.config.get("edit_model", "same"),
            "providers": providers
        }

    @webui.route("settings", method="POST")
    async def _route_save_settings(self, body=None, query=None):
        """Saves image generation & editing settings."""
        body = body or {}
        for key in ("enabled", "ask_before_generate", "endpoint", "model", "quality", "edit_endpoint", "edit_model"):
            if key in body:
                self.config.set(key, body[key])
        if "model" in body and body["model"]:
            if hasattr(self.manager.API, "set_image_model"):
                self.manager.API.set_image_model(body["model"])
        core.config.config.save()
        return self.result({"saved": True}, success=True)


    # =========================================================================
    # User Command (/images)
    # =========================================================================

    @core.module.command("images", help={
        "list": "Lists recent generated/edited images",
        "dir": "Shows configured image output folder"
    })
    async def images_command(self, args: list):
        """View recent images directly in chat."""
        sub = args[0] if args else "list"
        if sub == "dir":
            return f"Image output directory: `{self._get_output_dir()}`"

        res = await self.list_images(limit=10)
        items = res.get("content", [])
        if not items:
            return "No images found in output folder."

        lines = ["**Recent Images**:"]
        for it in items:
            lines.append(f"- `{it['filename']}` ({it['modified']})")
        return "\n".join(lines)
