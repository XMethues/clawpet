import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clawchat_pet.runtime import ClawchatPetRuntime
from clawchat_pet.services import petdex


class PetdexServiceTests(unittest.TestCase):
    def test_manifest_slug_can_serve_the_default_pet_asset(self):
        manifest = {
            "generatedAt": "2026-07-23T00:00:00.000Z",
            "total": 1,
            "pets": [
                {
                    "slug": "yinyue-2",
                    "displayName": "银月",
                    "kind": "creature",
                    "submittedBy": "is_coward",
                    "spritesheetUrl": (
                        "https://assets.petdex.dev/pets/"
                        "yinyue-7b6e2648345b/sprite.webp"
                    ),
                    "petJsonUrl": (
                        "https://assets.petdex.dev/pets/"
                        "yinyue-7b6e2648345b/petjson.json"
                    ),
                    "zipUrl": (
                        "https://assets.petdex.dev/pets/"
                        "yinyue-7b6e2648345b/zip.zip"
                    ),
                }
            ],
        }
        width = 1536
        height = 1872
        vp8x = (
            b"VP8X"
            + (10).to_bytes(4, "little")
            + b"\x10\x00\x00\x00"
            + (width - 1).to_bytes(3, "little")
            + (height - 1).to_bytes(3, "little")
        )
        sprite = (
            b"RIFF"
            + (len(vp8x) + 4).to_bytes(4, "little")
            + b"WEBP"
            + vp8x
        )

        with tempfile.TemporaryDirectory() as tmp:
            hermes_home = Path(tmp)
            cache_root = hermes_home / "clawchat-pet" / "cache"
            cache_root.mkdir(parents=True)
            (cache_root / "petdex-index.json").write_text(
                json.dumps(
                    {
                        "ts": 9_999_999_999,
                        "source": "https://petdex.dev/",
                        "pets": [
                            {
                                "slug": "boba",
                                "displayName": "Boba",
                                "assetUrl": (
                                    "https://assets.petdex.dev/curated/boba/"
                                    "sprite-v2.webp"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fetch = mock.Mock(return_value=json.dumps(manifest))

            def download(_url, destination, timeout=40):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(sprite)

            with (
                mock.patch.object(petdex, "HERMES_HOME", hermes_home),
                mock.patch.object(petdex, "CACHE_ROOT", cache_root),
                mock.patch.object(petdex, "PETS_CACHE", cache_root / "pets"),
                mock.patch.object(
                    petdex, "INDEX_FILE", cache_root / "petdex-index.json"
                ),
                mock.patch.object(petdex, "_fetch_text", fetch),
                mock.patch.object(petdex, "_download", download),
                mock.patch.object(petdex, "_pillow_image", return_value=None),
            ):
                runtime = ClawchatPetRuntime(
                    hermes_home / "clawchat-pet", pet_provider=petdex
                )

                presentation = runtime.presentation()
                asset_path = runtime.pet_asset("yinyue-2")

            self.assertEqual("yinyue-2", presentation["pet"]["slug"])
            self.assertEqual("银月", presentation["pet"]["displayName"])
            self.assertEqual(".webp", asset_path.suffix)
            self.assertEqual(sprite, asset_path.read_bytes())
            fetch.assert_called_once_with(petdex.PETDEX_MANIFEST_URL)


if __name__ == "__main__":
    unittest.main()
