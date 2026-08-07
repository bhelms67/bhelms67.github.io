const recentGamesUrl = 'https://raw.githubusercontent.com/bhelms67/bhelms67.github.io/master/assets/data/recent-games.json';
const embeds = document.getElementById('steamdb-embeds');
const profile = document.getElementById('steam-profile');

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

  if (Number.isFinite(game.playtime_2weeks)) {
    const playtime = document.createElement('p');
    playtime.className = 'steam-game-playtime';
    playtime.textContent = `Time played: ${formatPlaytime(game.playtime_2weeks)}`;
    gameContainer.appendChild(playtime);
  }

  const iframe = document.createElement('iframe');
  iframe.src = `https://steamdb.info/embed/?appid=${game.appid}`;
  iframe.height = '389';
  iframe.style.cssText = 'border:0;overflow:hidden;width:75%';
  iframe.loading = 'lazy';
  gameContainer.appendChild(iframe);

  embeds.appendChild(gameContainer);
}

async function loadRecentGames() {
  const response = await fetch(recentGamesUrl);
  const data = await response.json();
  const games = data.games || (data.appids || []).map((appid) => ({ appid }));

  addProfile(data.player || {});

  if (games.length === 0) {
    embeds.textContent = 'No Steam playtime has been recorded for the last two weeks.';
    return;
  }

  games.slice(0, 5).forEach(addGame);
}

loadRecentGames().catch(() => {
  embeds.textContent = 'Unable to load recent Steam games.';
});
