import json
import unittest
from subprocess import CompletedProcess

from clawchat_pet.publication import (
    HermesLivewareAdapter,
    LivewareAuthenticationRequired,
    LivewarePublication,
)


class InMemoryPublicationAdapter:
    def __init__(self):
        self.logged_in = False
        self.liveware_apps = []
        self.bindings = {}
        self.clawchat_apps = []

    def list_liveware_apps(self):
        if not self.logged_in:
            raise LivewareAuthenticationRequired("liveware login required")
        return list(self.liveware_apps)

    def login_liveware(self):
        self.logged_in = True

    def create_liveware_app(self, name):
        app = {
            "app_id": "app-clawpet",
            "name": name,
            "domain": "app-clawpet.apps.clawling.io",
        }
        self.liveware_apps.append(app)
        return dict(app)

    def bind_liveware_app(self, app_id, upstream):
        self.bindings[app_id] = upstream
        return "https://app-clawpet.apps.clawling.io"

    def list_clawchat_apps(self):
        return list(self.clawchat_apps)

    def register_clawchat_app(self, name, app_id, url):
        self.clawchat_apps.append({
            "name": name,
            "app_id": app_id,
            "url": url,
        })


class LivewarePublicationTests(unittest.TestCase):
    def test_first_start_publishes_one_fixed_clawpet_app(self):
        adapter = InMemoryPublicationAdapter()

        result = LivewarePublication(adapter).ensure()

        self.assertEqual("ClawPet", result.name)
        self.assertEqual("app-clawpet", result.app_id)
        self.assertTrue(adapter.logged_in)
        self.assertEqual(
            [{
                "app_id": "app-clawpet",
                "name": "ClawPet",
                "domain": "app-clawpet.apps.clawling.io",
            }],
            adapter.liveware_apps,
        )
        self.assertEqual(
            {"app-clawpet": "http://127.0.0.1:54321"},
            adapter.bindings,
        )
        self.assertEqual(
            [{
                "name": "ClawPet",
                "app_id": "app-clawpet",
                "url": "https://app-clawpet.apps.clawling.io",
            }],
            adapter.clawchat_apps,
        )

    def test_restart_reuses_the_same_app_and_registration(self):
        adapter = InMemoryPublicationAdapter()
        publication = LivewarePublication(adapter)

        first = publication.ensure()
        second = publication.ensure()

        self.assertEqual(first, second)
        self.assertEqual(1, len(adapter.liveware_apps))
        self.assertEqual(1, len(adapter.clawchat_apps))
        self.assertEqual(
            "http://127.0.0.1:54321",
            adapter.bindings[first.app_id],
        )

    def test_existing_clawpet_app_repairs_a_missing_registration(self):
        adapter = InMemoryPublicationAdapter()
        adapter.logged_in = True
        adapter.liveware_apps.append({
            "app_id": "app-clawpet",
            "name": "ClawPet",
            "domain": "app-clawpet.apps.clawling.io",
        })

        result = LivewarePublication(adapter).ensure()

        self.assertEqual("app-clawpet", result.app_id)
        self.assertEqual(1, len(adapter.liveware_apps))
        self.assertEqual(
            [{
                "name": "ClawPet",
                "app_id": "app-clawpet",
                "url": "https://app-clawpet.apps.clawling.io",
            }],
            adapter.clawchat_apps,
        )

    def test_hermes_adapter_publishes_from_real_cli_and_tool_shapes(self):
        environment = FakeHermesPublicationEnvironment()
        adapter = HermesLivewareAdapter(
            run_cli=environment.run_cli,
            invoke_tool=environment.invoke_tool,
        )

        result = LivewarePublication(adapter).ensure()

        self.assertEqual("app-clawpet", result.app_id)
        self.assertTrue(environment.logged_in)
        self.assertEqual(
            {"app-clawpet": "http://127.0.0.1:54321"},
            environment.bindings,
        )
        self.assertEqual(
            [{
                "name": "ClawPet",
                "app_id": "app-clawpet",
                "url": "https://app-clawpet.apps.clawling.io",
            }],
            environment.clawchat_apps,
        )


class FakeHermesPublicationEnvironment:
    def __init__(self):
        self.logged_in = False
        self.liveware_apps = []
        self.bindings = {}
        self.clawchat_apps = []

    def run_cli(self, args):
        operation = tuple(args[1:])
        if operation == ("app", "list", "--json"):
            if not self.logged_in:
                return CompletedProcess(args, 1, "", "authentication required")
            return CompletedProcess(
                args, 0, json.dumps(self.liveware_apps), ""
            )
        if operation == ("app", "create", "ClawPet"):
            self.liveware_apps.append({
                "appId": "app-clawpet",
                "name": "ClawPet",
                "domain": "app-clawpet.apps.clawling.io",
            })
            return CompletedProcess(args, 0, "appId app-clawpet\n", "")
        if operation == (
            "tunnel",
            "bind",
            "app-clawpet",
            "http://127.0.0.1:54321",
        ):
            self.bindings["app-clawpet"] = "http://127.0.0.1:54321"
            return CompletedProcess(
                args,
                0,
                "domain app-clawpet.apps.clawling.io\n",
                "",
            )
        raise AssertionError(f"unexpected CLI operation: {operation}")

    def invoke_tool(self, name, args):
        if name == "clawchat_liveware_login":
            self.logged_in = True
            return {"ok": True}
        if name == "clawchat_list_apps":
            return {"apps": list(self.clawchat_apps)}
        if name == "clawchat_register_app":
            self.clawchat_apps.append({
                "name": args["name"],
                "app_id": args["appId"],
                "url": args["url"],
            })
            return {"ok": True}
        raise AssertionError(f"unexpected Hermes tool: {name}")


if __name__ == "__main__":
    unittest.main()
