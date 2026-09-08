from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_recent_steam_games as steam_games


class FetchRecentSteamGamesTests(unittest.TestCase):
    def test_missing_required_secret_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "STEAM_API_KEY"):
            steam_games.load_configuration({"STEAM_IDS": "[]"})

    def test_explicit_empty_profile_list_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "recent-games.json"
            steam_games.run(
                {"STEAM_API_KEY": "secret", "STEAM_IDS": "[]"},
                output_path,
            )

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["profiles"], [])
        self.assertIn("generatedAt", payload)

    def test_transient_request_is_retried(self) -> None:
        attempts = 0
        delays: list[float] = []

        def opener(url: str, timeout: int) -> io.BytesIO:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise HTTPError(url, 503, "Unavailable", {}, None)
            return io.BytesIO(b'{"response": {}}')

        result = steam_games.fetch_json(
            "https://example.invalid/?key=secret",
            "test request",
            opener=opener,
            sleeper=delays.append,
        )

        self.assertEqual(result, {"response": {}})
        self.assertEqual(attempts, 2)
        self.assertEqual(delays, [2.0])

    def test_non_transient_http_error_is_not_retried(self) -> None:
        attempts = 0

        def opener(url: str, timeout: int) -> io.BytesIO:
            nonlocal attempts
            attempts += 1
            raise HTTPError(url, 403, "Forbidden", {}, None)

        with self.assertRaisesRegex(steam_games.SteamRequestError, "HTTP 403") as context:
            steam_games.fetch_json(
                "https://example.invalid/?key=must-not-appear",
                "test request",
                opener=opener,
                sleeper=lambda _: None,
            )

        self.assertEqual(attempts, 1)
        self.assertNotIn("must-not-appear", str(context.exception))

    def test_profile_failure_does_not_overwrite_existing_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "recent-games.json"
            original_payload = '{"profiles": [{"existing": true}]}\n'
            output_path.write_text(original_payload, encoding="utf-8")

            def failing_fetcher(url: str, request_name: str) -> dict[str, object]:
                raise steam_games.SteamRequestError("temporary failure")

            with self.assertRaises(steam_games.SteamRequestError):
                steam_games.run(
                    {"STEAM_API_KEY": "secret", "STEAM_IDS": '["123"]'},
                    output_path,
                    failing_fetcher,
                )

            self.assertEqual(output_path.read_text(encoding="utf-8"), original_payload)

    def test_successful_empty_games_response_replaces_old_games(self) -> None:
        responses = iter(
            [
                {
                    "response": {
                        "players": [
                            {"personaname": "Example", "avatarfull": "avatar.jpg"}
                        ]
                    }
                },
                {"response": {}},
            ]
        )

        def fetcher(url: str, request_name: str) -> dict[str, object]:
            return next(responses)

        profiles = steam_games.build_profiles(["123"], "secret", fetcher)

        self.assertEqual(profiles[0]["games"], [])


if __name__ == "__main__":
    unittest.main()
