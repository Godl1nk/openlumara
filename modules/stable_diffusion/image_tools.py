# -- AI GENERATED CODE (GPT-6) :: 2026-11-21 18:19:00 +08:00 harness:Codex
import asyncio
import os
import io
import time
import base64
import hashlib
import urllib.parse
from pathlib import Path

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageEnhance

import core
import channels.webui.api as webui

class ImageTools:
    """Provider generation, editing and historical image links for Stable Diffusion."""

    edit_tools = {"add_text", "resize", "crop", "rotate", "flip", "apply_filter", "convert_format"}
    media_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif"}

    def _prepare_image_tools(self):
        """Ensure the output directory exists."""
        out_dir = self._get_output_dir()
        os.makedirs(out_dir, exist_ok=True)
        disabled = set()
        if self.config.get("enabled") is False:
            disabled.update(self.edit_tools)
        if self.config.get("enabled") is False or self._generation_disabled():
            disabled.add("generate_image")
        if "models" in core.config.get("modules", "enabled", default=[]):
            disabled.add("set_image_model")
        self.disabled_tools[:] = sorted(disabled)

    def _generation_disabled(self):
        return self.config.get("generation") == "disabled"

    def _get_output_dir(self) -> str:
        configured = self.config.get("output_directory") or "data/images"
        if os.path.isabs(configured):
            return configured
        return core.get_path(configured, sandbox=False)

    def _view_url(self, path: str) -> str:
        """Web URL that serves an image saved in the output directory."""
        return f"/api/ext/stable_diffusion/view?file={urllib.parse.quote(os.path.basename(path))}"

    async def _refresh_gallery(self):
        websockets = getattr(self.channel, "websocket_manager", None)
        if websockets is not None:
            await websockets.broadcast({"type": "sd_gallery_refresh"})

    async def _edit_result(self, action: str, src: str, dest: str, alt: str = None, **extra):
        """Edit result carrying a ready-to-use web link.

        The model pastes this into its reply, so it has to be a URL: a bare
        filesystem path renders as a broken image in the chat.
        """
        payload = {
            "action": action,
            "source": src,
            "output": dest,
        }
        if Path(dest).resolve().parent == Path(self._get_output_dir()).resolve():
            url = self._view_url(dest)
            payload.update(url=url, markdown=f"![{alt or action}]({url})")
            await self._refresh_gallery()
        payload.update(extra)
        return self.result(payload, success=True)

    def _get_image_model(self) -> str:
        """Resolve active image model from module config, global core config, or fallback."""
        if core.config.get("model", "image_provider_id"):
            return self.manager.API.get_image_model()
        return core.config.get("model", "image_model") or self.config.get("openai_model") or "dall-e-3"

    def _provider_for_endpoint(self, endpoint: str, providers=None):
        """Resolve provider ID or an unambiguous legacy display name."""
        endpoint = str(endpoint or "").strip()
        if not endpoint or endpoint.lower() == "auto":
            return None
        if providers is None:
            providers = self.manager.API.get_providers()
        for provider in providers:
            if provider["id"] == endpoint:
                return provider if provider.get("enabled", True) else None
        matches = [provider for provider in providers if provider.get("enabled", True) and provider.get("name") == endpoint]
        return matches[0] if len(matches) == 1 else None

    _APPROVAL_WORDS = {
        "proceed", "yes", "y", "yep", "yeah", "ok", "okay", "sure",
        "approve", "approved", "confirm", "confirmed", "allow", "allowed",
        "accept", "accepted",
    }
    _DENIAL_WORDS = {
        "cancel", "no", "nope", "stop", "abort", "deny", "reject",
        "rejected", "decline", "don't", "dont", "not", "never", "wait",
    }
    _APPROVAL_PHRASES = ("go ahead", "go for it", "do it", "please do", "looks good", "that's fine")

    def _answer_is_approval(self, answer: str) -> bool:
        """True when a free-text answer clearly approves the action.

        Accepts natural replies like "yes, approve the resize" (answering in chat
        sends the raw message, not an option label) while failing closed: any
        negative wording wins, and anything ambiguous counts as a denial.
        """
        text = "".join(ch if (ch.isalnum() or ch in "' ") else " " for ch in str(answer or "").lower())
        text = " ".join(text.split())
        words = set(text.split())
        if words & self._DENIAL_WORDS:
            return False
        if words & self._APPROVAL_WORDS:
            return True
        return any(phrase in text for phrase in self._APPROVAL_PHRASES)

    async def authorize_image_action(self, action: str, detail: str = ""):
        """Return a refusal reason or None before an AI image operation."""
        if self.config.get("enabled") is False:
            return "AI image generation and editing are disabled in Stable Diffusion."
        if not self.config.get("ask_before_generate"):
            return None

        ask_mod = self.manager.modules.get("ask_user")
        if not ask_mod or not hasattr(ask_mod, "ask"):
            return ("Approval is required because 'ask before generate/edit' is enabled, "
                    "but the ask_user module is not enabled. Enable ask_user or turn the toggle off.")

        prompt = f"{action}\n{detail}" if detail else action
        ack = await ask_mod.ask(
            prompt,
            options=["Proceed", "Cancel"],
            timeout=int(self.config.get("approval_timeout") or 60),
            default_choice="Cancel",
        )
        content = (ack or {}).get("content") or {}
        if (ack or {}).get("status") != "success" or not isinstance(content, dict):
            return "Image action was not approved."

        if not self._answer_is_approval(content.get("answer")):
            return "Image action cancelled by user."
        return None


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

    def _generate_mock(self, prompt: str, size: tuple):
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
        draw.text((24, h - 36), f"{w}x{h} • Aegis ImageTools (Mock)", fill=(230, 230, 230))
        output = io.BytesIO()
        img.save(output, "PNG")
        return output.getvalue()

    # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-24 08:07 +08:00 harness:Codex
    def _configured_image_provider(self, providers=None):
        endpoint = str(self.config.get("endpoint") or "auto").strip()
        if not endpoint or endpoint.lower() == "auto":
            return None
        provider = self._provider_for_endpoint(endpoint, providers)
        if not provider:
            raise RuntimeError("Image endpoint override is unavailable or ambiguous. Check the Stable Diffusion settings.")
        return provider

    def _selected_image_endpoint(self, provider=None):
        provider = provider or self._configured_image_provider()
        if not provider and hasattr(self.manager.API, "get_image_model_provider"):
            provider, _ = self.manager.API.get_image_model_provider()
        if provider:
            api_url = provider.get("url")
            if not api_url:
                raise RuntimeError("Selected image provider has no endpoint URL.")
            api_key = provider.get("key")
        else:
            api_url = core.config.get("api", "url")
            module_url = self.config.get("openai_api_url") or "https://api.openai.com/v1"
            if not api_url or api_url == "http://API_URL_HERE/v1":
                api_url, api_key = module_url, self.config.get("openai_api_key")
            else:
                api_key = core.config.get("api", "key")
                if not api_key and api_url.rstrip("/") == module_url.rstrip("/"):
                    api_key = self.config.get("openai_api_key")
        return api_url.rstrip("/"), api_key

    # -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-23 21:06 +08:00 harness:Codex
    def _selected_provider_resolution(self, width, height, model=''):
        model = (model or self._get_image_model()).lower()
        if model == "dall-e-2":
            side = min((256, 512, 1024), key=lambda size: abs(size - max(width, height)))
            return side, side
        if model == "dall-e-3" or model.startswith("gpt-image-1"):
            long_side = 1792 if model == "dall-e-3" else 1536
            if width == height:
                return 1024, 1024
            return (long_side, 1024) if width > height else (1024, long_side)
        return width, height

    async def _generate_selected_provider(self, prompt: str, size: str, model='', provider=None):
        """Calls the selected OpenAI-compatible image endpoint."""
        api_url, api_key = self._selected_image_endpoint(provider)
        model = model or self._get_image_model()
        endpoint = f"{api_url}/images/generations"
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": size
        }
        if not model.lower().startswith("gpt-image-"):
            payload["response_format"] = "b64_json"
        if model == "dall-e-3":
            quality = str(self.config.get("quality") or "high").lower()
            payload["quality"] = "hd" if quality in ("high", "hd") else "standard"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90), trust_env=True) as session:
            async with session.post(endpoint, json=payload, headers=headers) as response:
                if response.status != 200:
                    detail = (await response.content.read(2048)).decode(errors="replace")
                    raise RuntimeError(f"Image API returned HTTP {response.status}: {detail}")
                data = await response.json(content_type=None)

            items = data.get("data", [])
            if not items:
                raise RuntimeError("No image data returned from image API")

            first_item = items[0]
            if "b64_json" in first_item:
                return base64.b64decode(first_item["b64_json"])
            elif "url" in first_item:
                img_url = str(first_item["url"])
                if urllib.parse.urlparse(img_url).scheme not in ("http", "https"):
                    raise RuntimeError("Image API returned a non-http(s) image URL")
                limit = 50 * 1024 * 1024
                async with session.get(img_url, allow_redirects=False) as image_response:
                    if image_response.status != 200:
                        raise RuntimeError(f"Failed to download image URL: {image_response.status}")
                    try:
                        await image_response.content.readexactly(limit + 1)
                    except asyncio.IncompleteReadError as image:
                        return image.partial
                    raise RuntimeError("Image download exceeded the 50 MB limit")
            else:
                raise RuntimeError("Unrecognized response payload structure")

    @core.module.tool
    async def set_image_model(self, model_name: str):
        """
        Sets the image generation model.

        Args:
            model_name: The name or ID of the image model (e.g. dall-e-3, dall-e-2, flux-schnell).
        """
        clean_name = str(model_name).strip()
        if not clean_name:
            return self.result("Model name cannot be empty.", success=False)
        if not self.manager.API.set_image_model(clean_name):
            return self.result("Choose an enabled image model and its provider.", success=False)
        return self.result(f"Image model has been set to '{clean_name}'.", success=True)

    # AI Tools - Local Image Manipulation (Pillow)
    # =========================================================================

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"add_text on {image_path}")
        if approval_error:
            return self.result(approval_error, success=False)

        dest = self._resolve_dest(output_path, src, suffix="_caption")
        if not dest:
            return self.result("Output path must be inside the project or image output directory.", success=False)
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

            return await self._edit_result("add_text", src, dest, text=text)
        except Exception as e:
            return self.result(f"Failed to add text: {core.detail_error(e)}", success=False)

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"resize to {width}x{height}")
        if approval_error:
            return self.result(approval_error, success=False)

        dest = self._resolve_dest(output_path, src, suffix=f"_resize_{width}x{height}")
        if not dest:
            return self.result("Output path must be inside the project or image output directory.", success=False)
        try:
            with Image.open(src) as img:
                out = img.resize((width, height), Image.Resampling.LANCZOS)
                out.save(dest)

            return await self._edit_result("resize", src, dest, f"resized {width}x{height}", dimensions=f"{width}x{height}")
        except Exception as e:
            return self.result(f"Resize failed: {core.detail_error(e)}", success=False)

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"crop {image_path}")
        if approval_error:
            return self.result(approval_error, success=False)

        dest = self._resolve_dest(output_path, src, suffix="_crop")
        if not dest:
            return self.result("Output path must be inside the project or image output directory.", success=False)
        try:
            with Image.open(src) as img:
                w, h = img.size
                left_c = max(0, min(int(left), w - 1))
                top_c = max(0, min(int(top), h - 1))
                right_c = max(left_c + 1, min(int(right), w))
                bottom_c = max(top_c + 1, min(int(bottom), h))

                cropped = img.crop((left_c, top_c, right_c, bottom_c))
                cropped.save(dest)

            return await self._edit_result("crop", src, dest, f"cropped {cropped.width}x{cropped.height}",
                                     box=[left_c, top_c, right_c, bottom_c],
                                     new_size=f"{cropped.width}x{cropped.height}")
        except Exception as e:
            return self.result(f"Crop failed: {core.detail_error(e)}", success=False)

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"rotate by {angle} degrees")
        if approval_error:
            return self.result(approval_error, success=False)

        dest = self._resolve_dest(output_path, src, suffix=f"_rot_{int(angle)}")
        if not dest:
            return self.result("Output path must be inside the project or image output directory.", success=False)
        try:
            with Image.open(src) as img:
                rotated = img.rotate(float(angle), expand=bool(expand), resample=Image.Resampling.BICUBIC)
                rotated.save(dest)

            return await self._edit_result("rotate", src, dest, f"rotated {angle} degrees",
                                     angle=angle, dimensions=f"{rotated.width}x{rotated.height}")
        except Exception as e:
            return self.result(f"Rotation failed: {core.detail_error(e)}", success=False)

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"flip {mode_clean}")
        if approval_error:
            return self.result(approval_error, success=False)

        dest = self._resolve_dest(output_path, src, suffix=f"_flip_{mode_clean}")
        if not dest:
            return self.result("Output path must be inside the project or image output directory.", success=False)
        try:
            with Image.open(src) as img:
                if mode_clean in ("vertical", "v"):
                    flipped = ImageOps.flip(img)
                else:
                    flipped = ImageOps.mirror(img)
                flipped.save(dest)

            return await self._edit_result("flip", src, dest, f"flipped {mode_clean}", mode=mode_clean)
        except Exception as e:
            return self.result(f"Flip failed: {core.detail_error(e)}", success=False)

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"apply {f_name} filter")
        if approval_error:
            return self.result(approval_error, success=False)

        dest = self._resolve_dest(output_path, src, suffix=f"_{f_name}")
        if not dest:
            return self.result("Output path must be inside the project or image output directory.", success=False)

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

            return await self._edit_result("filter", src, dest, f"{f_name} filter", filter=f_name)
        except Exception as e:
            return self.result(f"Filter failed: {core.detail_error(e)}", success=False)

    @core.module.tool
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

        approval_error = await self.authorize_image_action("Image edit requested:", f"convert to {fmt}")
        if approval_error:
            return self.result(approval_error, success=False)

        if output_path:
            dest = self._safe_image_path(output_path)
        else:
            dest = os.path.join(self._get_output_dir(), f"{Path(src).stem}_converted.{fmt}")
        if not dest or not self._is_allowed_dest(dest):
            return self.result("Output path must be inside the project or image output directory.", success=False)

        try:
            with Image.open(src) as img:
                if fmt in ("jpeg", "jpg") and img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(dest, fmt.upper())

            return await self._edit_result("convert_format", src, dest, f"converted to {fmt}", format=fmt)
        except Exception as e:
            return self.result(f"Format conversion failed: {core.detail_error(e)}", success=False)

    @core.module.tool
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

    @core.module.tool
    async def list_images(self, limit: int = 20):
        """
        Lists recently generated or edited images stored in the output directory.

        Args:
            limit: Maximum number of image records to return (default 20).
        """
        images = self._recent_images((self._get_output_dir(), self.output_dir), limit)
        return self.result(images, success=True)

    def _recent_images(self, folders, limit, exclude=()):
        files = []
        for folder in dict.fromkeys(os.path.realpath(path) for path in folders):
            if not os.path.isdir(folder):
                continue
            with os.scandir(folder) as entries:
                for entry in entries:
                    if (entry.name in exclude or not entry.is_file(follow_symlinks=False)
                        or os.path.splitext(entry.name)[1].lower() not in self.media_types):
                        continue
                    try:
                        stat = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if stat.st_size:
                        files.append((stat.st_mtime, entry.path, entry.name))

        files.sort(reverse=True, key=lambda x: x[0])
        limit_clean = max(1, min(int(limit), 100))

        items = []
        for mtime, path, name in files[:limit_clean]:
            items.append({
                "filename": name,
                "path": path,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            })
        return items

    # -------------------------------------------------------------------------
    # Helper Paths
    # -------------------------------------------------------------------------

    def _is_allowed_dest(self, path: str) -> bool:
        """Writes are only allowed under the project root or the image output dir."""
        try:
            target = Path(path).resolve()
        except Exception:
            return False
        roots = []
        try:
            roots.append(Path(core.get_path()).resolve())
        except Exception:
            pass
        try:
            roots.append(Path(self._get_output_dir()).resolve())
        except Exception:
            pass
        return any(target == root or root in target.parents for root in roots)

    def _resolve_dest(self, requested_dest: str, src_path: str, suffix: str = "") -> str:
        """Determines destination path for an edit operation."""
        if requested_dest:
            dest = self._safe_image_path(requested_dest)
            return dest if dest and self._is_allowed_dest(dest) else None

        p = Path(src_path)
        out_dir = self._get_output_dir()
        new_name = f"{p.stem}{suffix}{p.suffix}"
        return os.path.join(out_dir, new_name)

    # =========================================================================
    # WebUI API Routes (/api/ext/stable_diffusion/...)
    # =========================================================================

    @webui.route("list")
    async def _route_list(self, body=None, query=None):
        """Returns metadata for recent images in output directory."""
        return {"images": self._recent_images((self._get_output_dir(),), 50)}

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
        ext = os.path.splitext(clean_name)[1].lower()
        mt = self.media_types.get(ext)
        if not mt or os.path.islink(full_path) or not os.path.isfile(full_path):
            raise fastapi.HTTPException(status_code=404, detail="Image not found")
        return fastapi.responses.FileResponse(full_path, media_type=mt, headers={"Cache-Control": "private, no-cache"})

    @webui.route("delete", method="POST", admin_only=True)
    async def _route_delete(self, body=None, query=None):
        """Deletes an image from the gallery."""
        body = body or {}
        fname = body.get("filename", "")
        if not fname:
            return self.result("Missing filename", success=False)

        clean_name = os.path.basename(fname)
        full_path = os.path.join(self._get_output_dir(), clean_name)
        if os.path.splitext(clean_name)[1].lower() in self.media_types and os.path.isfile(full_path):
            os.remove(full_path)
            await self._refresh_gallery()
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
                    "enabled": p.get("enabled", True),
                    "models": [m["id"] if isinstance(m, dict) else str(m) for m in p.get("models", [])]
                })

        endpoint = self.config.get("endpoint") or "auto"
        provider = self._provider_for_endpoint(endpoint, providers)
        return {
            "enabled": self.config.get("enabled") is not False,
            "selected_provider": self.config.get("backend") == "selected_provider",
            "ask_before_generate": bool(self.config.get("ask_before_generate")),
            "endpoint": provider["id"] if provider else endpoint,
            "model": self._get_image_model(),
            "quality": self.config.get("quality") or "high",
            "providers": providers
        }

    @webui.route("settings", method="POST", admin_only=True)
    async def _route_save_settings(self, body=None, query=None):
        """Saves image generation settings."""
        body = body or {}
        enabled_changed = "enabled" in body and body["enabled"] != self.config.get("enabled")
        if "model" in body and not self.manager.API.set_image_model(body["model"]):
            return self.result("Choose an enabled image model and its provider.", success=False)
        for key in ("enabled", "ask_before_generate", "endpoint", "quality"):
            if key in body:
                self.config.set(key, body[key])
        core.config.config.save()
        if enabled_changed:
            await self.manager.reload_module(self.name)
        return self.result({"saved": True}, success=True)


    # =========================================================================
    # User Command (/images)
    # =========================================================================

    @core.module.command("images", help={
        "list": "Lists recent generated/edited images",
        "dir": "Shows generated and edited image folders"
    })
    async def images_command(self, args: list):
        """View recent images directly in chat."""
        sub = args[0] if args else "list"
        if sub == "dir":
            return f"Generated images: `{self.output_dir}`\nEdited images: `{self._get_output_dir()}`"

        res = await self.list_images(limit=10)
        items = res.get("content", [])
        if not items:
            return "No images found in output folder."

        lines = ["**Recent Images**:"]
        for it in items:
            lines.append(f"- `{it['filename']}` ({it['modified']})")
        return "\n".join(lines)
