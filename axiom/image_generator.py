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
                response = requests.post(url, json=payload, timeout=30)
                response.raise_for_status()

                data = response.json()
                if "images" in data and len(data["images"]) > 0:
                    img_data = base64.b64decode(data["images"][0])
                    save_path.write_bytes(img_data)
                    logger.info(f"Successfully saved SD image to {save_path}")
                    return str(save_path.resolve())
                else:
                    logger.warning("No images returned from SD WebUI API.")
            except Exception as e:
                logger.warning(
                    f"Stable Diffusion image generation failed: {e}. "
                    f"Please verify that Stable Diffusion WebUI is running at {api_url} and started with the --api option."
                )

        elif backend == "comfyui":
            try:
                workflow = self._load_comfyui_workflow(prompt)
                base_url = api_url.rstrip('/')
                prompt_url = f"{base_url}/prompt"

                logger.info(f"Submitting workflow to ComfyUI at {prompt_url}")
                response = requests.post(prompt_url, json={"prompt": workflow}, timeout=10)
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

                for _ in range(60):  # 60 seconds max
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
                    logger.warning("ComfyUI generation timed out or failed.")
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

        logger.warning("Falling back to mock image due to backend selection or generation error.")
        return self._save_mock_image(save_path)

    def _save_mock_image(self, save_path: Path) -> str:
        """Write the mock PNG data to the target path."""
        img_data = base64.b64decode(MOCK_PNG_BASE64)
        save_path.write_bytes(img_data)
        logger.info(f"Successfully saved mock image to {save_path}")
        return str(save_path.resolve())

    def _load_comfyui_workflow(self, prompt: str) -> dict:
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
                    "inputs": {"latent_image": ["3", 0], "vae": ["4", 2]},
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

        return workflow
