"""
tests/test_image_generator.py

Unit tests for the Axiom AI image generation system.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from axiom.config import AppConfig
from axiom.image_generator import ImageGenerator, MOCK_PNG_BASE64
from axiom.backends.base import LLMResponse, LLMBackend
from axiom.session import Session
from axiom.schema import create_universe_db
from axiom.db_helpers import create_new_save


class _FakeLLM(LLMBackend):
    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.calls: list[list[dict]] = []

    def complete(self, messages: list[dict], **kwargs) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            narrative_text=self.response_text,
            tool_call=None,
            finish_reason="stop",
        )

    def stream_tokens(self, messages: list[dict], **kwargs):
        yield self.response_text

    def is_available(self) -> bool:
        return True


def test_image_generator_prompt_generation() -> None:
    cfg = AppConfig()
    llm = _FakeLLM(response_text="a wizard casting a spell, digital art")
    img_gen = ImageGenerator(cfg, llm=llm)

    prompt = img_gen.generate_prompt(
        narrative_text="The wizard waves his wand. ![wizard image](wizard.jpg)",
        location_desc="A dark cavern with glowing crystals",
        character_desc="Wizard: old man in blue robes",
        game_state_tag="combat",
    )

    assert prompt == "a wizard casting a spell, digital art"
    assert len(llm.calls) == 1

    call_msg = llm.calls[0][1]["content"]
    assert "The wizard waves his wand." in call_msg
    assert "![wizard image]" not in call_msg
    assert "A dark cavern with glowing crystals" in call_msg
    assert "Wizard: old man in blue robes" in call_msg
    assert "combat" in call_msg


def test_image_generator_mock_backend(tmp_path: Path) -> None:
    cfg = AppConfig(image_backend="mock")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("test prompt", tmp_path, "test_mock.png")
    assert save_path is not None
    assert Path(save_path).exists()
    assert Path(save_path).read_bytes() == base64.b64decode(MOCK_PNG_BASE64)


@patch("requests.post")
def test_image_generator_stable_diffusion_backend_success(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    fake_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"images": [fake_base64]}
    mock_post.return_value = mock_resp

    cfg = AppConfig(
        image_backend="stable_diffusion",
        image_api_url="http://fake-sd-server:7860",
    )
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("digital fantasy art", tmp_path, "sd_out.png")
    assert save_path is not None
    assert Path(save_path).exists()
    assert Path(save_path).read_bytes() == base64.b64decode(fake_base64)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://fake-sd-server:7860/sdapi/v1/txt2img"
    assert kwargs["json"]["prompt"] == "digital fantasy art"


@patch("requests.post")
def test_image_generator_stable_diffusion_backend_failure_falls_back_to_mock(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = Exception("HTTP 500 Server Error")
    mock_post.return_value = mock_resp

    cfg = AppConfig(image_backend="stable_diffusion")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("digital fantasy art", tmp_path, "sd_fail.png")
    assert save_path is not None
    assert Path(save_path).exists()
    assert Path(save_path).read_bytes() == base64.b64decode(MOCK_PNG_BASE64)


@patch("requests.get")
@patch("requests.post")
def test_image_generator_comfyui_backend_success(
    mock_post: MagicMock, mock_get: MagicMock, tmp_path: Path
) -> None:
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"prompt_id": "comfy-prompt-uuid-123"}
    mock_post.return_value = mock_post_resp

    mock_get_hist = MagicMock()
    mock_get_hist.status_code = 200
    mock_get_hist.json.return_value = {
        "comfy-prompt-uuid-123": {
            "outputs": {
                "9": {
                    "images": [
                        {"filename": "out_file.png", "subfolder": "", "type": "output"}
                    ]
                }
            }
        }
    }

    mock_get_view = MagicMock()
    mock_get_view.status_code = 200
    mock_get_view.content = base64.b64decode(MOCK_PNG_BASE64)

    mock_get.side_effect = [mock_get_hist, mock_get_view]

    cfg = AppConfig(
        image_backend="comfyui", image_api_url="http://fake-comfy-server:8188"
    )
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("comfyui art", tmp_path, "comfy_out.png")
    assert save_path is not None
    assert Path(save_path).exists()
    assert Path(save_path).read_bytes() == base64.b64decode(MOCK_PNG_BASE64)

    mock_post.assert_called_once()
    post_args, post_kwargs = mock_post.call_args
    assert post_args[0] == "http://fake-comfy-server:8188/prompt"
    workflow = post_kwargs["json"]["prompt"]
    assert workflow["6"]["inputs"]["text"] == "comfyui art"

    assert mock_get.call_count == 2
    get_calls = mock_get.call_args_list
    assert (
        get_calls[0][0][0]
        == "http://fake-comfy-server:8188/history/comfy-prompt-uuid-123"
    )
    assert (
        get_calls[1][0][0]
        == "http://fake-comfy-server:8188/view?filename=out_file.png&subfolder=&type=output"
    )


@patch("requests.post")
def test_image_generator_comfyui_backend_failure_falls_back_to_mock(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    mock_post.side_effect = Exception("Network connection refused")

    cfg = AppConfig(image_backend="comfyui")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("comfyui art", tmp_path, "comfy_fail.png")
    assert save_path is not None
    assert Path(save_path).exists()
    assert Path(save_path).read_bytes() == base64.b64decode(MOCK_PNG_BASE64)


class _DummyVectorMemory:
    def query(self, *args, **kwargs) -> list:
        return []

    def embed_chunk(self, *args, **kwargs) -> str:
        return "mock-chunk-id"


def test_session_integration_image_generation(tmp_path: Path) -> None:
    db_path = str(tmp_path / "world.axiom")
    create_universe_db(db_path)
    save_id = create_new_save(db_path, player_name="Hero", difficulty="Normal")

    cfg = AppConfig(image_generation_enabled=True, image_backend="mock")

    with patch("axiom.config.load_config", return_value=cfg):
        llm = _FakeLLM(response_text="The scene description.")
        sess = Session(
            db_path,
            save_id,
            llm=llm,
            vector_memory=_DummyVectorMemory(),
            data_dir=tmp_path,
        )

        result = sess.take_turn("Hello world")

        assert result.image_path is not None
        assert Path(result.image_path).exists()
        assert Path(result.image_path).name == "turn_1.png"
