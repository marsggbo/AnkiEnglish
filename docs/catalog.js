const catalog = document.getElementById("catalog");
const empty = document.getElementById("empty");

function cardFor(episode) {
  const link = document.createElement("a");
  link.className = "catalog-card";
  link.href = episode.url;

  const code = document.createElement("span");
  code.className = "badge";
  code.textContent = episode.episode_code;

  const title = document.createElement("h2");
  title.textContent = episode.show;

  const detail = document.createElement("p");
  detail.textContent = `${episode.card_count} 个词条 · ${episode.source_name || "来源待复核"}`;

  link.append(code, title, detail);
  if (episode.review_required_count) {
    const warning = document.createElement("p");
    warning.className = "warning";
    warning.textContent = `${episode.review_required_count} 项待复核`;
    link.append(warning);
  }
  return link;
}

fetch("catalog.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`目录加载失败：${response.status}`);
    return response.json();
  })
  .then((data) => {
    const episodes = Array.isArray(data.episodes) ? data.episodes : [];
    empty.hidden = episodes.length > 0;
    episodes.forEach((episode) => catalog.append(cardFor(episode)));
  })
  .catch((error) => {
    empty.hidden = false;
    empty.querySelector("h2").textContent = "目录加载失败";
    empty.querySelector("p").textContent = error.message;
  });
