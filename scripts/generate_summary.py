#!/usr/bin/env python3
"""
生成社交媒体文案 - 使用 Groq LLM API
基于章节信息和字幕内容，生成适合各平台的推广文案
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

try:
    from groq import Groq
except ImportError:
    print("❌ 请先安装 groq: pip install groq")
    sys.exit(1)


def generate_summary(
    chapter_info: Dict,
    output_path: str = None,
    subtitle_text: str = None,
    model: str = "llama-3.3-70b-versatile"
) -> str:
    """
    使用 Groq LLM API 生成社交媒体文案

    Args:
        chapter_info: 章节信息 {title, time_range, summary, keywords}
        output_path: 输出 markdown 文件路径
        subtitle_text: 字幕全文（可选，提供更多上下文）
        model: Groq 模型名称

    Returns:
        str: 生成的 markdown 文案
    """
    api_key = os.environ.get('GROQ_API_KEY', '').strip()
    if not api_key:
        raise ValueError(
            "❌ 未设置 GROQ_API_KEY 或值为空\n"
            "   1. 申请 Key: https://console.groq.com/keys\n"
            "   2. 设置: export GROQ_API_KEY='gsk_...'"
        )
    if not api_key.startswith('gsk_'):
        raise ValueError(
            "❌ GROQ_API_KEY 格式不正确（应以 'gsk_' 开头）\n"
            "   请检查是否复制了完整的 Key: https://console.groq.com/keys"
        )

    client = Groq(api_key=api_key)

    title = chapter_info.get('title', '未命名章节')
    time_range = chapter_info.get('time_range', 'N/A')
    summary = chapter_info.get('summary', '')
    keywords = chapter_info.get('keywords', [])
    duration = chapter_info.get('duration', '')

    print(f"\n📝 生成社交媒体文案 (Groq LLM: {model})")
    print(f"   章节: {title}")
    print(f"   时间: {time_range}")

    # 构建上下文
    context = f"""视频章节信息：
- 标题: {title}
- 时长: {duration or time_range}
- 核心内容: {summary}
- 关键词: {', '.join(keywords)}"""

    if subtitle_text:
        # 截取前 2000 字符避免超出 token 限制
        sub_preview = subtitle_text[:2000]
        if len(subtitle_text) > 2000:
            sub_preview += "\n...(后续内容省略)"
        context += f"\n\n字幕全文（中文翻译）：\n{sub_preview}"

    prompt = f"""{context}

请基于以上信息，生成适合各社交媒体平台的推广文案。

要求：
1. 标题要吸引人，有悬念或冲突感
2. 内容要抓住核心看点，有金句
3. 风格口语化，适合中文互联网
4. 每个平台的风格要有区别

请严格按以下 Markdown 格式输出：

# 社交媒体文案

## 视频信息
- **标题**: {title}
- **时长**: {duration or time_range}
- **主题**: (一句话概括)

---

## 小红书文案

### 标题
(15-25字，要有emoji，吸引点击)

### 正文
(口语化，有emoji，分段清晰，500-800字)

(末尾加话题标签，5-8个)

---

## 抖音/快手文案

### 标题
(15-20字，简洁有力)

### 文案
(精炼，突出金句，emoji点缀，300字以内)

(末尾加话题标签)

---

## YouTube 简介
(概括视频核心看点，带关键词，200-300字)

---

## Twitter/X 文案

### 推文 1
(280字以内的主推文)

### 推文 2
(补充角度的跟推)

---

## Instagram 文案
(适合图文配合，有故事感，300-500字)
"""

    print(f"   调用 Groq API...")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你是资深的社交媒体运营专家，擅长为视频内容创作吸引人的推广文案。文案风格要接地气、有网感，适合中文互联网用户。"
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    result = response.choices[0].message.content.strip()

    print(f"   ✅ 文案生成完成")

    # 保存到文件
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)

        print(f"   💾 已保存: {output_path}")

    return result


def load_chapter_info(json_path: str) -> Dict:
    """从 JSON 文件加载章节信息"""
    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_subtitle_text(srt_path: str) -> str:
    """从 SRT 文件提取纯文本"""
    srt_path = Path(srt_path)
    if not srt_path.exists():
        return ""

    lines = []
    with open(srt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过序号、时间戳、空行
            if not line or line.isdigit() or '-->' in line:
                continue
            lines.append(line)

    return '\n'.join(lines)


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python generate_summary.py <chapter_info.json> [output.md] [subtitle.srt]")
        print("  python generate_summary.py --create <title> <time_range> <summary> <keywords> [output.md] [subtitle.srt]")
        print("\nExamples:")
        print("  python generate_summary.py chapter.json")
        print("  python generate_summary.py chapter.json copy.md chinese.srt")
        print("  python generate_summary.py --create 'Pauline成为kingmaker' '00:00-01:46' '澳洲政坛变局' 'OneNation,政治,联盟' copy.md")
        print("\nRequires: GROQ_API_KEY environment variable")
        sys.exit(1)

    subtitle_text = None

    try:
        if sys.argv[1] == '--create':
            if len(sys.argv) < 6:
                print("❌ --create 模式需要: title, time_range, summary, keywords")
                sys.exit(1)

            chapter_info = {
                'title': sys.argv[2],
                'time_range': sys.argv[3],
                'summary': sys.argv[4],
                'keywords': sys.argv[5].split(','),
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            output_file = sys.argv[6] if len(sys.argv) > 6 else 'summary.md'

            # 可选的字幕文件
            if len(sys.argv) > 7:
                subtitle_text = load_subtitle_text(sys.argv[7])

        else:
            json_file = sys.argv[1]
            chapter_info = load_chapter_info(json_file)
            output_file = sys.argv[2] if len(sys.argv) > 2 else 'summary.md'

            # 可选的字幕文件
            if len(sys.argv) > 3:
                subtitle_text = load_subtitle_text(sys.argv[3])

        result = generate_summary(chapter_info, output_file, subtitle_text)

        print(f"\n✨ 文案生成完成！")
        print(f"   输出文件: {output_file}")

    except Exception as e:
        from utils import sanitize_error_message
        print(f"\n❌ 错误: {sanitize_error_message(str(e))}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
