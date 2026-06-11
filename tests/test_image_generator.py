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
    # Le timeout vient de la config (30s en dur ne suffisait pas en local)
    assert kwargs["timeout"] == AppConfig().image_timeout


@patch("requests.post")
def test_image_generator_stable_diffusion_404_means_api_disabled(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    """WebUI lancé sans --api → 404 sur /sdapi : None, sans lever ni écrire."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_post.return_value = mock_resp

    cfg = AppConfig(image_backend="stable_diffusion")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("digital fantasy art", tmp_path, "sd_404.png")
    assert save_path is None
    assert not (tmp_path / "sd_404.png").exists()
    # raise_for_status ne doit pas être le chemin emprunté pour le 404
    mock_resp.raise_for_status.assert_not_called()


@patch("requests.post")
def test_image_generator_stable_diffusion_custom_timeout(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    fake_base64 = MOCK_PNG_BASE64.decode()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"images": [fake_base64]}
    mock_post.return_value = mock_resp

    cfg = AppConfig(image_backend="stable_diffusion", image_timeout=300)
    img_gen = ImageGenerator(cfg)

    assert img_gen.generate_image("art", tmp_path, "sd_to.png") is not None
    assert mock_post.call_args.kwargs["timeout"] == 300


@patch("requests.post")
def test_image_generator_stable_diffusion_backend_failure_returns_none(
    mock_post: MagicMock, tmp_path: Path
) -> None:
    """TICKET-045 : un backend réel en échec ne produit AUCUNE image (pas de mock 1×1)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = Exception("HTTP 500 Server Error")
    mock_post.return_value = mock_resp

    cfg = AppConfig(image_backend="stable_diffusion")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("digital fantasy art", tmp_path, "sd_fail.png")
    assert save_path is None
    assert not (tmp_path / "sd_fail.png").exists()


@patch("requests.get")
@patch("requests.post")
def test_image_generator_comfyui_backend_success(
    mock_post: MagicMock, mock_get: MagicMock, tmp_path: Path
) -> None:
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"prompt_id": "comfy-prompt-uuid-123"}
    mock_post.return_value = mock_post_resp

    mock_get_objinfo = MagicMock()
    mock_get_objinfo.status_code = 200
    mock_get_objinfo.json.return_value = {
        "CheckpointLoaderSimple": {
            "input": {"required": {"ckpt_name": [["ilustmix_v111.safetensors"]]}}
        }
    }

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

    mock_get.side_effect = [mock_get_objinfo, mock_get_hist, mock_get_view]

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
    # Le checkpoint en dur du template a été remplacé par celui du serveur,
    # et VAEDecode utilise bien l'entrée "samples" attendue par ComfyUI.
    assert workflow["4"]["inputs"]["ckpt_name"] == "ilustmix_v111.safetensors"
    assert workflow["8"]["inputs"]["samples"] == ["3", 0]

    assert mock_get.call_count == 3
    get_calls = mock_get.call_args_list
    assert (
        get_calls[0][0][0]
        == "http://fake-comfy-server:8188/object_info/CheckpointLoaderSimple"
    )
    assert (
        get_calls[1][0][0]
        == "http://fake-comfy-server:8188/history/comfy-prompt-uuid-123"
    )
    assert (
        get_calls[2][0][0]
        == "http://fake-comfy-server:8188/view?filename=out_file.png&subfolder=&type=output"
    )


@patch("time.sleep")
@patch("requests.get")
@patch("requests.post")
def test_image_generator_comfyui_polling_respects_timeout(
    mock_post: MagicMock, mock_get: MagicMock, mock_sleep: MagicMock, tmp_path: Path
) -> None:
    """Le polling ComfyUI s'arrête après ~image_timeout secondes (1 poll/s)."""
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"prompt_id": "never-finishes"}
    mock_post.return_value = mock_post_resp

    mock_get_hist = MagicMock()
    mock_get_hist.status_code = 200
    mock_get_hist.json.return_value = {}  # jamais prêt
    mock_get.return_value = mock_get_hist

    cfg = AppConfig(image_backend="comfyui", image_timeout=25)
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("comfyui art", tmp_path, "comfy_to.png")
    assert save_path is None
    history_polls = [
        c for c in mock_get.call_args_list if "/history/" in c[0][0]
    ]
    assert len(history_polls) == 25


@patch("requests.get")
@patch("requests.post")
def test_image_generator_comfyui_backend_failure_returns_none(
    mock_post: MagicMock, mock_get: MagicMock, tmp_path: Path
) -> None:
    """TICKET-045 : ComfyUI injoignable → None, rien d'écrit sur disque."""
    mock_post.side_effect = Exception("Network connection refused")
    mock_get.side_effect = Exception("Network connection refused")

    cfg = AppConfig(image_backend="comfyui")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("comfyui art", tmp_path, "comfy_fail.png")
    assert save_path is None
    assert not (tmp_path / "comfy_fail.png").exists()


@patch("requests.get")
@patch("requests.post")
def test_image_generator_comfyui_checkpoint_listing_failure_keeps_workflow(
    mock_post: MagicMock, mock_get: MagicMock, tmp_path: Path
) -> None:
    """/object_info injoignable → le workflow part tel quel (pas de crash)."""
    mock_get.side_effect = Exception("Network connection refused")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {}  # pas de prompt_id → arrêt propre
    mock_post.return_value = mock_post_resp

    cfg = AppConfig(image_backend="comfyui")
    img_gen = ImageGenerator(cfg)

    assert img_gen.generate_image("art", tmp_path, "comfy_ckpt.png") is None
    workflow = mock_post.call_args.kwargs["json"]["prompt"]
    assert workflow["4"]["inputs"]["ckpt_name"] == "v1-5-pruned-emaonly.ckpt"


@patch("requests.get")
@patch("requests.post")
def test_image_generator_comfyui_validation_error_returns_none(
    mock_post: MagicMock, mock_get: MagicMock, tmp_path: Path
) -> None:
    """Workflow rejeté par ComfyUI (400 validation) → None, pas d'exception."""
    mock_get.side_effect = Exception("no object_info")

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 400
    mock_post_resp.json.return_value = {
        "error": {"message": "Prompt outputs failed validation"},
        "node_errors": {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "errors": [
                    {
                        "message": "Value not in list",
                        "details": "ckpt_name: 'v1-5-pruned-emaonly.ckpt'",
                    }
                ],
            }
        },
    }
    mock_post.return_value = mock_post_resp

    cfg = AppConfig(image_backend="comfyui")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("art", tmp_path, "comfy_400.png")
    assert save_path is None
    assert not (tmp_path / "comfy_400.png").exists()


def _fake_gemini_response(parts: list) -> object:
    """Build a minimal GenerateContentResponse-like object."""
    from types import SimpleNamespace

    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))]
    )


@patch("axiom.backends.gemini.genai.Client")
def test_image_generator_gemini_backend_success(
    mock_client_cls: MagicMock, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    png_bytes = base64.b64decode(MOCK_PNG_BASE64)
    parts = [
        SimpleNamespace(inline_data=None, text="Here is your image."),
        SimpleNamespace(inline_data=SimpleNamespace(data=png_bytes)),
    ]
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _fake_gemini_response(parts)
    mock_client_cls.return_value = mock_client

    cfg = AppConfig(
        image_backend="gemini",
        gemini_api_key="fake-key",
        image_width=1024,
        image_height=576,
    )
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("gemini art", tmp_path, "gemini_out.png")
    assert save_path is not None
    assert Path(save_path).read_bytes() == png_bytes

    mock_client_cls.assert_called_once_with(api_key="fake-key")
    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs["model"] == "gemini-2.5-flash-image"
    assert kwargs["contents"] == "gemini art"
    assert list(kwargs["config"].response_modalities) == ["TEXT", "IMAGE"]
    # 1024x576 → ratio supporté le plus proche = 16:9
    assert kwargs["config"].image_config.aspect_ratio == "16:9"


@patch("axiom.backends.gemini.genai.Client")
def test_image_generator_gemini_no_api_key_returns_none(
    mock_client_cls: MagicMock, tmp_path: Path
) -> None:
    cfg = AppConfig(image_backend="gemini", gemini_api_key="")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("gemini art", tmp_path, "gemini_nokey.png")
    assert save_path is None
    assert not (tmp_path / "gemini_nokey.png").exists()
    mock_client_cls.assert_not_called()


@patch("axiom.backends.gemini.genai.Client")
def test_image_generator_gemini_failure_returns_none(
    mock_client_cls: MagicMock, tmp_path: Path
) -> None:
    """TICKET-045 : échec API Gemini → None, rien d'écrit sur disque."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API blew up")
    mock_client_cls.return_value = mock_client

    cfg = AppConfig(image_backend="gemini", gemini_api_key="fake-key")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("gemini art", tmp_path, "gemini_fail.png")
    assert save_path is None
    assert not (tmp_path / "gemini_fail.png").exists()


@patch("axiom.backends.gemini.genai.Client")
def test_image_generator_gemini_no_image_part_returns_none(
    mock_client_cls: MagicMock, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    parts = [SimpleNamespace(inline_data=None, text="No image, sorry.")]
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _fake_gemini_response(parts)
    mock_client_cls.return_value = mock_client

    cfg = AppConfig(image_backend="gemini", gemini_api_key="fake-key")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("gemini art", tmp_path, "gemini_nopart.png")
    assert save_path is None
    assert not (tmp_path / "gemini_nopart.png").exists()


def test_closest_aspect_ratio_mapping() -> None:
    from axiom.image_generator import closest_aspect_ratio

    assert closest_aspect_ratio(512, 512) == "1:1"
    assert closest_aspect_ratio(1024, 576) == "16:9"
    assert closest_aspect_ratio(768, 1024) == "3:4"
    assert closest_aspect_ratio(576, 1024) == "9:16"
    assert closest_aspect_ratio(2100, 900) == "21:9"
    assert closest_aspect_ratio(0, 0) == "1:1"


def test_image_generator_unknown_backend_returns_none(tmp_path: Path) -> None:
    """TICKET-045 : backend inconnu → None (le mock est réservé au backend 'mock')."""
    cfg = AppConfig(image_backend="dall-e-imaginaire")
    img_gen = ImageGenerator(cfg)

    save_path = img_gen.generate_image("any prompt", tmp_path, "unknown.png")
    assert save_path is None
    assert not (tmp_path / "unknown.png").exists()


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
