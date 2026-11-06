const FSRS_URL = "https://esm.sh/ts-fsrs@6.0.0";
const DAY_MS = 86_400_000;
const MODE_KEY = "ankienglish:study-mode";
const VOICE_KEY = "ankienglish:voice-uri";
const LISTENING_LABELS = {
  heard_no_meaning: "听懂了，但不知道意思",
  heard_and_understood: "听懂了，而且知道意思",
  not_understood: "没听懂",
};

const elements = Object.fromEntries([
  "deck-title", "eyebrow", "due-count", "learned-count", "scheduler-badge",
  "review-panel", "empty-panel", "card-content", "card-meta", "level", "category",
  "review-status", "term", "ipa", "scene-sentence", "reveal-button", "answer",
  "definition", "scene-translation", "everyday-example", "everyday-translation",
  "notes", "source-name", "source-link", "notify-button", "export-button",
  "import-input", "mode-toggle", "listening-prompt", "tts-status", "audio-orb",
  "replay-button", "slow-replay-button", "voice-select", "text-panel", "text-step",
  "answer-step", "listening-result", "text-ratings", "listening-complete",
].map((id) => [id, document.getElementById(id)]));

function readPreference(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writePreference(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    console.warn("无法保存网页偏好", error);
  }
}

let deck;
let deckId;
let storageKey;
let progress;
let queue = [];
let currentCard = null;
let scheduler = null;
let Rating = null;
let schedulerName = "基础间隔（FSRS 加载失败）";
let studyMode = readPreference(MODE_KEY) === "listening" ? "listening" : "text";
let englishVoices = [];
let pendingListeningGrade = null;
let pendingListeningAnswer = null;
const ttsSupported = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

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

function voiceScore(voice) {
  let score = voice.localService ? 100 : 0;
  if (/premium|enhanced|natural|neural/i.test(voice.name)) score += 80;
  if (/samantha|ava|zoe|daniel|karen|moira|jenny|aria|serena|google us english/i.test(voice.name)) score += 60;
  if (/^en-US/i.test(voice.lang)) score += 20;
  else if (/^en-GB/i.test(voice.lang)) score += 15;
  if (voice.default) score += 5;
  return score;
}

function loadVoices() {
  if (!ttsSupported) return;
  const selectedUri = readPreference(VOICE_KEY);
  englishVoices = window.speechSynthesis.getVoices()
    .filter((voice) => /^en[-_]/i.test(voice.lang))
    .sort((a, b) => voiceScore(b) - voiceScore(a) || a.name.localeCompare(b.name));

  elements["voice-select"].replaceChildren();
  if (!englishVoices.length) {
    const option = new Option("浏览器默认英文声音", "");
    elements["voice-select"].add(option);
    return;
  }
  for (const voice of englishVoices) {
    const locality = voice.localService ? "本地" : "浏览器";
    const option = new Option(`${voice.name} · ${voice.lang} · ${locality}`, voice.voiceURI);
    elements["voice-select"].add(option);
  }
  const selected = englishVoices.find((voice) => voice.voiceURI === selectedUri) || englishVoices[0];
  elements["voice-select"].value = selected.voiceURI;
}

function selectedVoice() {
  return englishVoices.find((voice) => voice.voiceURI === elements["voice-select"].value) || englishVoices[0] || null;
}

function cancelSpeech() {
  if (!ttsSupported) return;
  window.speechSynthesis.cancel();
  elements["audio-orb"].classList.remove("speaking");
}

function speakCurrent(rate = 0.95) {
  if (!currentCard || studyMode !== "listening") return;
  if (!ttsSupported) {
    setText("tts-status", "当前浏览器不支持语音合成，请切换到文字模式");
    return;
  }

  cancelSpeech();
  const utterance = new SpeechSynthesisUtterance(currentCard.scene_sentence);
  const voice = selectedVoice();
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang;
  } else {
    utterance.lang = "en-US";
  }
  utterance.rate = rate;
  utterance.pitch = 1;
  utterance.volume = 1;
  utterance.onstart = () => {
    setText("tts-status", rate < 0.9 ? "正在慢速播放…" : "正在播放…");
    elements["audio-orb"].classList.add("speaking");
  };
  utterance.onend = () => {
    setText("tts-status", "播放结束，可以重听或选择理解程度");
    elements["audio-orb"].classList.remove("speaking");
  };
  utterance.onerror = (event) => {
    if (event.error === "canceled" || event.error === "interrupted") return;
    setText("tts-status", "自动播放被浏览器阻止，请点“再听一遍”");
    elements["audio-orb"].classList.remove("speaking");
  };
  window.speechSynthesis.speak(utterance);
}

function updateModeControl() {
  const listening = studyMode === "listening";
  elements["mode-toggle"].textContent = listening ? "切换到文字模式" : "开启听力模式";
  elements["mode-toggle"].setAttribute("aria-pressed", String(listening));
  elements["mode-toggle"].classList.toggle("active", listening);
  if (!ttsSupported) {
    elements["mode-toggle"].disabled = true;
    elements["mode-toggle"].textContent = "浏览器不支持听力模式";
  }
}

function showTextStage(answer, grade) {
  pendingListeningAnswer = answer;
  pendingListeningGrade = grade;
  cancelSpeech();
  elements["listening-prompt"].hidden = true;
  elements["card-content"].hidden = false;
  elements["card-meta"].hidden = false;
  elements["text-panel"].hidden = false;
  elements["text-step"].hidden = false;
  elements["listening-result"].hidden = false;
  setText("listening-result", `你的判断：${LISTENING_LABELS[answer]}`);
  elements["reveal-button"].hidden = false;
  elements["answer"].hidden = true;
}

function revealAnswer() {
  elements["answer"].hidden = false;
  elements["reveal-button"].hidden = true;
  const listening = studyMode === "listening";
  elements["answer-step"].hidden = !listening;
  elements["text-ratings"].hidden = listening;
  elements["listening-complete"].hidden = !listening;
}

function renderCurrent({ autoSpeak = false } = {}) {
  cancelSpeech();
  currentCard = queue[0] || null;
  pendingListeningGrade = null;
  pendingListeningAnswer = null;
  elements["answer"].hidden = true;
  elements["listening-result"].hidden = true;
  elements["text-step"].hidden = true;
  elements["answer-step"].hidden = true;
  elements["text-ratings"].hidden = false;
  elements["listening-complete"].hidden = true;
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

  const listening = studyMode === "listening" && ttsSupported;
  elements["listening-prompt"].hidden = !listening;
  elements["card-content"].hidden = listening;
  elements["card-meta"].hidden = listening;
  elements["text-panel"].hidden = listening;
  elements["reveal-button"].hidden = listening;
  if (listening) {
    setText("tts-status", "准备播放");
    if (autoSpeak) speakCurrent();
  }
  updateStats();
}

async function review(grade, listeningAnswer = null) {
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
  cardProgress.events.push({
    grade,
    at: now.toISOString(),
    intervalDays,
    mode: listeningAnswer ? "listening" : "text",
    ...(listeningAnswer ? { listeningAnswer } : {}),
  });
  saveProgress();
  await buildQueue();
  renderCurrent({ autoSpeak: studyMode === "listening" });
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
  renderCurrent({ autoSpeak: studyMode === "listening" });
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
  updateModeControl();
  if (ttsSupported) {
    loadVoices();
    window.speechSynthesis.addEventListener("voiceschanged", loadVoices);
  }
  await initScheduler();
  await buildQueue();
  renderCurrent({ autoSpeak: studyMode === "listening" });

  elements["mode-toggle"].addEventListener("click", () => {
    studyMode = studyMode === "listening" ? "text" : "listening";
    writePreference(MODE_KEY, studyMode);
    updateModeControl();
    renderCurrent({ autoSpeak: studyMode === "listening" });
  });
  elements["voice-select"].addEventListener("change", () => {
    writePreference(VOICE_KEY, elements["voice-select"].value);
    speakCurrent();
  });
  elements["replay-button"].addEventListener("click", () => speakCurrent());
  elements["slow-replay-button"].addEventListener("click", () => speakCurrent(0.75));
  document.querySelectorAll("[data-listening-grade]").forEach((button) => {
    button.addEventListener("click", () => showTextStage(button.dataset.listeningAnswer, button.dataset.listeningGrade));
  });
  elements["reveal-button"].addEventListener("click", revealAnswer);
  elements["listening-complete"].addEventListener("click", () => {
    if (pendingListeningGrade && pendingListeningAnswer) review(pendingListeningGrade, pendingListeningAnswer);
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
  window.addEventListener("pagehide", cancelSpeech);
}

init().catch((error) => {
  console.error(error);
  elements["deck-title"].textContent = "学习包加载失败";
  elements["eyebrow"].textContent = error.message;
  elements["empty-panel"].hidden = false;
});
