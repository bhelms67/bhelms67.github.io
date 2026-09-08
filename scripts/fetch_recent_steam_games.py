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


class SteamRequestError(RuntimeError):
    """Raised when Steam data cannot be fetched safely."""


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
                    f"{request_name} failed with HTTP {error.code}."
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


def fetch_profile(profile_identifier: str, api_key: str, fetcher: FetchJson) -> JsonObject:
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

    return {
        "player": {
            "name": player["personaname"],
            "avatar": player.get("avatarfull", ""),
        },
        "games": [
            {
                "appid": game["appid"],
                "playtime_2weeks": game.get("playtime_2weeks", 0),
                "playtime_forever": game.get("playtime_forever", 0),
            }
            for game in sorted(
                games,
                key=lambda game: game.get("playtime_2weeks", 0),
                reverse=True,
            )[:5]
        ],
    }


def build_profiles(
    profile_identifiers: Sequence[str],
    api_key: str,
    fetcher: FetchJson = fetch_json,
) -> list[JsonObject]:
    profiles = []
    for index, profile_identifier in enumerate(profile_identifiers, start=1):
        try:
            profiles.append(fetch_profile(profile_identifier, api_key, fetcher))
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
