from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

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
        self.assertEqual(context.exception.status_code, 403)
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

    def test_recent_playtime_sorts_games_without_being_published(self) -> None:
        responses = iter(
            [
                {
                    "response": {
                        "players": [
                            {"personaname": "Example", "avatarfull": "avatar.jpg"}
                        ]
                    }
                },
                {
                    "response": {
                        "games": [
                            {
                                "appid": 1,
                                "playtime_2weeks": 10,
                                "playtime_forever": 100,
                            },
                            {
                                "appid": 2,
                                "playtime_2weeks": 20,
                                "playtime_forever": 200,
                            },
                        ]
                    }
                },
                {"game": {}},
                {"game": {}},
            ]
        )

        def fetcher(url: str, request_name: str) -> dict[str, object]:
            return next(responses)

        profiles = steam_games.build_profiles(["123"], "secret", fetcher)

        self.assertEqual([game["appid"] for game in profiles[0]["games"]], [2, 1])
        self.assertTrue(
            all("playtime_2weeks" not in game for game in profiles[0]["games"])
        )

    def test_achievement_snapshot_is_derived_and_shared_data_is_cached(self) -> None:
        request_counts: dict[str, int] = {}

        def fetcher(url: str, request_name: str) -> dict[str, object]:
            path = urlparse(url).path
            query = parse_qs(urlparse(url).query)
            request_counts[path] = request_counts.get(path, 0) + 1

            if "GetPlayerSummaries" in path:
                steam_id = query["steamids"][0]
                return {
                    "response": {
                        "players": [
                            {
                                "personaname": f"Player {steam_id}",
                                "avatarfull": "avatar.jpg",
                            }
                        ]
                    }
                }
            if "GetRecentlyPlayedGames" in path:
                return {
                    "response": {
                        "games": [
                            {
                                "appid": 10,
                                "playtime_2weeks": 30,
                                "playtime_forever": 120,
                            }
                        ]
                    }
                }
            if "GetSchemaForGame" in path:
                return {
                    "game": {
                        "availableGameStats": {
                            "achievements": [
                                {"name": "FIRST", "displayName": "First Steps"},
                                {"name": "RARE", "displayName": "Rare Find"},
                                {"name": "LOCKED", "displayName": "Still Locked"},
                            ]
                        }
                    }
                }
            if "GetPlayerAchievements" in path:
                return {
                    "playerstats": {
                        "success": True,
                        "achievements": [
                            {
                                "apiname": "FIRST",
                                "achieved": 1,
                                "unlocktime": 1_000,
                            },
                            {
                                "apiname": "RARE",
                                "achieved": 1,
                                "unlocktime": 2_000,
                            },
                            {
                                "apiname": "LOCKED",
                                "achieved": 0,
                                "unlocktime": 0,
                            },
                        ],
                    }
                }
            if "GetGlobalAchievementPercentagesForApp" in path:
                return {
                    "achievementpercentages": {
                        "achievements": [
                            {"name": "FIRST", "percent": 75.5},
                            {"name": "RARE", "percent": 4.25},
                            {"name": "LOCKED", "percent": 1.0},
                        ]
                    }
                }
            self.fail(f"Unexpected request: {request_name}")

        profiles = steam_games.build_profiles(["123", "456"], "secret", fetcher)

        expected_snapshot = {
            "unlocked": 2,
            "total": 3,
            "rarest_unlocked": {"name": "Rare Find", "percent": 4.25},
            "latest_unlock": {
                "name": "Rare Find",
                "unlocked_at": "1970-01-01T00:33:20Z",
            },
        }
        self.assertEqual(profiles[0]["games"][0]["achievements"], expected_snapshot)
        self.assertEqual(profiles[1]["games"][0]["achievements"], expected_snapshot)

        schema_path = "/ISteamUserStats/GetSchemaForGame/v2/"
        percentages_path = (
            "/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"
        )
        player_achievements_path = "/ISteamUserStats/GetPlayerAchievements/v1/"
        self.assertEqual(request_counts[schema_path], 1)
        self.assertEqual(request_counts[percentages_path], 1)
        self.assertEqual(request_counts[player_achievements_path], 2)

    def test_forbidden_player_achievements_omit_only_the_snapshot(self) -> None:
        def fetcher(url: str, request_name: str) -> dict[str, object]:
            path = urlparse(url).path

            if "GetPlayerSummaries" in path:
                return {
                    "response": {
                        "players": [
                            {"personaname": "Example", "avatarfull": "avatar.jpg"}
                        ]
                    }
                }
            if "GetRecentlyPlayedGames" in path:
                return {
                    "response": {
                        "games": [
                            {
                                "appid": 1_867_240,
                                "playtime_2weeks": 30,
                                "playtime_forever": 120,
                            }
                        ]
                    }
                }
            if "GetSchemaForGame" in path:
                return {
                    "game": {
                        "availableGameStats": {
                            "achievements": [
                                {"name": "ACHIEVEMENT", "displayName": "Achievement"}
                            ]
                        }
                    }
                }
            if "GetPlayerAchievements" in path:
                raise steam_games.SteamRequestError(
                    "Steam player achievements failed with HTTP 403.",
                    status_code=403,
                )
            self.fail(f"Unexpected request: {request_name}")

        profiles = steam_games.build_profiles(["123"], "secret", fetcher)

        self.assertEqual(
            profiles[0]["games"],
            [{"appid": 1_867_240, "playtime_forever": 120}],
        )


if __name__ == "__main__":
    unittest.main()
