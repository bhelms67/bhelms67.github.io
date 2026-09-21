#!/usr/bin/env python3
"""Generate the public recent Steam games payload for the Pages artifact."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

OUTPUT_PATH = Path("assets/data/recent-games.json")
MAX_ATTEMPTS = 4
BASE_RETRY_DELAY_SECONDS = 2
TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

JsonObject = dict[str, Any]
OpenUrl = Callable[..., Any]
Sleep = Callable[[float], None]
FetchJson = Callable[[str, str], JsonObject]
AchievementCatalog = dict[str, JsonObject]


class SteamRequestError(RuntimeError):
    """Raised when Steam data cannot be fetched safely."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _retry_delay(
    error: HTTPError | URLError | TimeoutError | json.JSONDecodeError,
    attempt: int,
) -> float:
    if isinstance(error, HTTPError):
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after and retry_after.isdecimal():
            return min(float(retry_after), 60.0)

    return float(BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))


def _safe_error_summary(error: HTTPError | URLError | TimeoutError | json.JSONDecodeError) -> str:
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, json.JSONDecodeError):
        return "invalid JSON response"
    if isinstance(error, TimeoutError):
        return "request timed out"
    return "network error"


def fetch_json(
    url: str,
    request_name: str,
    *,
    opener: OpenUrl = urlopen,
    sleeper: Sleep = time.sleep,
) -> JsonObject:
    """Fetch JSON, retrying errors that are likely to be temporary."""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with opener(url, timeout=30) as response:
                data = json.load(response)
            if not isinstance(data, dict):
                raise SteamRequestError(f"{request_name} returned an unexpected JSON value.")
            return data
        except HTTPError as error:
            if error.code not in TRANSIENT_HTTP_STATUS_CODES:
                raise SteamRequestError(
                    f"{request_name} failed with HTTP {error.code}.",
                    status_code=error.code,
                ) from None
            transient_error: HTTPError | URLError | TimeoutError | json.JSONDecodeError = error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            transient_error = error

        summary = _safe_error_summary(transient_error)
        if attempt == MAX_ATTEMPTS:
            raise SteamRequestError(
                f"{request_name} failed after {MAX_ATTEMPTS} attempts ({summary})."
            ) from None

        delay = _retry_delay(transient_error, attempt)
        print(
            f"Warning: {request_name} failed ({summary}); "
            f"retrying in {delay:g} seconds ({attempt}/{MAX_ATTEMPTS}).",
            file=sys.stderr,
        )
        sleeper(delay)

    raise AssertionError("Retry loop exited unexpectedly.")


def load_configuration(environ: Mapping[str, str]) -> tuple[str, list[str]]:
    api_key = environ.get("STEAM_API_KEY", "").strip()
    steam_ids_json = environ.get("STEAM_IDS", "").strip()

    missing_secrets = [
        name
        for name, value in (("STEAM_API_KEY", api_key), ("STEAM_IDS", steam_ids_json))
        if not value
    ]
    if missing_secrets:
        raise ValueError(f"Missing required secret(s): {', '.join(missing_secrets)}.")

    try:
        steam_ids = json.loads(steam_ids_json)
    except json.JSONDecodeError as error:
        raise ValueError("STEAM_IDS must be a JSON array of Steam IDs.") from error

    if not isinstance(steam_ids, list) or not all(
        isinstance(steam_id, str) and steam_id.strip() for steam_id in steam_ids
    ):
        raise ValueError("STEAM_IDS must be a JSON array of non-empty Steam ID strings.")

    return api_key, [steam_id.strip() for steam_id in steam_ids]


def resolve_steam_id(profile_identifier: str, api_key: str, fetcher: FetchJson) -> str:
    if profile_identifier.isdecimal():
        return profile_identifier

    vanity_query = urlencode(
        {"key": api_key, "vanityurl": profile_identifier, "format": "json"}
    )
    vanity_url = (
        "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
        f"?{vanity_query}"
    )
    vanity_data = fetcher(vanity_url, "Steam vanity-name lookup").get("response", {})
    steam_id = vanity_data.get("steamid")
    if vanity_data.get("success") != 1 or not isinstance(steam_id, str):
        raise SteamRequestError("Steam could not resolve a configured vanity profile name.")
    return steam_id


def _achievement_name(achievement: JsonObject, catalog: AchievementCatalog) -> str:
    api_name = achievement.get("apiname")
    if not isinstance(api_name, str):
        return "Unknown achievement"

    schema_achievement = catalog.get(api_name, {})
    display_name = schema_achievement.get("displayName")
    if isinstance(display_name, str) and display_name:
        return display_name

    player_name = achievement.get("name")
    return player_name if isinstance(player_name, str) and player_name else api_name


def _unlock_timestamp(unlock_time: object) -> str | None:
    if not isinstance(unlock_time, (int, float)) or isinstance(unlock_time, bool):
        return None
    if unlock_time <= 0:
        return None

    try:
        unlocked_at = datetime.fromtimestamp(unlock_time, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return unlocked_at.isoformat().replace("+00:00", "Z")


def fetch_achievement_catalog(
    app_id: int,
    api_key: str,
    fetcher: FetchJson,
    catalog_cache: dict[int, AchievementCatalog],
) -> AchievementCatalog:
    if app_id in catalog_cache:
        return catalog_cache[app_id]

    schema_query = urlencode(
        {"key": api_key, "appid": app_id, "l": "english", "format": "json"}
    )
    schema_url = (
        "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
        f"?{schema_query}"
    )
    schema_data = fetcher(schema_url, f"Steam achievement schema for app {app_id}")
    schema_achievements = (
        schema_data.get("game", {})
        .get("availableGameStats", {})
        .get("achievements", [])
    )
    if not isinstance(schema_achievements, list):
        raise SteamRequestError(
            f"Steam returned an invalid achievement schema for app {app_id}."
        )

    catalog = {
        achievement["name"]: achievement
        for achievement in schema_achievements
        if isinstance(achievement, dict)
        and isinstance(achievement.get("name"), str)
    }
    catalog_cache[app_id] = catalog
    return catalog


def fetch_global_achievement_percentages(
    app_id: int,
    fetcher: FetchJson,
    percentage_cache: dict[int, dict[str, float]],
) -> dict[str, float]:
    if app_id in percentage_cache:
        return percentage_cache[app_id]

    percentage_query = urlencode({"gameid": app_id, "format": "json"})
    percentage_url = (
        "https://api.steampowered.com/ISteamUserStats/"
        "GetGlobalAchievementPercentagesForApp/v2/"
        f"?{percentage_query}"
    )
    percentage_data = fetcher(
        percentage_url,
        f"Steam global achievement percentages for app {app_id}",
    )
    percentage_entries = percentage_data.get("achievementpercentages", {}).get(
        "achievements", []
    )
    if not isinstance(percentage_entries, list):
        raise SteamRequestError(
            f"Steam returned invalid global achievement percentages for app {app_id}."
        )

    percentages = {
        achievement["name"]: float(achievement["percent"])
        for achievement in percentage_entries
        if isinstance(achievement, dict)
        and isinstance(achievement.get("name"), str)
        and isinstance(achievement.get("percent"), (int, float))
        and not isinstance(achievement.get("percent"), bool)
    }
    percentage_cache[app_id] = percentages
    return percentages


def fetch_achievement_snapshot(
    steam_id: str,
    app_id: int,
    api_key: str,
    fetcher: FetchJson,
    catalog_cache: dict[int, AchievementCatalog],
    percentage_cache: dict[int, dict[str, float]],
) -> JsonObject | None:
    catalog = fetch_achievement_catalog(app_id, api_key, fetcher, catalog_cache)
    if not catalog:
        return None

    player_query = urlencode(
        {
            "key": api_key,
            "steamid": steam_id,
            "appid": app_id,
            "l": "english",
            "format": "json",
        }
    )
    player_url = (
        "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
        f"?{player_query}"
    )
    try:
        player_data = fetcher(
            player_url,
            f"Steam player achievements for app {app_id}",
        )
    except SteamRequestError as error:
        if error.status_code != 403:
            raise
        print(
            f"Warning: Steam player achievements are unavailable for app {app_id} "
            "(HTTP 403); omitting its achievement snapshot.",
            file=sys.stderr,
        )
        return None

    player_stats = player_data.get("playerstats", {})
    if player_stats.get("success") is not True:
        return None

    player_achievements = player_stats.get("achievements", [])
    if not isinstance(player_achievements, list):
        raise SteamRequestError(
            f"Steam returned invalid player achievements for app {app_id}."
        )

    unlocked = [
        achievement
        for achievement in player_achievements
        if isinstance(achievement, dict)
        and achievement.get("achieved") == 1
        and achievement.get("apiname") in catalog
    ]
    snapshot: JsonObject = {
        "unlocked": len(unlocked),
        "total": len(catalog),
    }

    if not unlocked:
        return snapshot

    percentages = fetch_global_achievement_percentages(
        app_id,
        fetcher,
        percentage_cache,
    )
    unlocked_with_percentages = [
        (achievement, percentages[achievement["apiname"]])
        for achievement in unlocked
        if achievement.get("apiname") in percentages
    ]
    if unlocked_with_percentages:
        rarest, percent = min(unlocked_with_percentages, key=lambda item: item[1])
        snapshot["rarest_unlocked"] = {
            "name": _achievement_name(rarest, catalog),
            "percent": percent,
        }

    unlocked_with_dates = [
        (achievement, unlocked_at)
        for achievement in unlocked
        if (unlocked_at := _unlock_timestamp(achievement.get("unlocktime")))
    ]
    if unlocked_with_dates:
        latest, unlocked_at = max(unlocked_with_dates, key=lambda item: item[1])
        snapshot["latest_unlock"] = {
            "name": _achievement_name(latest, catalog),
            "unlocked_at": unlocked_at,
        }

    return snapshot


def fetch_profile(
    profile_identifier: str,
    api_key: str,
    fetcher: FetchJson,
    catalog_cache: dict[int, AchievementCatalog],
    percentage_cache: dict[int, dict[str, float]],
) -> JsonObject:
    steam_id = resolve_steam_id(profile_identifier, api_key, fetcher)

    player_query = urlencode({"key": api_key, "steamids": steam_id, "format": "json"})
    player_url = (
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
        f"?{player_query}"
    )
    player_data = fetcher(player_url, "Steam player summary")
    players = player_data.get("response", {}).get("players", [])
    player = players[0] if isinstance(players, list) and players else {}
    if not isinstance(player, dict) or not player.get("personaname"):
        raise SteamRequestError("Steam did not return a public player profile.")

    recent_games_query = urlencode({"key": api_key, "steamid": steam_id, "format": "json"})
    recent_games_url = (
        "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/"
        f"?{recent_games_query}"
    )
    recent_games_data = fetcher(recent_games_url, "Steam recent-games request")
    games = recent_games_data.get("response", {}).get("games", [])
    if not isinstance(games, list):
        raise SteamRequestError("Steam returned an invalid recent-games list.")

    selected_games = sorted(
        games,
        key=lambda game: game.get("playtime_2weeks", 0),
        reverse=True,
    )[:5]
    public_games = []
    for game in selected_games:
        app_id = game["appid"]
        public_game = {
            "appid": app_id,
            "playtime_forever": game.get("playtime_forever", 0),
        }
        achievement_snapshot = fetch_achievement_snapshot(
            steam_id,
            app_id,
            api_key,
            fetcher,
            catalog_cache,
            percentage_cache,
        )
        if achievement_snapshot is not None:
            public_game["achievements"] = achievement_snapshot
        public_games.append(public_game)

    return {
        "player": {
            "name": player["personaname"],
            "avatar": player.get("avatarfull", ""),
        },
        "games": public_games,
    }


def build_profiles(
    profile_identifiers: Sequence[str],
    api_key: str,
    fetcher: FetchJson = fetch_json,
) -> list[JsonObject]:
    profiles = []
    catalog_cache: dict[int, AchievementCatalog] = {}
    percentage_cache: dict[int, dict[str, float]] = {}
    for index, profile_identifier in enumerate(profile_identifiers, start=1):
        try:
            profiles.append(
                fetch_profile(
                    profile_identifier,
                    api_key,
                    fetcher,
                    catalog_cache,
                    percentage_cache,
                )
            )
        except (KeyError, TypeError, AttributeError, SteamRequestError) as error:
            raise SteamRequestError(
                f"Configured Steam profile #{index} could not be refreshed: {error}"
            ) from None

    if profile_identifiers and not profiles:
        raise SteamRequestError(
            "Refusing to replace configured Steam profiles with an empty result."
        )
    return profiles


def write_payload(output_path: Path, profiles: Sequence[JsonObject]) -> None:
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "profiles": profiles,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, indent=2)
        file.write("\n")


def run(
    environ: Mapping[str, str],
    output_path: Path = OUTPUT_PATH,
    fetcher: FetchJson = fetch_json,
) -> None:
    api_key, profile_identifiers = load_configuration(environ)
    profiles = build_profiles(profile_identifiers, api_key, fetcher)
    write_payload(output_path, profiles)


if __name__ == "__main__":
    run(os.environ)
