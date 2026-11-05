# AnkiEnglish

AnkiEnglish 是一个面向 AI Agent 的 Skill：输入剧名、季数和集数后，它获取合法可访问的英文字幕，清洗并筛选约 50 个 B2-C1 词汇或短语，生成审阅 CSV、Anki CSV 和带间隔重复复习的 GitHub Pages 网页。

## 相比参考方案的改进

参考仓库 `gbro-series-vocab` 的有效方法是：按来源优先级寻找字幕，优先短语动词/习语/口语/B2-C1 词汇，只保留剧本中的原句，并输出 Anki CSV。AnkiEnglish 在此基础上增加：

- 可重复执行的字幕清洗与原句校验脚本。
- 完整词条字段：IPA、中文释义、剧中原句、日常替换例句、等级、语域和复核状态。
- 通用 CSV 与 Anki CSV 同源生成。
- GitHub 仓库增量同步与 Pages 自动启用，网页可直接下载完整 CSV 和 Anki CSV。
- 网页端 FSRS-7 到期队列、评分、进度导入导出和页面内通知。
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
│   └── publish_github.py
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
  --repo OWNER/ankienglish-data \
  --confirm-publish \
  --create-public
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
- npm 固定依赖：[ts-fsrs 6.0.0](https://www.npmjs.com/package/ts-fsrs/v/6.0.0)

上述资料内容已为遵守许可限制而重新表述。参考仓库与 `ts-fsrs` 均采用 MIT 许可；本项目没有复制其实现代码。
