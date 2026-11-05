const FSRS_URL = "https://esm.sh/ts-fsrs@6.0.0";
const DAY_MS = 86_400_000;

const elements = Object.fromEntries([
  "deck-title", "eyebrow", "due-count", "learned-count", "scheduler-badge",
  "review-panel", "empty-panel", "level", "category", "review-status", "term",
  "ipa", "scene-sentence", "reveal-button", "answer", "definition",
  "scene-translation", "everyday-example", "everyday-translation", "notes",
  "source-name", "source-link", "notify-button", "export-button", "import-input",
].map((id) => [id, document.getElementById(id)]));

let deck;
let deckId;
let storageKey;
let progress;
let queue = [];
let currentCard = null;
let scheduler = null;
let Rating = null;
let schedulerName = "基础间隔（FSRS 加载失败）";

function localDateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function safeLoad(key) {
  try {
    const stored = JSON.parse(localStorage.getItem(key));
    return stored && stored.version === 1 ? stored : null;
  } catch {
    return null;
  }
}

function saveProgress() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(progress));
  } catch (error) {
    console.warn("无法保存复习进度", error);
  }
}

async function initScheduler() {
  try {
    const module = await import(FSRS_URL);
    Rating = module.Rating;
    scheduler = await module.DefaultScheduler({
      version: "FSRS-7",
      desiredRetention: deck.settings.desired_retention,
      enableShortTerm: true,
      learningSteps: ["1m", "10m"],
      relearningSteps: ["10m"],
      enableFuzz: true,
      maximumInterval: 36_500,
    });
    schedulerName = `FSRS-7 · 目标记忆率 ${Math.round(deck.settings.desired_retention * 100)}%`;
  } catch (error) {
    console.warn("FSRS 模块加载失败，使用基础间隔", error);
  }
  elements["scheduler-badge"].textContent = schedulerName;
}

function ensureCardProgress(card) {
  if (!progress.cards[card.id]) {
    progress.cards[card.id] = {
      introducedAt: new Date().toISOString(),
      introducedOn: localDateKey(),
      events: [],
    };
    saveProgress();
  }
  return progress.cards[card.id];
}

function fallbackNextInterval(grade, previousDays) {
  if (grade === "Again") return 10 / 1440;
  if (grade === "Hard") return Math.max(1, previousDays * 1.2 || 1);
  if (grade === "Easy") return Math.max(3, previousDays * 2.8 || 3);
  return Math.max(1, previousDays * 2.2 || 1);
}

function fallbackState(cardProgress) {
  const events = cardProgress.events;
  if (!events.length) return { due: new Date(cardProgress.introducedAt), intervalDays: 0 };
  const last = events[events.length - 1];
  const intervalDays = Number(last.intervalDays || 0);
  return { due: new Date(new Date(last.at).getTime() + intervalDays * DAY_MS), intervalDays };
}

async function materialize(cardProgress) {
  if (!scheduler) return fallbackState(cardProgress);
  let state = scheduler.newCard({ now: new Date(cardProgress.introducedAt) });
  for (const event of [...cardProgress.events].sort((a, b) => a.at.localeCompare(b.at))) {
    const grade = Rating[event.grade];
    if (grade === undefined) continue;
    state = scheduler.review({ card: state, grade, now: new Date(event.at) }).card;
  }
  return state;
}

async function buildQueue() {
  const now = new Date();
  const due = [];
  const unseen = [];
  for (const card of deck.cards) {
    const cardProgress = progress.cards[card.id];
    if (!cardProgress) {
      unseen.push(card);
      continue;
    }
    const state = await materialize(cardProgress);
    if (new Date(state.due).getTime() <= now.getTime()) {
      due.push({ card, due: new Date(state.due).getTime() });
    }
  }
  due.sort((a, b) => a.due - b.due);
  const introducedToday = Object.values(progress.cards)
    .filter((item) => item.introducedOn === localDateKey()).length;
  const newSlots = Math.max(0, deck.settings.daily_new_limit - introducedToday);
  queue = [...due.map((item) => item.card), ...unseen.slice(0, newSlots)];
  updateStats();
}

function updateStats() {
  elements["due-count"].textContent = String(queue.length);
  elements["learned-count"].textContent = String(Object.keys(progress.cards).length);
}

function setText(id, value) {
  elements[id].textContent = value || "";
}

function renderCurrent() {
  currentCard = queue[0] || null;
  elements["answer"].hidden = true;
  elements["reveal-button"].hidden = false;
  if (!currentCard) {
    elements["review-panel"].hidden = true;
    elements["empty-panel"].hidden = false;
    updateStats();
    return;
  }

  ensureCardProgress(currentCard);
  elements["review-panel"].hidden = false;
  elements["empty-panel"].hidden = true;
  setText("level", currentCard.level);
  setText("category", `${currentCard.category} · ${currentCard.register}`);
  setText("review-status", currentCard.review_status === "待复核" ? "⚠ 待复核" : "");
  setText("term", currentCard.term);
  setText("ipa", currentCard.ipa);
  setText("scene-sentence", currentCard.scene_sentence);
  setText("definition", currentCard.definition_zh);
  setText("scene-translation", currentCard.scene_translation_zh);
  setText("everyday-example", currentCard.everyday_example);
  setText("everyday-translation", currentCard.everyday_translation_zh);
  setText("notes", currentCard.notes);
  updateStats();
}

async function review(grade) {
  if (!currentCard) return;
  const cardProgress = ensureCardProgress(currentCard);
  const now = new Date();
  let intervalDays = 0;
  if (scheduler) {
    const state = await materialize(cardProgress);
    const result = scheduler.review({ card: state, grade: Rating[grade], now });
    intervalDays = Math.max(0, (new Date(result.card.due).getTime() - now.getTime()) / DAY_MS);
  } else {
    const previous = Number(cardProgress.events.at(-1)?.intervalDays || 0);
    intervalDays = fallbackNextInterval(grade, previous);
  }
  cardProgress.events.push({ grade, at: now.toISOString(), intervalDays });
  saveProgress();
  await buildQueue();
  renderCurrent();
}

function configureSource() {
  setText("source-name", `字幕来源：${deck.metadata.source_name || "待复核"}`);
  try {
    const url = new URL(deck.metadata.source_url);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsupported protocol");
    elements["source-link"].href = url.href;
    elements["source-link"].hidden = false;
  } catch {
    elements["source-link"].hidden = true;
  }
}

function exportProgress() {
  const blob = new Blob([JSON.stringify(progress, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ankienglish-progress-${deckId}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function importProgress(file) {
  const incoming = JSON.parse(await file.text());
  if (incoming.version !== 1 || incoming.deckId !== deckId || typeof incoming.cards !== "object") {
    throw new Error("进度文件与当前学习包不匹配");
  }
  progress = incoming;
  saveProgress();
  await buildQueue();
  renderCurrent();
}

async function enableNotifications() {
  if (!("Notification" in window)) {
    alert("当前浏览器不支持通知。请使用 Anki 获得稳定的每日提醒。");
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission === "granted") {
    new Notification("AnkiEnglish", { body: `当前有 ${queue.length} 张卡片待复习。` });
  }
}

async function init() {
  const response = await fetch("data/cards.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`学习数据加载失败：${response.status}`);
  deck = await response.json();
  deckId = `${deck.metadata.show_slug}-${deck.metadata.episode_code}`;
  storageKey = `ankienglish:v1:${deckId}`;
  progress = safeLoad(storageKey) || { version: 1, deckId, cards: {} };

  setText("deck-title", `${deck.metadata.show} ${deck.metadata.episode_code}`);
  setText("eyebrow", `${deck.cards.length} 个词条 · 每日最多 ${deck.settings.daily_new_limit} 张新卡`);
  document.title = `${deck.metadata.show} ${deck.metadata.episode_code} · AnkiEnglish`;
  configureSource();
  await initScheduler();
  await buildQueue();
  renderCurrent();

  elements["reveal-button"].addEventListener("click", () => {
    elements["answer"].hidden = false;
    elements["reveal-button"].hidden = true;
  });
  document.querySelectorAll("[data-grade]").forEach((button) => {
    button.addEventListener("click", () => review(button.dataset.grade));
  });
  elements["notify-button"].addEventListener("click", enableNotifications);
  elements["export-button"].addEventListener("click", exportProgress);
  elements["import-input"].addEventListener("change", async (event) => {
    try {
      if (event.target.files[0]) await importProgress(event.target.files[0]);
    } catch (error) {
      alert(error.message);
    } finally {
      event.target.value = "";
    }
  });
}

init().catch((error) => {
  console.error(error);
  elements["deck-title"].textContent = "学习包加载失败";
  elements["eyebrow"].textContent = error.message;
  elements["empty-panel"].hidden = false;
});
