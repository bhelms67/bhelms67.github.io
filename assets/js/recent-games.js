const recentGamesUrl = '/assets/data/recent-games.json';
const embeds = document.getElementById('steamdb-embeds');
const freshness = document.getElementById('steam-data-freshness');
const profile = document.getElementById('steam-profile');
const profileSelect = document.getElementById('steam-profile-select');

function addProfile(player) {
  if (!player.name || !player.avatar) {
    return;
  }

  const avatar = document.createElement('img');
  avatar.src = player.avatar;
  avatar.alt = `${player.name}'s Steam avatar`;

  const name = document.createElement('span');
  name.textContent = player.name;

  profile.append(avatar, name);
}

function clearContent(element) {
  element.replaceChildren();
}

function formatPlaytime(minutes) {
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours === 0) {
    return `${minutes}m`;
  }

  return remainingMinutes === 0 ? `${hours}h` : `${hours}h ${remainingMinutes}m`;
}

function showFreshness(generatedAt) {
  const generatedDate = new Date(generatedAt);
  if (Number.isNaN(generatedDate.getTime())) {
    return;
  }

  const formattedDate = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(generatedDate);
  freshness.textContent = `Steam data last refreshed ${formattedDate}.`;
  freshness.hidden = false;
}

function addAchievementSnapshot(game, gameContainer) {
  const achievements = game.achievements;
  if (!achievements
      || !Number.isInteger(achievements.unlocked)
      || !Number.isInteger(achievements.total)) {
    return;
  }

  const snapshot = document.createElement('div');
  snapshot.className = 'steam-achievements';

  const completion = document.createElement('div');
  completion.textContent = `Achievements: ${achievements.unlocked} / ${achievements.total} unlocked`;
  snapshot.appendChild(completion);

  const rarest = achievements.rarest_unlocked;
  if (rarest?.name && Number.isFinite(rarest.percent)) {
    const percentage = new Intl.NumberFormat(undefined, {
      maximumFractionDigits: 2,
    }).format(rarest.percent);
    const rarestAchievement = document.createElement('div');
    rarestAchievement.textContent = `Rarest earned: ${rarest.name} (${percentage}% of players)`;
    snapshot.appendChild(rarestAchievement);
  }

  const latest = achievements.latest_unlock;
  const unlockedAt = new Date(latest?.unlocked_at);
  if (latest?.name && !Number.isNaN(unlockedAt.getTime())) {
    const formattedDate = new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
    }).format(unlockedAt);
    const latestAchievement = document.createElement('div');
    latestAchievement.textContent = `Latest unlock: ${latest.name} (${formattedDate})`;
    snapshot.appendChild(latestAchievement);
  }

  gameContainer.appendChild(snapshot);
}

function addGame(game) {
  const gameContainer = document.createElement('div');
  gameContainer.className = 'steam-game';

  if (Number.isFinite(game.playtime_forever)) {
    const playtime = document.createElement('div');
    playtime.textContent = `All Time Played: ${formatPlaytime(game.playtime_forever)}`;
    gameContainer.appendChild(playtime);
  }

  addAchievementSnapshot(game, gameContainer);

  const iframe = document.createElement('iframe');
  iframe.src = `https://steamdb.info/embed/?appid=${game.appid}`;
  iframe.title = `SteamDB details for Steam app ${game.appid}`;
  iframe.loading = 'lazy';
  gameContainer.appendChild(iframe);

  embeds.appendChild(gameContainer);
}

function showProfile(selectedProfile) {
  clearContent(profile);
  clearContent(embeds);
  addProfile(selectedProfile.player || {});

  const games = selectedProfile.games || [];
  if (games.length === 0) {
    embeds.textContent = 'No Steam playtime has been recorded for the last two weeks.';
    return;
  }

  games.slice(0, 5).forEach(addGame);
}

function addProfileOptions(profiles) {
  clearContent(profileSelect);

  profiles.forEach((steamProfile, index) => {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = steamProfile.player?.name || 'Unknown Steam profile';
    profileSelect.appendChild(option);
  });

  profileSelect.disabled = false;
  profileSelect.addEventListener('change', () => {
    showProfile(profiles[Number(profileSelect.value)]);
  });
}

async function loadRecentGames() {
  const response = await fetch(recentGamesUrl);
  if (!response.ok) {
    throw new Error(`Unable to load recent Steam games (HTTP ${response.status}).`);
  }

  const data = await response.json();
  const profiles = data.profiles || [];
  showFreshness(data.generatedAt);

  if (profiles.length === 0) {
    profileSelect.replaceChildren(new Option('No profiles available'));
    profileSelect.disabled = true;
    embeds.textContent = 'No Steam profiles are configured.';
    return;
  }

  addProfileOptions(profiles);
  showProfile(profiles[0]);
}

loadRecentGames().catch(() => {
  profileSelect.replaceChildren(new Option('Profiles unavailable'));
  profileSelect.disabled = true;
  embeds.textContent = 'Unable to load recent Steam games.';
});
