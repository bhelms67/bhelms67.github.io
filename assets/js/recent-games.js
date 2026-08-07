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

function addEmbed(appid) {
  const iframe = document.createElement('iframe');
  iframe.src = `https://steamdb.info/embed/?appid=${appid}`;
  iframe.height = '389';
  iframe.style.cssText = 'border:0;overflow:hidden;width:75%';
  iframe.loading = 'lazy';
  embeds.appendChild(iframe);
}

async function loadRecentGames() {
  const response = await fetch(recentGamesUrl);
  const data = await response.json();
  const appids = data.appids || [];

  addProfile(data.player || {});

  if (appids.length === 0) {
    embeds.textContent = 'No Steam playtime has been recorded for the last two weeks.';
    return;
  }

  appids.slice(0, 5).forEach(addEmbed);
}

loadRecentGames().catch(() => {
  embeds.textContent = 'Unable to load recent Steam games.';
});
