const recentGamesUrl = 'https://raw.githubusercontent.com/bhelms67/bhelms67.github.io/master/assets/data/recent-games.json';
const embeds = document.getElementById('steamdb-embeds');
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

function addGame(game) {
  const gameContainer = document.createElement('div');
  gameContainer.className = 'steam-game';

  const playtime = document.createElement('div');
  playtime.className = 'steam-game-playtime';

  const playtimeHeading = document.createElement('p');
  playtimeHeading.textContent = 'Time played:';
  playtime.appendChild(playtimeHeading);

  const playtimeDetails = document.createElement('div');
  playtimeDetails.className = 'steam-game-playtime-details';

  if (Number.isFinite(game.playtime_2weeks)) {
    const recentPlaytime = document.createElement('div');
    recentPlaytime.textContent = `Last 2 weeks - ${formatPlaytime(game.playtime_2weeks)}`;
    playtimeDetails.appendChild(recentPlaytime);
  }

  if (Number.isFinite(game.playtime_forever)) {
    const totalPlaytime = document.createElement('div');
    totalPlaytime.textContent = `All time - ${formatPlaytime(game.playtime_forever)}`;
    playtimeDetails.appendChild(totalPlaytime);
  }

  if (playtimeDetails.childElementCount > 0) {
    playtime.appendChild(playtimeDetails);
    gameContainer.appendChild(playtime);
  }

  const iframe = document.createElement('iframe');
  iframe.src = `https://steamdb.info/embed/?appid=${game.appid}`;
  iframe.height = '389';
  iframe.style.cssText = 'border:0;overflow:hidden;width:50%';
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
  const data = await response.json();
  const profiles = data.profiles || [];

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
