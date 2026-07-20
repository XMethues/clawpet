import tempfile
import unittest
from pathlib import Path

from clawchat_pet.runtime import ClawchatPetRuntime


class FakePetdex:
    def __init__(self, sprite: Path):
        self.sprite = sprite
        self.cached = []

    def list_pets(self, force=False):
        return [
            {"slug": "yinyue-2", "displayName": "Yinyue", "source": "petdex", "cached": True},
            {"slug": "boba", "displayName": "Boba", "source": "petdex", "cached": False},
        ]

    def ensure_cached(self, slug):
        self.cached.append(slug)

    def sprite_path(self, slug):
        return self.sprite


class PetIdentityTests(unittest.TestCase):
    def test_production_pet_module_caches_before_persisting_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            sprite = directory / "sprite.png"
            sprite.write_bytes(b"png")
            provider = FakePetdex(sprite)
            runtime = ClawchatPetRuntime(directory, pet_provider=provider)

            selected = runtime.command({"type": "select_pet", "pet_id": "boba"})

            self.assertEqual(["boba"], provider.cached)
            self.assertEqual("boba", selected["pet"]["slug"])
            self.assertEqual("/assets/pets/boba.png", selected["pet"]["spriteUrl"])
            self.assertEqual(sprite, runtime.pet_asset("boba"))

    def test_failed_cache_does_not_commit_the_new_pet(self):
        class FailingPetdex(FakePetdex):
            def ensure_cached(self, slug):
                raise OSError("cache unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            provider = FailingPetdex(directory / "missing.png")
            runtime = ClawchatPetRuntime(directory, pet_provider=provider)

            with self.assertRaisesRegex(OSError, "cache unavailable"):
                runtime.command({"type": "select_pet", "pet_id": "boba"})

            self.assertEqual("yinyue-2", runtime.presentation()["pet"]["slug"])


if __name__ == "__main__":
    unittest.main()
