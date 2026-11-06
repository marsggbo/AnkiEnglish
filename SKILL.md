---
name: AnkiEnglish
description: 从英美剧单集或公开视频字幕中筛选 50 个 B2-C1 词汇与短语，生成可导入 Anki 的 CSV、带 FSRS 复习和可选 TTS 听力模式的静态网页，并在用户授权后同步到 GitHub Pages。用户提到 AnkiEnglish、追剧学英语、剧集词汇、series vocab、某部剧第几季第几集、从视频生成 Anki 时使用。仅处理用户有权访问的公开字幕或用户提供的字幕，不绕过 DRM、登录、付费墙或验证码。
---

# AnkiEnglish

把一集剧的字幕转成一套可核查、可导入 Anki、可发布到 GitHub Pages 的英语学习材料。

## 不可违反的原则

1. 剧中原句必须来自本集字幕。运行 `build_pack.py` 验证；匹配失败时标记 `待复核`，不得改写成“看起来像原句”的句子。
2. IPA、词义或自拟日常例句没有可靠把握时，在 `review_status` 和对应字段中标记 `待复核`，不得编造。
3. 只发布筛选出的短句，不上传整集字幕或视频。
4. 不绕过 DRM、登录、付费墙、地域限制或验证码。拿不到合法字幕时请用户提供 SRT/VTT/TXT。
5. GitHub 仓库写入和公开 Pages 会产生外部副作用。首次执行前展示仓库名、公开范围和将要推送的文件，并取得一次明确授权。后续仅在配置 `auto_publish=true` 时自动推送。
6. GitHub Pages 是静态托管。网页关闭时无法可靠主动推送通知；每日提醒交给 Anki/AnkiMobile/AnkiDroid，网页仅在打开时显示到期卡并可触发浏览器通知。

## 输入格式

最简输入：

```text
AnkiEnglish Friends S02E03
```

也接受：

```text
AnkiEnglish 剧名="Friends" season=2 episode=3
AnkiEnglish https://公开视频地址 剧名="Friends" S02E03
AnkiEnglish 字幕=/absolute/path/Friends.S02E03.en.srt 剧名="Friends" S02E03
```

解析字段：

- `show`：剧名，必填。
- `season`、`episode`：正整数，统一格式化成 `SxxEyy`。
- `video_url`：可选，只能抓取公开可访问字幕。
- `subtitle_path`：可选，用户提供时优先使用。
- `count`：默认且推荐 50。用户明确要求其他数量时才改变。

剧名、季数或集数不明确时先询问，不猜测。

## 首次配置

配置保存在 `~/.config/ankienglish/config.json`，不要写在 Skill 目录，避免 Skill 更新覆盖个人设置。可从 `config.example.json` 复制。缺少配置时依次询问：

1. 本地产出目录，默认 `~/Documents/AnkiEnglish`。
2. 母语，默认 `zh-CN`。
3. GitHub 仓库，例如 `marsggbo/ankienglish-data`。允许暂不配置。
4. 是否允许创建公开仓库并启用 Pages。
5. `auto_publish` 是否开启。默认关闭。
6. 每日新卡上限，默认 10；FSRS 目标记忆率，默认 0.90。

不要收集或写入 GitHub token。使用用户已有的 `gh auth`。

## 执行流程

### 1. 确定字幕来源

按以下优先级，找到可靠正文后停止：

1. 用户提供的 `.srt`、`.vtt` 或 `.txt`。
2. 用户提供的公开视频链接：使用平台允许的字幕接口或 `yt-dlp --write-subs --write-auto-subs --skip-download`；优先人工字幕，记录是否为自动字幕。
3. Springfield Springfield：适合较老剧集。slug 规则为小写、空格转 `-`、删除非字母数字和连字符、合并连续连字符。
4. SubsLikeScript：先搜索剧集页，再从剧集页定位带标题的 season/episode URL，不直接猜 URL。
5. 通用 Web 搜索和可信剧集 Wiki transcript。
6. 全部失败时请用户提供字幕文件，不继续猜。

Springfield 请求示例：

```bash
curl -sL "https://r.jina.ai/https://www.springfieldspringfield.co.uk/view_episode_scripts.php?tv-show={slug}&episode=s02e03"
```

SubsLikeScript 每一步都通过 `r.jina.ai`：搜索页 → 剧集页 → 单集页。搜索失败时去掉 `The`、标点或改用独特关键词，并检查同名剧年份。

来源验收：

- 页面标题、剧名、季集必须一致。
- 正文应有大量连续对话，而不是导航链接、剧情简介或另一集内容。
- 保存 `source_url`、`source_name`、`retrieved_at`、`source_confidence`。
- 自动字幕、同名剧无法完全确认或只有二手转载时，`source_confidence` 写 `待复核`。

### 2. 清洗字幕

在临时目录保存原字幕，不把原字幕复制进发布目录。运行：

```bash
python3 {skill_dir}/scripts/clean_subtitles.py INPUT \
  --output CLEANED.txt \
  --report CLEANED.report.json
```

脚本删除 SRT/VTT 序号、时间轴、格式标签、纯舞台提示和连续重复字幕，保留一行一个对白片段。阅读报告，确认清洗后仍有足够正文。正文过短或疑似错误页面时停止。

### 3. 筛选 50 个词或短语

优先级：

1. 短语动词。
2. 习语、固定搭配和高迁移性句型。
3. 常见口语和俚语。
4. B2-C1 的日常实用词。

排除：

- A1-B1 基础词，除非它在固定表达中产生新含义。
- 极低频专业名词、角色名、地名、品牌名。
- 只用于本集笑点或剧情设定、难以迁移到日常表达的内容。
- 冒犯性表达，除非学习价值明确；此时增加语域/风险说明。
- 重复词条、同一原句的重复卡片。

覆盖建议：短语动词和固定搭配不少于一半；B2 与 C1 均有覆盖；不要为了凑满 50 个降低质量。合格项不足 50 时，输出实际数量并解释，不添加虚构或低价值条目。

### 4. 生成中间 JSON

写入 `entries.json`：

```json
{
  "metadata": {
    "show": "Friends",
    "season": 2,
    "episode": 3,
    "source_name": "Springfield Springfield",
    "source_url": "https://...",
    "source_confidence": "已核验",
    "retrieved_at": "2026-11-04T12:00:00Z",
    "native_language": "zh-CN"
  },
  "cards": [
    {
      "term": "pull off",
      "ipa": "/pʊl ɒf/",
      "definition_zh": "成功完成困难的事情",
      "scene_sentence": "How did you pull that off?",
      "scene_translation_zh": "你是怎么做到的？",
      "everyday_example": "She pulled off the presentation without any notes.",
      "everyday_translation_zh": "她没看笔记就顺利完成了演讲。",
      "level": "B2",
      "category": "phrasal verb",
      "register": "neutral",
      "review_status": "已核验",
      "notes": ""
    }
  ]
}
```

字段规则：

- `term`：词、短语或固定搭配。
- `ipa`：可靠词典音标；短语可以给整体读音。无法确认写 `待复核`。
- `definition_zh`：该原句语境中的中文解释。
- `scene_sentence`：字幕中的完整原句，不自行改写。
- `scene_translation_zh`：忠于语境的中文译句。
- `everyday_example`：自然、可替换到日常场景的自拟例句，不冒充剧中原句。
- `everyday_translation_zh`：日常例句翻译。
- `level`：只允许 `B2`、`C1` 或 `待复核`。
- `category`：`phrasal verb`、`idiom`、`collocation`、`slang`、`word`、`sentence pattern`。
- `register`：如 `neutral`、`informal`、`formal`、`offensive`。
- `review_status`：`已核验` 或 `待复核`。

### 5. 校验并构建学习包

```bash
python3 {skill_dir}/scripts/build_pack.py \
  --input entries.json \
  --transcript CLEANED.txt \
  --output-dir "{output_dir}/{show_slug}/{SxxEyy}" \
  --templates "{skill_dir}/templates" \
  --expected-count 50 \
  --daily-new-limit 10 \
  --desired-retention 0.90
```

输出：

- `cards.csv`：完整字段，适合表格检查。
- `anki-{show_slug}-{SxxEyy}.csv`：Anki Basic 笔记，正面为词条和剧中原句，背面为释义、音标、译文和日常例句。
- `cards.json`：网页数据。
- `manifest.json`：来源、数量、校验警告和构建参数。
- `site/`：可独立打开或部署的网页，内含可下载的完整 CSV、Anki CSV 和 manifest。

`build_pack.py` 会用归一化后的文本检查每个 `scene_sentence`。未匹配、缺字段、等级异常时写入 `manifest.json` 并把条目标成 `待复核`。不要隐藏警告。

### 6. 人工检查门

发布前汇报：

- 字幕来源和可信度。
- 词条数量与 B2/C1、类别分布。
- `待复核` 条目数量及原因。
- 本地输出路径。
- 即将写入的 GitHub 仓库与公开 URL。

首次发布、目标仓库变化或将创建公开仓库时必须再次取得授权。

### 7. 发布 GitHub Pages

确认 `gh auth status` 成功后执行：

```bash
python3 {skill_dir}/scripts/publish_github.py \
  --pack-dir "{output_dir}/{show_slug}/{SxxEyy}" \
  --repo "OWNER/REPO" \
  --branch main \
  --confirm-publish
```

仓库不存在时，只有用户明确同意创建公开仓库，才加：

```text
--create-public
```

发布器只增量更新 `docs/episodes/{show_slug}/{SxxEyy}/`、`docs/catalog.json` 和站点壳，不强推、不改 Git 配置、不删除其他剧集。它将 Pages 配置为从 `main:/docs` 发布，并返回公网 URL。

### 8. 复习、听力模式与每日提醒

网页采用固定版本的 `ts-fsrs` 和 FSRS-7，默认目标记忆率 0.90。复习记录保存在当前浏览器的 `localStorage`，网页提供进度导入/导出，换浏览器前应先导出。

默认使用纯文字模式，按 `显示解释 → Again / Hard / Good / Easy` 复习。用户可随时开启听力模式；选择会保存在浏览器中，也可以切回纯文字模式。听力模式使用免费的浏览器 Web Speech API，不需要 API key，并优先选择设备上的高质量本地英文声音。流程必须是：

1. 隐藏词条、音标、原句和解释，只播放剧中英文原句。允许正常速度重听、慢速重听和选择英文声音。
2. 用户选择 `听懂了，但不知道意思`、`听懂了，而且知道意思` 或 `没听懂`。
3. 显示词条、音标和剧中原句，不立即显示中文解释。
4. 用户点击 `显示解释` 后，显示释义、翻译和日常例句。
5. 用户点击 `完成本卡并继续`，再写入复习记录并进入下一张卡。

听力答案映射到 FSRS：

- `听懂了，但不知道意思` → `Hard`
- `听懂了，而且知道意思` → `Good`
- `没听懂` → `Again`

复习事件额外记录 `mode=listening` 和 `listeningAnswer`，便于导出后分析听力表现。TTS 不支持或播放被浏览器限制时，明确提示用户点击重播或切换到文字模式，不能让复习流程卡死。

提醒用户：

- 网页打开时会自动展示今日到期卡，可授权浏览器通知。
- TTS 音质和可用声音由浏览器及操作系统决定；网页不上传待朗读文本，也不捆绑大型语音模型。
- GitHub Pages 关闭时不能可靠后台推送。
- 要获得稳定的每日提醒，应导入 Anki，并在 Anki 中启用 FSRS 与系统通知。
- 网页和 Anki 各自维护调度状态；导入 CSV 后不会自动双向同步复习记录。

## 输出字段

`cards.csv` 字段顺序：

```text
id,show,episode,term,ipa,definition_zh,scene_sentence,scene_translation_zh,everyday_example,everyday_translation_zh,level,category,register,review_status,source_name,source_url
```

Anki CSV 使用 `#separator:Comma`、`#html:true`、`#notetype:Basic`、`#deck:AnkiEnglish::{show}`、`#columns:Front,Back,Tags` 和 `#tags column:3`。文件不添加普通表头行。

## 完成回复格式

```text
✅ AnkiEnglish 已完成 {show} {SxxEyy}

字幕来源：{source_name}（{source_confidence}）
词条：{count}，其中待复核 {review_count}
本地 CSV：{cards_csv}
Anki CSV：{anki_csv}
网页：{pages_url 或“未发布”}

说明：网页到期复习使用 FSRS-7；稳定的每日系统提醒请使用 Anki。
```

## 失败处理

- 字幕找不到：请求用户上传字幕，不继续生成。
- 字幕与季集不符：停止并说明证据。
- 合格词不足 50：输出实际数量并说明原因。
- GitHub 未登录：保留本地产物，提示运行 `gh auth login`，不要求用户在聊天中提供 token。
- 推送冲突或分支保护：停止并保留临时克隆路径，不使用强推。
- Pages API 失败：报告仓库已推送但 Pages 未启用，不声称公网可访问。
