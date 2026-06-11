"""
axiom/image_generator.py

Image generator engine for Axiom AI.
Translates game/narrative context into visual prompts using the LLM and calls
local image generation APIs (Stable Diffusion WebUI, ComfyUI, or mock).
"""

from __future__ import annotations

import base64
import json
import random
import re
from pathlib import Path
from typing import Any

from axiom.backends.base import LLMBackend
from axiom.config import AppConfig
from axiom.logger import logger

MOCK_PNG_BASE64 = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

# Aspect ratios accepted by the Gemini image API (it takes a ratio, not pixel
# dimensions). The configured width/height are mapped to the closest one.
GEMINI_ASPECT_RATIOS: tuple[str, ...] = (
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9",
)


def closest_aspect_ratio(width: int, height: int) -> str:
    """Return the supported Gemini aspect ratio closest to width/height."""
    if width <= 0 or height <= 0:
        return "1:1"
    target = width / height
    return min(
        GEMINI_ASPECT_RATIOS,
        key=lambda r: abs((int(r.split(":")[0]) / int(r.split(":")[1])) - target),
    )


class ImageGenerator:
    """Handles prompt generation and communication with local image generation backends.

    Attributes:
        config: The AppConfig instance containing image settings.
        llm:    The LLMBackend instance used for prompt engineering.
    """

    def __init__(self, config: AppConfig, llm: LLMBackend | None = None) -> None:
        self.config = config
        self._llm = llm

    def generate_prompt(
        self,
        narrative_text: str,
        location_desc: str = "",
        character_desc: str = "",
        game_state_tag: str = "",
    ) -> str:
        """Use the auxiliary LLM to extract a visual prompt from the narrative turn.

        Args:
            narrative_text: Prose description of the scene.
            location_desc:  Optional description of the location/environment.
            character_desc: Optional description of characters present.
            game_state_tag: Optional mood tag (exploration, combat, dialogue, tension).

        Returns:
            A comma-separated visual prompt optimized for Stable Diffusion.
        """
        if not self._llm:
            return "a digital fantasy painting of a fantasy scene"

        # Strip any markdown image tags or HTML tags
        from axiom.prompts import _strip_media_tags
        clean_narrative = _strip_media_tags(narrative_text)

        system_prompt = (
            "You are a visual prompt generator for AI image models like Stable Diffusion and ComfyUI.\n"
            "Given a piece of narrative text and context (character description, location, game state), "
            "your task is to return a clean, descriptive, comma-separated list of visual keywords (prompt) "
            "optimized for text-to-image generation.\n\n"
            "CRITICAL RULES:\n"
            "1. Only return the comma-separated prompt. Do NOT include phrases like 'Here is the prompt:', "
            "'Description:', or any markdown quotes/formatting.\n"
            "2. Keep the prompt descriptive, focusing on characters, clothing, actions, environment, lighting, and style "
            "(e.g., 'digital oil painting', 'fantasy concept art', 'highly detailed').\n"
            "3. Keep the output under 75 words.\n"
            "4. Do NOT write conversational text."
        )

        user_content = f"Narrative Text:\n{clean_narrative}\n"
        if location_desc:
            user_content += f"Location/Environment:\n{location_desc}\n"
        if character_desc:
            user_content += f"Characters Involved:\n{character_desc}\n"
        if game_state_tag:
            user_content += f"Mood/Atmosphere: {game_state_tag}\n"
        user_content += "\nGenerate the visual prompt now."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            resp = self._llm.complete(messages, max_tokens=150)
            prompt = resp.narrative_text.strip()
            # Clean up potential markdown formatting around the output
            prompt = re.sub(r"^[`'\"]+", "", prompt)
            prompt = re.sub(r"[`'\"]+$", "", prompt)
            return prompt
        except Exception as e:
            logger.warning(f"Failed to generate visual prompt via LLM: {e}. Using fallback.")
            return "fantasy concept art, digital painting, atmospheric lighting"

    def generate_image(self, prompt: str, save_dir: str | Path, filename: str) -> str | None:
        """Call the configured backend to generate and save an image.

        Args:
            prompt:   Visual prompt.
            save_dir: Path to directory where the image should be saved.
            filename: File name to save under (should end with .png).

        Returns:
            The absolute path to the generated image file, or None if generation failed.
        """
        import requests

        save_path = Path(save_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)

        backend = self.config.image_backend.lower().strip()

        # Fix URL scheme if missing (e.g. "127.0.0.1:7860" -> "http://127.0.0.1:7860")
        api_url = self.config.image_api_url.strip()
        if api_url and not api_url.startswith(("http://", "https://")):
            api_url = f"http://{api_url}"

        if backend == "mock":
            return self._save_mock_image(save_path)

        if backend == "gemini":
            return self._generate_gemini(prompt, save_path)

        if backend not in ("stable_diffusion", "comfyui"):
            logger.warning(f"Unknown image backend '{backend}': no image generated.")
            return None

        # Local backends can be slow (first call loads the model, AMD/CPU rigs
        # take minutes): the timeout must be configurable, 30s was never enough.
        timeout_s = max(10, self.config.image_timeout)

        if backend == "stable_diffusion":
            try:
                url = f"{api_url.rstrip('/')}/sdapi/v1/txt2img"
                payload = {
                    "prompt": prompt,
                    "negative_prompt": "blurry, low quality, distorted, extra limbs, bad anatomy, text, watermark",
                    "steps": self.config.image_steps,
                    "width": self.config.image_width,
                    "height": self.config.image_height,
                    "cfg_scale": self.config.image_cfg_scale,
                }

                logger.info(f"Requesting SD image from {url} for prompt: {prompt[:50]}...")
                response = requests.post(url, json=payload, timeout=timeout_s)
                if response.status_code == 404:
                    # The WebUI is up but its API is not: /sdapi/* only exists
                    # when the server was started with the --api flag.
                    logger.warning(
                        f"SD WebUI at {api_url} answered 404 on {url}: the server is "
                        f"running WITHOUT its API. Restart it with the --api option "
                        f"(e.g. ./webui.sh --api or COMMANDLINE_ARGS=\"--api\")."
                    )
                    return None
                response.raise_for_status()

                data = response.json()
                if "images" in data and len(data["images"]) > 0:
                    img_data = base64.b64decode(data["images"][0])
                    save_path.write_bytes(img_data)
                    logger.info(f"Successfully saved SD image to {save_path}")
                    return str(save_path.resolve())
                else:
                    logger.warning("No images returned from SD WebUI API.")
            except requests.exceptions.Timeout:
                logger.warning(
                    f"Stable Diffusion image generation timed out after {timeout_s}s. "
                    f"Increase the image timeout in the settings (slow hardware needs "
                    f"more, especially on the first image while the model loads)."
                )
            except Exception as e:
                logger.warning(
                    f"Stable Diffusion image generation failed: {e}. "
                    f"Please verify that Stable Diffusion WebUI is running at {api_url} and started with the --api option."
                )

        elif backend == "comfyui":
            try:
                base_url = api_url.rstrip('/')
                workflow = self._load_comfyui_workflow(prompt, base_url)
                prompt_url = f"{base_url}/prompt"

                logger.info(f"Submitting workflow to ComfyUI at {prompt_url}")
                response = requests.post(prompt_url, json={"prompt": workflow}, timeout=10)
                if response.status_code == 400:
                    # ComfyUI validates the workflow upfront and answers 400
                    # with per-node errors (missing checkpoint, bad input name…).
                    try:
                        err = response.json()
                        parts = [(err.get("error") or {}).get("message", "")]
                        for node_id, node_err in (err.get("node_errors") or {}).items():
                            label = node_err.get("class_type", f"node {node_id}")
                            for node_e in node_err.get("errors", []):
                                parts.append(
                                    f"{label}: {node_e.get('message', '')} "
                                    f"{node_e.get('details', '')}".strip()
                                )
                        detail = "; ".join(p for p in parts if p)
                    except Exception:
                        detail = response.text[:300]
                    logger.warning(
                        f"ComfyUI rejected the workflow: {detail or 'invalid prompt'}. "
                        f"Check the model/node names in your workflow (settings, "
                        f"Illustration tab)."
                    )
                    return None
                response.raise_for_status()

                res_data = response.json()
                prompt_id = res_data.get("prompt_id")
                if not prompt_id:
                    logger.warning("ComfyUI response did not contain prompt_id.")
                    return None

                logger.info(f"ComfyUI prompt submitted. ID: {prompt_id}. Polling for completion...")
                import time

                completed_data = None
                history_url = f"{base_url}/history/{prompt_id}"

                for _ in range(timeout_s):  # ~1 poll per second up to the timeout
                    time.sleep(1)
                    try:
                        hist_resp = requests.get(history_url, timeout=5)
                        if hist_resp.status_code == 200:
                            hist_data = hist_resp.json()
                            if prompt_id in hist_data:
                                completed_data = hist_data[prompt_id]
                                break
                    except Exception as poll_err:
                        logger.warning(f"Error polling ComfyUI history: {poll_err}")

                if not completed_data:
                    logger.warning(
                        f"ComfyUI generation not finished after {timeout_s}s. "
                        f"Increase the image timeout in the settings if your "
                        f"hardware needs more time per image."
                    )
                    return None

                outputs = completed_data.get("outputs", {})
                image_info = None
                for _, node_output in outputs.items():
                    if "images" in node_output:
                        for img in node_output["images"]:
                            if img.get("type") in ("output", "temp"):
                                image_info = img
                                break
                    if image_info:
                        break

                if not image_info:
                    logger.warning("Could not find generated image info in ComfyUI outputs.")
                    return None

                filename_param = image_info["filename"]
                subfolder_param = image_info.get("subfolder", "")
                type_param = image_info.get("type", "output")

                view_url = f"{base_url}/view?filename={filename_param}&subfolder={subfolder_param}&type={type_param}"
                logger.info(f"Fetching ComfyUI image from {view_url}")

                img_resp = requests.get(view_url, timeout=15)
                img_resp.raise_for_status()

                save_path.write_bytes(img_resp.content)
                logger.info(f"Successfully saved ComfyUI image to {save_path}")
                return str(save_path.resolve())

            except Exception as e:
                logger.warning(
                    f"ComfyUI image generation failed: {e}. "
                    f"Please verify that ComfyUI is running at {api_url}."
                )

        # Real backend failed: no image for this turn (TICKET-045). A 1×1 mock
        # placeholder in the chat would be worse than nothing.
        return None

    def _generate_gemini(self, prompt: str, save_path: Path) -> str | None:
        """Generate an image through the Gemini API (cloud, no local install).

        Reuses the text backend's API key and quota resilience; the dedicated
        image model comes from config.image_gemini_model. Real failure → None
        (TICKET-045: no placeholder).
        """
        api_key = (self.config.gemini_api_key or "").strip()
        if not api_key:
            logger.warning(
                "Gemini image backend selected but no Gemini API key is configured: "
                "no image generated."
            )
            return None

        try:
            from axiom.backends.gemini import GeminiClient

            client = GeminiClient(
                api_key=api_key,
                model_name=self.config.image_gemini_model,
                requests_per_minute=self.config.llm_requests_per_minute,
            )
            # Propagate the status/cancellation hooks of the session's text
            # backend (TICKET-033) so retry countdowns stay visible/cancellable.
            if self._llm is not None:
                client.on_status = getattr(self._llm, "on_status", None)
                client.cancel_event = getattr(self._llm, "cancel_event", None)

            aspect_ratio = closest_aspect_ratio(
                self.config.image_width, self.config.image_height
            )
            logger.info(
                f"Requesting Gemini image ({self.config.image_gemini_model}, "
                f"{aspect_ratio}) for prompt: {prompt[:50]}..."
            )
            img_data = client.generate_image_bytes(prompt, aspect_ratio=aspect_ratio)
            if not img_data:
                logger.warning("Gemini response did not contain an image part.")
                return None

            save_path.write_bytes(img_data)
            logger.info(f"Successfully saved Gemini image to {save_path}")
            return str(save_path.resolve())
        except Exception as e:
            logger.warning(
                f"Gemini image generation failed: {e}. "
                f"Please verify the API key and the image model "
                f"'{self.config.image_gemini_model}' in the settings."
            )
            return None

    def _save_mock_image(self, save_path: Path) -> str:
        """Write the mock PNG data to the target path."""
        img_data = base64.b64decode(MOCK_PNG_BASE64)
        save_path.write_bytes(img_data)
        logger.info(f"Successfully saved mock image to {save_path}")
        return str(save_path.resolve())

    def _comfyui_available_checkpoints(self, base_url: str) -> list[str]:
        """Return the checkpoint files installed on the ComfyUI server (or [])."""
        import requests

        try:
            resp = requests.get(
                f"{base_url}/object_info/CheckpointLoaderSimple", timeout=10
            )
            resp.raise_for_status()
            node_info = resp.json().get("CheckpointLoaderSimple", {})
            choices = node_info["input"]["required"]["ckpt_name"][0]
            if isinstance(choices, list):
                return [c for c in choices if isinstance(c, str)]
        except Exception as e:
            logger.warning(f"Could not list ComfyUI checkpoints from {base_url}: {e}")
        return []

    def _load_comfyui_workflow(self, prompt: str, base_url: str = "") -> dict:
        """Load, configure, and inject parameters into ComfyUI workflow JSON."""
        workflow_str = self.config.image_comfyui_workflow.strip()
        workflow = None

        if workflow_str:
            # Check if it's a file path
            if Path(workflow_str).is_file():
                try:
                    workflow = json.loads(Path(workflow_str).read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"Failed to read ComfyUI workflow file {workflow_str}: {e}")
            else:
                # Try parsing as raw JSON string
                try:
                    workflow = json.loads(workflow_str)
                except Exception as e:
                    logger.warning(f"Failed to parse ComfyUI workflow JSON string: {e}")

        if not workflow:
            # Default workflow template
            workflow = {
                "3": {
                    "class_type": "KSampler",
                    "inputs": {
                        "cfg": 7.0,
                        "denoise": 1.0,
                        "latent_image": ["5", 0],
                        "model": ["4", 0],
                        "negative": ["7", 0],
                        "positive": ["6", 0],
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "seed": 42,
                        "steps": 20,
                    },
                },
                "4": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"},
                },
                "5": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {"batch_size": 1, "height": 512, "width": 512},
                },
                "6": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {"clip": ["4", 1], "text": "{prompt}"},
                },
                "7": {
                    "class_type": "CLIPTextEncode",
                    "inputs": {
                        "clip": ["4", 1],
                        "text": "blurry, low quality, distorted, extra limbs, bad anatomy, text, watermark",
                    },
                },
                "8": {
                    "class_type": "VAEDecode",
                    "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                },
                "9": {
                    "class_type": "SaveImage",
                    "inputs": {"filename_prefix": "AxiomAI", "images": ["8", 0]},
                },
            }

        seed = random.randint(1, 1000000000)

        # Dynamic configuration replacement
        for _, node_data in list(workflow.items()):
            if not isinstance(node_data, dict):
                continue

            class_type = node_data.get("class_type", "")
            inputs = node_data.get("inputs", {})
            if not isinstance(inputs, dict):
                continue

            if class_type == "KSampler":
                inputs["seed"] = seed
                inputs["steps"] = self.config.image_steps
                inputs["cfg"] = self.config.image_cfg_scale

            elif class_type == "EmptyLatentImage":
                inputs["width"] = self.config.image_width
                inputs["height"] = self.config.image_height

            elif class_type == "CLIPTextEncode":
                text = inputs.get("text", "")
                if isinstance(text, str):
                    if "{prompt}" in text or "[prompt]" in text:
                        text = text.replace("{prompt}", prompt).replace("[prompt]", prompt)
                        inputs["text"] = text
                    elif "{negative_prompt}" in text or "[negative_prompt]" in text:
                        neg = "blurry, low quality, distorted, extra limbs, bad anatomy, text, watermark"
                        text = text.replace("{negative_prompt}", neg).replace("[negative_prompt]", neg)
                        inputs["text"] = text

        # Fallback replacement if no placeholders were in the workflow text
        clip_nodes = []
        for _, node_data in list(workflow.items()):
            if isinstance(node_data, dict) and node_data.get("class_type") == "CLIPTextEncode":
                inputs = node_data.get("inputs", {})
                if isinstance(inputs, dict) and "text" in inputs:
                    if prompt in inputs["text"]:
                        continue
                    clip_nodes.append(node_data)

        if clip_nodes:
            first_inputs = clip_nodes[0].get("inputs", {})
            first_inputs["text"] = prompt

            if len(clip_nodes) > 1:
                second_inputs = clip_nodes[1].get("inputs", {})
                second_inputs["text"] = "blurry, low quality, distorted, extra limbs, bad anatomy, text, watermark"

        # No install actually has the exact checkpoint file a workflow names
        # (the default template ships the classic SD1.5 name): ask the server
        # what it has and substitute any missing checkpoint with its first one.
        ckpt_nodes = [
            node for node in workflow.values()
            if isinstance(node, dict)
            and node.get("class_type") == "CheckpointLoaderSimple"
            and isinstance(node.get("inputs"), dict)
        ]
        if ckpt_nodes and base_url:
            available = self._comfyui_available_checkpoints(base_url)
            if available:
                for node in ckpt_nodes:
                    current = node["inputs"].get("ckpt_name")
                    if current not in available:
                        logger.info(
                            f"ComfyUI checkpoint '{current}' is not installed on "
                            f"the server: using '{available[0]}' instead."
                        )
                        node["inputs"]["ckpt_name"] = available[0]

        return workflow
