import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime
from clawchat_pet.server import ServerRunner
from tests.test_runtime_v2 import PETS


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=1) as response:
        return response.status, json.load(response)


def post_json(url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=1) as response:
        return response.status, json.load(response)


class MinimalHTTPAdapterTests(unittest.TestCase):
    def start(self, directory: str):
        runtime_dir = Path(directory)
        sprite = runtime_dir / "sprite.png"
        sprite.write_bytes(b"\x89PNG\r\n\x1a\n")
        pets = [{**pet, "spritePath": str(sprite)} for pet in PETS]
        runtime = ClawchatPetRuntime(runtime_dir, pet_catalog=pets)
        runner = ServerRunner(runtime=runtime, bootstrap=lambda: None)
        runner.start(host="127.0.0.1", port=0)
        return runtime, runner

    def test_adapter_exposes_presentation_catalog_command_asset_and_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            _runtime, runner = self.start(tmp)
            try:
                health_status, health = get_json(runner.base_url + "/healthz")
                presentation_status, presentation = get_json(
                    runner.base_url + "/presentation"
                )
                catalog_status, catalog = get_json(runner.base_url + "/catalog")
                command_status, changed = post_json(runner.base_url + "/command", {
                    "type": "select_scene", "scene_id": "star-voyage"
                })
                with urllib.request.urlopen(
                    runner.base_url + "/assets/pets/yinyue-2.png", timeout=1
                ) as response:
                    asset_status = response.status
                    asset = response.read()
            finally:
                runner.stop()

        self.assertEqual(200, health_status)
        self.assertTrue(health["ok"])
        self.assertEqual(200, presentation_status)
        self.assertEqual("xianxia", presentation["scene"]["id"])
        self.assertEqual(200, catalog_status)
        self.assertEqual("xianxia", catalog["active"]["scene_id"])
        self.assertEqual(200, command_status)
        self.assertEqual("star-voyage", changed["scene"]["id"])
        self.assertEqual((200, b"\x89PNG\r\n\x1a\n"), (asset_status, asset))

    def test_pet_asset_response_uses_the_cached_files_content_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            sprite = runtime_dir / "sprite.webp"
            sprite.write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
            pets = [{**pet, "spritePath": str(sprite)} for pet in PETS]
            runner = ServerRunner(
                runtime=ClawchatPetRuntime(runtime_dir, pet_catalog=pets),
                bootstrap=lambda: None,
            )
            runner.start(host="127.0.0.1", port=0)
            try:
                with urllib.request.urlopen(
                    runner.base_url + "/assets/pets/yinyue-2.png", timeout=1
                ) as response:
                    status = response.status
                    content_type = response.headers["Content-Type"]
                    body = response.read()
            finally:
                runner.stop()

        self.assertEqual(200, status)
        self.assertEqual("image/webp", content_type)
        self.assertEqual(b"RIFF\x00\x00\x00\x00WEBP", body)

    def test_old_http_interfaces_are_not_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            _runtime, runner = self.start(tmp)
            try:
                for path in (
                    "/state",
                    "/cultivation",
                    "/api/v1/experience",
                    "/api/v1/events",
                    "/api/v1/pets",
                    "/api/v1/scenes",
                    "/api/v1/skins",
                ):
                    with self.subTest(path=path):
                        try:
                            if path == "/api/v1/events":
                                post_json(runner.base_url + path, {})
                            else:
                                get_json(runner.base_url + path)
                        except urllib.error.HTTPError as exc:
                            self.assertEqual(404, exc.code)
                        else:
                            self.fail(f"legacy route still exists: {path}")
            finally:
                runner.stop()

    def test_command_validation_uses_400_and_missing_catalog_items_use_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            _runtime, runner = self.start(tmp)
            try:
                with self.assertRaises(urllib.error.HTTPError) as invalid:
                    post_json(runner.base_url + "/command", {"type": "select_scene"})
                with self.assertRaises(urllib.error.HTTPError) as missing:
                    post_json(runner.base_url + "/command", {
                        "type": "select_skin", "skin_id": "missing"
                    })
            finally:
                runner.stop()

        self.assertEqual(400, invalid.exception.code)
        self.assertEqual(404, missing.exception.code)


if __name__ == "__main__":
    unittest.main()
