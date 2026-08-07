const topGamesUrl = 'https://raw.githubusercontent.com/bhelms67/bhelms67.github.io/master/top-games.json';
const embeds = document.getElementById('steamdb-embeds');

async function loadTopGames() {
  const response = await fetch(topGamesUrl);
  const appids = await response.json();

  appids.slice(0, 5).forEach((appid) => {
    const iframe = document.createElement('iframe');
    iframe.src = `https://steamdb.info/embed/?appid=${appid}`;
    iframe.height = '389';
    iframe.style.cssText = 'border:0;overflow:hidden;width:100%';
    iframe.loading = 'lazy';
    embeds.appendChild(iframe);
  });
}

loadTopGames().catch(() => {
  embeds.textContent = 'Unable to load the current top Steam games.';
});
