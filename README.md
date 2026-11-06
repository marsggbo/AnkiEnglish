# AnkiEnglish

AnkiEnglish 是一个面向 AI Agent 的 Skill：输入剧名、季数和集数后，它获取合法可访问的英文字幕，清洗并筛选约 50 个 B2-C1 词汇或短语，生成审阅 CSV、Anki CSV 和带间隔重复复习的 GitHub Pages 网页。

## 相比参考方案的改进

参考仓库 `gbro-series-vocab` 的有效方法是：按来源优先级寻找字幕，优先短语动词/习语/口语/B2-C1 词汇，只保留剧本中的原句，并输出 Anki CSV。AnkiEnglish 在此基础上增加：

- 可重复执行的字幕清洗与原句校验脚本。
- 完整词条字段：IPA、中文释义、剧中原句、日常替换例句、等级、语域和复核状态。
- 通用 CSV 与 Anki CSV 同源生成。
- GitHub 仓库增量同步与 Pages 自动启用，网页可直接下载完整 CSV 和 Anki CSV。
- 网页端 FSRS-7 到期队列、评分、进度导入导出和页面内通知。
- 可选 TTS 听力模式：只听原句、判断理解程度、再依次揭示文字和解释；无需 API key。
- 明确的 `待复核` 和版权/技术边界，不用猜测补齐数据。

## 目录

```text
AnkiEnglish/
├── SKILL.md
├── README.md
├── config.example.json
├── scripts/
│   ├── clean_subtitles.py
│   ├── build_pack.py
│   ├── publish_github.py
│   └── refresh_pages.py
└── templates/
    ├── index.html
    ├── app.js
    ├── styles.css
    ├── catalog.html
    └── catalog.js
```

## 使用

安装 Skill 后，在支持 Skill 的 Agent 中输入：

```text
AnkiEnglish Friends S02E03
```

也可直接提供字幕：

```text
AnkiEnglish 字幕=/Users/me/Downloads/Friends.S02E03.en.srt 剧名="Friends" S02E03
```

首次运行会创建 `~/.config/ankienglish/config.json`。发布 GitHub Pages 前需要：

```bash
gh auth login
```

Agent 会在首次公开发布前展示目标仓库和文件范围并请求授权。

## 本地脚本

清洗字幕：

```bash
python3 scripts/clean_subtitles.py episode.srt --output cleaned.txt --report cleaned.report.json
```

根据 Agent 整理的 `entries.json` 构建学习包：

```bash
python3 scripts/build_pack.py \
  --input entries.json \
  --transcript cleaned.txt \
  --output-dir output/friends/S02E03 \
  --templates templates
```

授权后发布：

```bash
python3 scripts/publish_github.py \
  --pack-dir output/friends/S02E03 \
  --repo OWNER/AnkiEnglish \
  --confirm-publish \
  --create-public
```

## 网页听力模式

网页默认使用纯文字模式。点击页面顶部的“开启听力模式”后，每张卡按以下步骤学习：

1. 页面隐藏词条和原句，通过 TTS 播放剧中英文原句。
2. 选择“听懂了，但不知道意思”“听懂了，而且知道意思”或“没听懂”。
3. 页面显示英文词条、音标和原句。
4. 点击“显示解释”，查看中文释义、译文和日常例句。
5. 点击“完成本卡并继续”，系统按对应的 `Hard`、`Good` 或 `Again` 更新 FSRS。

可以正常速度重听、慢速重听和选择设备可用的英文声音。模式和声音偏好保存在浏览器中，随时可以切回文字模式。

TTS 使用浏览器标准 [Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)，免费且不需要 API key。它优先选择设备上的本地高质量英文声音，但具体音质由操作系统和浏览器决定。没有捆绑 Piper、Kokoro 等大型模型，因此首次打开不需要下载数十或数百 MB 的语音权重。

更新网页模板后，可以一次刷新所有已发布剧集：

```bash
python3 scripts/refresh_pages.py --docs-dir docs --templates templates
```

## 网页复习和推送边界

网页使用 FSRS-7 计算到期时间，复习记录留在浏览器 `localStorage`。GitHub Pages 没有后台服务，因此页面关闭后不能可靠地按天主动推送。网页能在打开时显示到期卡并发送浏览器通知。稳定的每日系统提醒应通过导入 Anki 后开启 Anki/AnkiMobile/AnkiDroid 通知实现。

## 隐私与版权

- GitHub Pages 上的内容通常公开。发布前请检查词条、例句和仓库可见性。
- 产物只包含筛选出的学习短句，不发布整集字幕或视频。
- 不绕过 DRM、登录、付费墙、验证码或地域限制。
- 不把 GitHub token 写入配置或网页。

## 资料来源

- 参考方法：[pyang5166/gbro-series-vocab](https://github.com/pyang5166/gbro-series-vocab)
- FSRS 项目：[open-spaced-repetition/fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki)
- JavaScript 实现与接口：[ts-fsrs 文档](https://open-spaced-repetition.github.io/ts-fsrs/guide/)
- Anki 文本导入头：[Anki Manual - Text Files](https://docs.ankiweb.net/importing/text-files.html)
- 浏览器 TTS：[MDN Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- 语音选择接口：[MDN SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis)
- npm 固定依赖：[ts-fsrs 6.0.0](https://www.npmjs.com/package/ts-fsrs/v/6.0.0)

上述资料内容已为遵守许可限制而重新表述。参考仓库与 `ts-fsrs` 均采用 MIT 许可；本项目没有复制其实现代码。
