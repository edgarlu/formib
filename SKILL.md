---
name: video-clipper
description: >
  视频智能剪辑工具。支持 YouTube、Twitter/X、Instagram、TikTok 和本地视频。下载视频和字幕，AI 分析生成精细章节（几分钟级别），
  用户选择片段后自动剪辑、翻译字幕为中英双语、烧录字幕到视频，并生成总结文案。
  使用场景：当用户需要剪辑 YouTube/Twitter/Instagram/TikTok 视频、处理本地视频、生成短视频片段、制作双语字幕版本时。
  关键词：视频剪辑、YouTube、Twitter、Instagram、TikTok、本地视频、字幕翻译、双语字幕、视频下载、clip video、剪片
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - AskUserQuestion
model: sonnet
---

# 视频智能剪辑工具

> **Installation**: If you're installing this skill from GitHub, please refer to [README.md](README.md#installation) for installation instructions. The recommended method is `npx skills add https://github.com/op7418/Youtube-clipper-skill`.

## 翻译词表（必须严格遵守）

翻译字幕时，以下术语必须使用指定的中文翻译：

| 英文 | 中文翻译 | 备注 |
|------|----------|------|
| Trump | 川普 | 不用"特朗普" |
| Bessent | 贝森特 | 财政部长 |

**使用说明**：
- 翻译时必须查阅此词表，确保术语一致性
- 用户可通过说"更新剪片词表"来添加或修改词条

---

## 支持的视频来源

- **YouTube**: `https://youtube.com/watch?v=xxx` 或 `https://youtu.be/xxx`
- **Twitter/X**: `https://x.com/user/status/xxx` 或 `https://twitter.com/user/status/xxx`
- **Instagram**: `https://www.instagram.com/p/xxx/` 或 `https://www.instagram.com/reel/xxx/`
- **TikTok**: `https://www.tiktok.com/@user/video/xxx` 或 `https://vm.tiktok.com/xxx`
- **本地视频**: `/path/to/video.mp4`（支持 mp4, mkv, avi, mov, webm 等格式）

## 工作流程

你将按照以下 6 个阶段执行视频剪辑任务：

### 阶段 1: 环境检测

**目标**: 确保所有必需工具和依赖都已安装

1. 检测 yt-dlp 是否可用
   ```bash
   yt-dlp --version
   ```

2. 检测 FFmpeg 版本和 libass 支持
   ```bash
   # 优先检查 ffmpeg-full（macOS）
   /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg -version

   # 检查标准 FFmpeg
   ffmpeg -version

   # 验证 libass 支持（字幕烧录必需）
   ffmpeg -filters 2>&1 | grep subtitles
   ```

3. 检测 Python 依赖
   ```bash
   python3 -c "import yt_dlp; print('✅ yt-dlp available')"
   python3 -c "import pysrt; print('✅ pysrt available')"
   python3 -c "import groq; print('✅ groq available')"
   ```

4. 检测 Groq API Key（字幕转录必需）
   ```bash
   python3 -c "import os; key=os.environ.get('GROQ_API_KEY',''); print('✅ GROQ_API_KEY set' if key else '❌ GROQ_API_KEY not set')"
   ```

**如果环境检测失败**:
- yt-dlp 未安装: 提示 `brew install yt-dlp` 或 `pip install yt-dlp`
- FFmpeg 无 libass: 提示安装 ffmpeg-full
  ```bash
  brew install ffmpeg-full  # macOS
  ```
- Python 依赖缺失: 提示 `pip install pysrt python-dotenv groq`
- GROQ_API_KEY 未设置: 提示用户设置
  ```
  1. 申请免费 Key: https://console.groq.com/keys
  2. 设置: export GROQ_API_KEY='你的key'
  ```

**注意**:
- 标准 Homebrew FFmpeg 不包含 libass，无法烧录字幕
- ffmpeg-full 路径: `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` (Apple Silicon)
- 必须先通过环境检测才能继续

---

### 阶段 2: 下载/处理视频

**目标**: 下载在线视频或处理本地视频文件

1. 获取用户输入（支持五种来源）：
   - YouTube URL: `https://youtube.com/watch?v=xxx`
   - Twitter/X URL: `https://x.com/user/status/xxx`
   - Instagram URL: `https://www.instagram.com/p/xxx/` 或 `https://www.instagram.com/reel/xxx/`
   - TikTok URL: `https://www.tiktok.com/@user/video/xxx` 或 `https://vm.tiktok.com/xxx`
   - 本地文件路径: `/path/to/video.mp4`

2. 调用 download_video.py 脚本
   ```bash
   cd ~/.claude/skills/youtube-clipper
   python3 scripts/download_video.py <source>
   ```

3. 脚本会根据来源类型：
   - **YouTube**: 只下载视频并缩放到 1920x1080（**不下载平台字幕**）
   - **Twitter/X**: 下载视频并缩放到 1920x1080
   - **Instagram**: 下载视频并缩放到 1920x1080
   - **TikTok**: 下载视频并缩放到 1920x1080
   - **本地文件**: 复制到工作目录并缩放到 1920x1080

**视频分辨率**: 所有视频都会自动缩放到 **1920x1080**（保持宽高比，不足部分用黑边填充）

4. **使用 Groq Whisper API 转录字幕（所有来源必须执行此步骤）**

   **重要：绝对不要使用 YouTube 自动字幕或任何平台提供的字幕。** YouTube 自动字幕是"滚动式"格式，每条字幕重复上下两行并夹杂大量 10ms 过渡帧，质量极差，无法直接使用。所有来源统一使用 Groq Whisper API 从音频重新转录，输出干净的 SRT 格式。

   ```bash
   cd ~/.claude/skills/video-clipper
   python3 scripts/transcribe_groq.py <video_path>
   ```

   - Groq Whisper 使用 `whisper-large-v3` 模型，速度极快（比本地 Whisper 快 50 倍以上）
   - 自动提取音频、压缩到 25MB 以内、发送 API 转录
   - 输出干净的 SRT 格式字幕，每条字幕是完整的一句话，时间码精确
   - 将输出的 SRT 文件保存为 `<视频标题>_original.srt`

5. 向用户展示：
   - 视频标题/文件名
   - 视频时长
   - 文件大小
   - 来源类型
   - 转录字幕条数和检测到的语言

**输出目录**: 所有文件保存到 `~/Documents/Claude Code/Convert/<视频标题>/`

**必须保存的文件**:
1. **原片**: `<视频标题>_1080p.mp4` - 缩放到 1080p 的原始视频（无字幕）
2. **原始字幕**: `<视频标题>_original.srt` - Groq Whisper 转录的原语言字幕（带时间码）
3. **中文字幕**: `<视频标题>_chinese.srt` - 翻译后的中文字幕（带时间码）
4. **成品视频**: `<视频标题>_final.mp4` - 烧录中文字幕和水印的最终视频

**Groq API Key 配置**:
- 申请免费 Key: https://console.groq.com/keys
- 设置环境变量: `export GROQ_API_KEY='你的key'`

---

### 阶段 3: 分析章节（核心差异化功能）

**目标**: 使用 Claude AI 分析字幕内容，生成精细章节（2-5 分钟级别）

1. 读取 Groq Whisper 生成的 SRT 字幕文件（`<视频标题>_original.srt`）

2. SRT 字幕数据包含：
   - 完整字幕文本（带时间戳）
   - 每条字幕是完整的一句话（Groq Whisper 输出质量远优于 YouTube 自动字幕）
   - 总时长
   - 字幕条数

3. **你需要执行 AI 分析**（这是最关键的步骤）：
   - 阅读完整字幕内容
   - 理解内容语义和主题转换点
   - 识别自然的话题切换位置
   - 生成 2-5 分钟粒度的章节（避免半小时粗粒度切分）

4. 为每个章节生成：
   - **标题**: 精炼的主题概括（10-20 字）
   - **时间范围**: 起始和结束时间（格式: MM:SS 或 HH:MM:SS）
   - **核心摘要**: 1-2 句话说明这段讲了什么（50-100 字）
   - **关键词**: 3-5 个核心概念词

5. **章节生成原则**：
   - 粒度：每个章节 2-5 分钟（避免太短或太长）
   - 完整性：确保所有视频内容都被覆盖，无遗漏
   - 有意义：每个章节是一个相对独立的话题
   - 自然切分：在主题转换点切分，不要机械地按时间切

6. 向用户展示章节列表：
   ```
   📊 分析完成，生成 X 个章节：

   1. [00:00 - 03:15] AGI 不是时间点，是指数曲线
      核心: AI 模型能力每 4-12 月翻倍，工程师已用 Claude 写代码
      关键词: AGI、指数增长、Claude Code

   2. [03:15 - 06:30] 中国在 AI 上的差距
      核心: 芯片禁运卡住中国，DeepSeek benchmark 优化不代表实力
      关键词: 中国、芯片禁运、DeepSeek

   ... (所有章节)

   ✓ 所有内容已覆盖，无遗漏
   ```

---

### 阶段 4: 用户选择

**目标**: 让用户选择要剪辑的章节和处理选项

1. 使用 AskUserQuestion 工具让用户选择章节
   - 提供章节编号供用户选择
   - 支持多选（可以选择多个章节）

2. 询问处理选项：
   - 是否生成双语字幕？（英文 + 中文）
   - 是否烧录字幕到视频？（硬字幕）
   - 是否生成总结文案？

3. 确认用户选择并展示处理计划

---

### 阶段 5: 剪辑处理（核心执行阶段）

**目标**: 并行执行多个处理任务

对于每个用户选择的章节，执行以下步骤：

#### 5.1 剪辑视频片段
```bash
python3 scripts/clip_video.py <video_path> <start_time> <end_time> <output_path>
```
- 使用 FFmpeg 精确剪辑
- 保持原始视频质量
- 输出: `<章节标题>_clip.mp4`

#### 5.2 提取字幕片段
- 从完整字幕中过滤出该时间段的字幕
- 调整时间戳（减去起始时间，从 00:00:00 开始）
- 转换为 SRT 格式
- 输出: `<章节标题>_original.srt`

#### 5.3 翻译字幕（使用 Groq LLM API）
```bash
cd ~/.claude/skills/video-clipper
python3 scripts/translate_subtitles.py <srt_file> <chinese_output> [bilingual_output] [batch_size]
```
- **使用 Groq LLM API 翻译**（`llama-3.3-70b-versatile` 模型），需要 `GROQ_API_KEY`
- **批量翻译优化**: 每批 20 条字幕一起发送给 LLM，带重试机制（最多 3 次）
- **翻译词表**: 脚本内置默认词表（Trump=川普 等），也支持同目录 `glossary.json` 外部词表
- **自动换行**: 超过 25 个中文字符时，在标点处自动断开
- 翻译策略：
  - 保持技术术语的准确性
  - 口语化表达（适合短视频）
  - 简洁流畅（避免冗长）
  - **每行不超过 25 个中文字符**
- 输出: `<章节标题>_chinese.srt`（中文字幕）和可选的 `<章节标题>_bilingual.srt`（双语字幕）

**中文字幕换行规则（必须严格遵守）**：
- 每行最多 25 个中文字符
- 超过 25 字时，在语义合适的位置断开（如逗号、顿号、句号后）
- 使用 `\N` 作为换行符（SRT 格式）
- 例如：
  ```
  原文: "The newly released documents show he continued to communicate with some of the most powerful men in the world."
  错误: 新公开的文件显示他继续与世界上一些最有权势的人保持联系
  正确: 新公开的文件显示\N他继续与世界上一些\N最有权势的人保持联系
  ```

#### 5.4 生成双语字幕文件（如果用户选择）
- 合并英文和中文字幕
- 格式: SRT 双语（每条字幕包含英文和中文）
- 样式: 英文在上，中文在下
- 输出: `<章节标题>_bilingual.srt`

#### 5.5 烧录字幕到视频（如果用户选择）

使用 ffmpeg 烧录字幕和水印：

```bash
ffmpeg -y -i <video_path> -vf "
  subtitles=<subtitle_path>:force_style='FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,BackColour=&H4D000000,Outline=0,Shadow=0,BorderStyle=4,MarginV=50',
  drawtext=text='奶爸':fontfile='/System/Library/Fonts/STHeiti Medium.ttc':fontsize=56:fontcolor=white@0.2:x=(w-text_w)/2:y=h*2/3
" -c:a copy <output_path>
```

**字幕样式（必须严格遵守）**：
- 白色文字: `PrimaryColour=&H00FFFFFF`
- 黑色背景: `BackColour=&H4D000000`（70%不透明度，4D = 77 = 30% 透明）
- 背景样式: `BorderStyle=4`（不透明背景框）
- 无描边: `Outline=0, Shadow=0`
- 字体大小: 22
- 底部边距: 50

**水印样式（必须严格遵守）**：
- 文字: "奶爸"
- 位置: 水平居中，距底部 1/3 处 (`x=(w-text_w)/2:y=h*2/3`)
- 字体大小: 56
- 透明度: 20%（`fontcolor=white@0.2`）

- 输出: `<章节标题>_with_subtitles.mp4`

#### 5.6 生成总结文案（使用 Groq LLM API）
```bash
cd ~/.claude/skills/video-clipper
python3 scripts/generate_summary.py --create <title> <time_range> <summary> <keywords> <output.md> [subtitle.srt]
```
- **使用 Groq LLM API 生成**（`llama-3.3-70b-versatile` 模型），需要 `GROQ_API_KEY`
- 可传入中文字幕文件提供更多上下文，生成更精准的文案
- 一次生成 5 个平台的文案：小红书、抖音/快手、YouTube、Twitter/X、Instagram
- 输出: `<章节标题>_social_media_copy.md`

**进度展示**:
```
🎬 开始处理章节 1/3: AGI 不是时间点，是指数曲线

1/6 剪辑视频片段... ✅
2/6 提取字幕片段... ✅
3/6 翻译字幕为中文... [=====>    ] 50% (26/52)
4/6 生成双语字幕文件... ✅
5/6 烧录字幕到视频... ✅
6/6 生成总结文案... ✅

✨ 章节 1 处理完成
```

---

### 阶段 6: 输出结果

**目标**: 组织输出文件并展示给用户

1. 创建输出目录
   ```
   ~/Documents/Claude Code/Convert/<视频标题>/
   ```

2. **必须保存的文件**（所有文件都要保存，缺一不可）：
   ```
   <视频标题>/
   ├── <视频标题>_1080p.mp4        # 原片（1080p，无字幕）
   ├── <视频标题>_original.srt     # 原始语言字幕（Groq Whisper 转录）
   ├── <视频标题>_chinese.srt      # 中文翻译字幕
   └── <视频标题>_final.mp4        # 成品视频（烧录中文字幕+水印）
   ```

3. 向用户展示：
   - 输出目录路径
   - 文件列表（带文件大小）
   - 快速预览命令

   ```
   ✨ 处理完成！

   📁 输出目录: ~/Documents/Claude Code/Convert/伊朗讽刺节目/

   文件列表:
     🎬 伊朗讽刺节目_1080p.mp4 (5.2 MB) - 原片
     📄 伊朗讽刺节目_original.srt (1.2 KB) - 原始字幕
     📄 伊朗讽刺节目_chinese.srt (0.8 KB) - 中文字幕
     🎬 伊朗讽刺节目_final.mp4 (5.5 MB) - 成品视频

   快速预览:
   open ~/Documents/Claude\ Code/Convert/伊朗讽刺节目/伊朗讽刺节目_final.mp4
   ```

4. 询问是否继续剪辑其他章节
   - 如果是，返回阶段 4（用户选择）
   - 如果否，结束 Skill

---

## 关键技术点

### 0. 视频分辨率标准化
**目标**: 所有输出视频统一为 1920x1080 (1080p)

**方法**: 使用 ffmpeg scale + pad 滤镜
```bash
ffmpeg -i input.mp4 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black" output.mp4
```
- 保持原始宽高比
- 不足部分用黑边填充
- 居中显示

### 1. FFmpeg 路径空格问题
**问题**: FFmpeg subtitles 滤镜无法正确解析包含空格的路径

**解决方案**: burn_subtitles.py 使用临时目录
- 创建无空格临时目录
- 复制文件到临时目录
- 执行 FFmpeg
- 移动输出文件回目标位置

### 2. 批量翻译优化
**问题**: 逐条翻译会产生大量 API 调用

**解决方案**: 每批 20 条字幕一起翻译
- 节省 95% API 调用
- 提高翻译速度
- 保持翻译一致性

### 3. 章节分析精细度
**目标**: 生成 2-5 分钟粒度的章节，避免半小时粗粒度

**方法**:
- 理解字幕语义，识别主题转换
- 寻找自然的话题切换点
- 确保每个章节有完整的论述
- 避免机械按时间切分

### 4. FFmpeg 版本选择
**区别**:
- 标准 FFmpeg: 无 libass 支持，无法烧录字幕
- ffmpeg-full: 包含 libass，支持字幕烧录

**路径**:
- 标准: `/opt/homebrew/bin/ffmpeg`
- ffmpeg-full: `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` (Apple Silicon)

### 5. 中文字幕换行规范
**规则**: 每行最多 25 个中文字符

**处理方法**:
- 翻译时自动控制每行长度
- 超过 25 字在语义合适位置断开
- 使用 `\N` 作为 SRT 换行符
- 断句优先级：句号 > 逗号 > 顿号 > 空格 > 强制断开

**示例**:
```
❌ 错误（32字一行）:
新公开的文件显示他继续与世界上一些最有权势的人保持联系

✅ 正确（分成两行，每行≤20字）:
新公开的文件显示\N他继续与世界上最有权势的人联系
```

### 6. 字幕和水印样式规范

**字幕样式**:
- 白色粗体文字 + 黑色半透明背景（70%不透明度）
- ASS force_style 参数:
  - `Bold=1` (粗体)
  - `PrimaryColour=&H00FFFFFF` (白色文字)
  - `BackColour=&H4D000000` (黑色背景，80=128=50%不透明)
  - `BorderStyle=4` (不透明背景框)
  - `Outline=0, Shadow=0` (无描边无阴影)
  - `FontSize=22`
  - `MarginV=50`

**水印样式**:
- 文字: "奶爸"
- 字体: STHeiti Medium（华文黑体，粗体）
- 位置: 水平居中，距底部 1/3 处
- 字体大小: 56
- 透明度: 20%
- drawtext 参数: `text='奶爸':fontfile='/System/Library/Fonts/STHeiti Medium.ttc':fontsize=56:fontcolor=white@0.2:x=(w-text_w)/2:y=h*2/3`

---

## 错误处理

### 环境问题
- 缺少工具 → 提示安装命令
- FFmpeg 无 libass → 引导安装 ffmpeg-full
- Python 依赖缺失 → 提示 pip install

### 下载问题
- 无效 URL → 提示检查 URL 格式
- 网络错误 → 提示重试
- Groq API 转录失败 → 检查 GROQ_API_KEY 是否正确，检查网络连接

### 处理问题
- FFmpeg 执行失败 → 显示详细错误信息
- 翻译失败 → 重试机制（最多 3 次）
- 磁盘空间不足 → 提示清理空间

---

## 输出文件命名规范

**输出目录**: `~/Documents/Claude Code/Convert/<视频标题>/`

**必须保存的 4 个文件**:
- 原片: `<视频标题>_1080p.mp4` - 缩放到 1080p 的原始视频
- 原始字幕: `<视频标题>_original.srt` - Groq Whisper 转录的原语言字幕
- 中文字幕: `<视频标题>_chinese.srt` - 翻译后的中文字幕
- 成品视频: `<视频标题>_final.mp4` - 烧录中文字幕和水印的最终视频

**文件名处理**:
- 移除特殊字符（`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`）
- 空格替换为下划线
- 限制长度（最多 100 字符）

---

## 用户体验要点

1. **进度可见**: 每个步骤都展示进度和状态
2. **错误友好**: 清晰的错误信息和解决方案
3. **可控性**: 用户选择要剪辑的章节和处理选项
4. **高质量**: 章节分析有意义，翻译准确流畅
5. **完整性**: 提供原始和处理后的多个版本

---

## 开始执行

当用户触发这个 Skill 时：
1. 立即开始阶段 1（环境检测）
2. 按照 6 个阶段顺序执行
3. 每个阶段完成后自动进入下一阶段
4. 遇到问题时提供清晰的解决方案
5. 最后展示完整的输出结果

记住：这个 Skill 的核心价值在于 **AI 精细章节分析** 和 **无缝的技术处理**，让用户能快速从长视频中提取高质量的短视频片段。
