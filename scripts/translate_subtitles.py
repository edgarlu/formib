#!/usr/bin/env python3
"""
翻译字幕 - 使用 Groq LLM API
两阶段翻译法：
  Phase 1: 全文理解翻译 - 将完整内容作为一篇文章翻译
  Phase 2: 时间码分配 - 根据每段时长压缩/扩充翻译内容
"""

import os
import sys
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional

try:
    from groq import Groq
except ImportError:
    print("❌ 请先安装 groq: pip install groq")
    sys.exit(1)

from utils import seconds_to_time

# 默认翻译词表（与 SKILL.md 保持一致）
DEFAULT_GLOSSARY = {
    "Trump": "川普",
    "Bessent": "贝森特",
}


def load_glossary(glossary_path: str = None) -> dict:
    """加载翻译词表"""
    glossary = DEFAULT_GLOSSARY.copy()
    if glossary_path and Path(glossary_path).exists():
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                external = json.load(f)
            if not isinstance(external, dict):
                raise ValueError("词表必须是 JSON 对象（dict）")
            for k, v in external.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise ValueError("词表的 key 和 value 必须都是字符串")
            glossary.update(external)
            print(f"   📖 加载外部词表: {len(external)} 条")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"   ⚠️  外部词表格式无效（{e}），使用默认词表")
    return glossary


def build_glossary_prompt(glossary: dict) -> str:
    """构建词表 prompt 片段"""
    if not glossary:
        return ""
    lines = ["\n翻译词表（必须严格遵守）："]
    for en, zh in glossary.items():
        lines.append(f"  {en} → {zh}")
    return "\n".join(lines)


def call_llm(client: Groq, system_prompt: str, user_prompt: str,
             model: str = "llama-3.3-70b-versatile",
             temperature: float = 0.3, max_tokens: int = 8192,
             max_retries: int = 3) -> str:
    """调用 Groq LLM，带重试机制"""
    for retry in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if retry < max_retries - 1:
                wait = (retry + 1) * 2
                print(f"重试({retry + 1})...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise
    return ""


def phase1_holistic_translate(
    client: Groq,
    subtitles: List[Dict],
    target_lang: str = "中文",
    source_lang: str = "英文",
    model: str = "llama-3.3-70b-versatile",
    glossary: dict = None
) -> str:
    """
    阶段一：全文理解翻译
    将所有字幕拼成完整文章，一次性翻译，确保上下文连贯
    """
    # 构建带编号的完整原文
    full_text_lines = []
    for i, sub in enumerate(subtitles):
        full_text_lines.append(sub['text'])
    full_text = " ".join(full_text_lines)

    glossary_prompt = build_glossary_prompt(glossary or {})

    system_prompt = f"你是专业的视频字幕翻译员。请将完整的视频内容翻译为自然流畅的{target_lang}。"

    user_prompt = f"""以下是一段完整的视频内容（{source_lang}）。请先通读理解全部内容，然后作为一篇完整的文章翻译为{target_lang}。

翻译要求：
1. 先理解整体内容和语境，再翻译
2. 口语化、简洁流畅，适合视频字幕
3. 保持原文的语气和风格（如讽刺、幽默、正式等）
4. 只输出翻译结果，不要任何解释{glossary_prompt}

完整内容：
{full_text}"""

    return call_llm(client, system_prompt, user_prompt, model)


def phase2_distribute(
    client: Groq,
    holistic_translation: str,
    subtitles: List[Dict],
    target_lang: str = "中文",
    model: str = "llama-3.3-70b-versatile",
    glossary: dict = None
) -> List[str]:
    """
    阶段二：时间码分配
    根据完整翻译和每段时间码的时长，分配翻译内容
    短时间码压缩，长时间码扩充
    """
    # 构建段落信息（含时长和原文）
    segments_info_lines = []
    for i, sub in enumerate(subtitles):
        duration = sub['end'] - sub['start']
        # 估算目标字数：中文语速约 3-4 字/秒
        target_chars = max(2, int(duration * 3.5))
        segments_info_lines.append(
            f"[{i}] 时长{duration:.1f}秒 (目标约{target_chars}字) | 原文: {sub['text']}"
        )
    segments_info = "\n".join(segments_info_lines)

    glossary_prompt = build_glossary_prompt(glossary or {})

    system_prompt = "你是专业的视频字幕翻译员。根据完整翻译和时间码信息，将翻译内容分配到各段。严格按 \"序号: 翻译\" 格式输出。"

    user_prompt = f"""已有一段视频的完整{target_lang}翻译，现在需要把翻译内容分配到各个时间码段落中。

完整翻译（参考）：
{holistic_translation}

各段落的时间码信息：
{segments_info}

核心原则：默认完整翻译原文的每一个意思，不要省略！只有时长极短（<1.5秒）的段落才可以适当精简。

分配规则：
1. 每段的「目标约N字」是参考值，翻译应尽量接近这个字数，不要远少于它
2. 时长≥2秒的段落：必须完整翻译原文的全部意思，不能省略任何信息
   - 例如原文 "Improved communication with your mom can bring you closer"
   - 正确: "改善与妈妈的沟通可以拉近你们的距离"（完整意思）
   - 错误: "改善与妈妈的沟通"（省略了"可以拉近距离"）
3. 时长<1.5秒的段落：可以只保留核心词，如 "好问题" "什么？"
4. 时长>8秒的段落：应该翻译得充分详细，把完整翻译中对应的内容都分配进去
5. 确保完整翻译的所有信息都被分配到各段中，不遗漏任何内容{glossary_prompt}

请严格按 "序号: 翻译" 格式输出，每行一条，不要任何其他内容："""

    result_text = call_llm(client, system_prompt, user_prompt, model)

    # 解析响应
    translations = {}
    for line in result_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^\[?(\d+)\]?\s*[:：.]\s*(.+)$', line)
        if match:
            idx = int(match.group(1))
            text = match.group(2).strip()
            translations[idx] = text

    # 按序号构建结果
    result = []
    for i in range(len(subtitles)):
        if i in translations:
            result.append(translations[i])
        else:
            result.append(f"[翻译失败: {subtitles[i]['text'][:20]}...]")

    return result


def phase2_distribute_batched(
    client: Groq,
    holistic_translation: str,
    subtitles: List[Dict],
    batch_size: int = 50,
    target_lang: str = "中文",
    model: str = "llama-3.3-70b-versatile",
    glossary: dict = None
) -> List[str]:
    """
    阶段二（分批版）：对长视频分批分配翻译
    每批提供完整翻译作为上下文参考
    """
    total = len(subtitles)
    if total <= batch_size:
        return phase2_distribute(client, holistic_translation, subtitles,
                                 target_lang, model, glossary)

    num_batches = (total + batch_size - 1) // batch_size
    all_translations = []

    for batch_idx in range(num_batches):
        start_i = batch_idx * batch_size
        end_i = min(start_i + batch_size, total)
        batch = subtitles[start_i:end_i]

        print(f"   📝 分配第 {start_i + 1}-{end_i} 条...", end=" ", flush=True)

        translations = phase2_distribute(
            client, holistic_translation, batch,
            target_lang, model, glossary
        )

        # 修正序号（因为 batch 内的序号从 0 开始，但实际是从 start_i 开始）
        all_translations.extend(translations)
        print("✅")

        if batch_idx < num_batches - 1:
            time.sleep(0.5)

    return all_translations


def clean_punctuation(text: str) -> str:
    """
    清理中文字幕标点：
    1. 删除每行末尾的句号（。）和逗号（，）
    2. 将中间的逗号（，）和顿号（、）替换为空格
    """
    lines = text.replace("\\N", "\n").split("\n")
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = line.rstrip("。，")
        line = line.replace("，", " ").replace("、", " ")
        result.append(line)
    return "\n".join(result)


def enforce_line_length(text: str, max_chars: int = 25) -> str:
    """将 \\N 和换行合并为单行"""
    text = text.replace("\\N", " ").replace("\n", " ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def split_long_subtitles(translated: List[Dict], max_chars: int = 25,
                         content_key: str = "translation") -> List[Dict]:
    """拆分过长的中文字幕为两条"""
    result = []
    split_count = 0

    for sub in translated:
        text = sub.get(content_key, '')
        if len(text) <= max_chars:
            result.append(sub)
            continue

        mid = len(text) // 2
        best_pos = -1
        for offset in range(len(text)):
            right = mid + offset
            left = mid - offset
            if right < len(text) and text[right] == ' ':
                best_pos = right
                break
            if left >= 0 and text[left] == ' ':
                best_pos = left
                break

        if best_pos <= 0 or best_pos >= len(text) - 1:
            result.append(sub)
            continue

        first_text = text[:best_pos].strip()
        second_text = text[best_pos:].strip()

        if not first_text or not second_text:
            result.append(sub)
            continue

        start = sub['start']
        end = sub['end']
        duration = end - start
        ratio = len(first_text) / (len(first_text) + len(second_text))
        split_time = round(start + duration * ratio, 3)

        first_sub = dict(sub)
        first_sub['end'] = split_time
        first_sub[content_key] = first_text

        second_sub = dict(sub)
        second_sub['start'] = split_time
        second_sub['text'] = ''
        second_sub[content_key] = second_text

        result.append(first_sub)
        result.append(second_sub)
        split_count += 1

    if split_count > 0:
        print(f"   ✂️ 拆分 {split_count} 条过长字幕 (>{max_chars}字)")

    return result


def translate_subtitles(
    subtitles: List[Dict],
    batch_size: int = 50,
    target_lang: str = "中文",
    source_lang: str = "英文",
    model: str = "llama-3.3-70b-versatile",
    glossary: dict = None,
    max_retries: int = 3
) -> List[Dict]:
    """
    两阶段翻译法：
    Phase 1: 全文理解翻译 - 通读全部内容后整体翻译
    Phase 2: 时间码分配 - 根据时长压缩/扩充分配到各段
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

    subtitles = [s for s in subtitles if s.get('text', '').strip()]
    total = len(subtitles)

    print(f"\n🌐 两阶段翻译法 (Groq LLM: {model})")
    print(f"   总条数: {total}")
    print(f"   源语言: {source_lang} → 目标语言: {target_lang}")
    if glossary:
        print(f"   词表: {len(glossary)} 条")

    # ===== Phase 1: 全文理解翻译 =====
    print(f"\n   📖 阶段一：全文理解翻译...", end=" ", flush=True)
    try:
        holistic_translation = phase1_holistic_translate(
            client, subtitles, target_lang, source_lang, model, glossary
        )
        print("✅")
        print(f"   完整翻译 ({len(holistic_translation)} 字):")
        # 显示翻译预览（前200字）
        preview = holistic_translation[:200]
        if len(holistic_translation) > 200:
            preview += "..."
        print(f"   「{preview}」")
    except Exception as e:
        from utils import sanitize_error_message
        print(f"❌ 失败: {sanitize_error_message(str(e))}")
        raise

    # ===== Phase 2: 时间码分配 =====
    print(f"\n   📐 阶段二：按时间码分配翻译...", end=" ", flush=True)
    try:
        translations = phase2_distribute_batched(
            client, holistic_translation, subtitles,
            batch_size, target_lang, model, glossary
        )
        print("✅")
    except Exception as e:
        from utils import sanitize_error_message
        print(f"❌ 失败: {sanitize_error_message(str(e))}")
        raise

    # ===== 后处理 =====
    translated = []
    for i, sub in enumerate(subtitles):
        trans_text = translations[i] if i < len(translations) else "[翻译失败]"
        trans_text = clean_punctuation(trans_text)
        trans_text = enforce_line_length(trans_text, 25)
        translated.append({
            'start': sub['start'],
            'end': sub['end'],
            'text': sub['text'],
            'translation': trans_text
        })

    print(f"\n   ✅ 翻译完成: {total}/{total} 条")

    return translated


def save_translated_srt(
    translated: List[Dict],
    output_path: str,
    content_key: str = "translation"
):
    """保存翻译后的字幕为 SRT 文件"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(translated, 1):
            f.write(f"{i}\n")
            start_time = seconds_to_time(sub['start'], include_hours=True, use_comma=True)
            end_time = seconds_to_time(sub['end'], include_hours=True, use_comma=True)
            f.write(f"{start_time} --> {end_time}\n")
            text = sub[content_key]
            f.write(f"{text}\n")
            f.write("\n")

    print(f"💾 已保存: {output_path}")


def save_bilingual_srt(translated: List[Dict], output_path: str):
    """保存双语字幕（英文在上，中文在下）"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(translated, 1):
            f.write(f"{i}\n")
            start_time = seconds_to_time(sub['start'], include_hours=True, use_comma=True)
            end_time = seconds_to_time(sub['end'], include_hours=True, use_comma=True)
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{sub['text']}\n{sub['translation']}\n")
            f.write("\n")

    print(f"💾 双语字幕已保存: {output_path}")


def load_subtitles_from_srt(srt_path: str) -> List[Dict]:
    """从 SRT 文件加载字幕"""
    try:
        import pysrt
    except ImportError:
        print("❌ Error: pysrt not installed")
        print("Please install: pip install pysrt")
        sys.exit(1)

    srt_path = Path(srt_path)
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    print(f"📂 加载 SRT 字幕: {srt_path.name}")

    subs = pysrt.open(srt_path)
    subtitles = []

    skipped = 0
    for sub in subs:
        text = sub.text.replace('\n', ' ').strip()
        if not text:
            skipped += 1
            continue
        start = sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds + sub.start.milliseconds / 1000
        end = sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds + sub.end.milliseconds / 1000
        subtitles.append({
            'start': start,
            'end': end,
            'text': text
        })

    print(f"   找到 {len(subtitles)} 条字幕")
    if skipped > 0:
        print(f"   ⚠️  已过滤 {skipped} 条空字幕")
    return subtitles


LANG_CODE_MAP = {
    'en': '英文', 'english': '英文',
    'zh': '中文', 'chinese': '中文',
    'ja': '日文', 'japanese': '日文',
    'ko': '韩文', 'korean': '韩文',
    'fr': '法文', 'french': '法文',
    'de': '德文', 'german': '德文',
    'es': '西班牙文', 'spanish': '西班牙文',
    'pt': '葡萄牙文', 'portuguese': '葡萄牙文',
    'ru': '俄文', 'russian': '俄文',
    'ar': '阿拉伯文', 'arabic': '阿拉伯文',
    'it': '意大利文', 'italian': '意大利文',
    'th': '泰文', 'thai': '泰文',
    'vi': '越南文', 'vietnamese': '越南文',
    'hi': '印地文', 'hindi': '印地文',
    'tr': '土耳其文', 'turkish': '土耳其文',
    'fa': '波斯文', 'persian': '波斯文',
    'he': '希伯来文', 'hebrew': '希伯来文',
    'uk': '乌克兰文', 'ukrainian': '乌克兰文',
    'pl': '波兰文', 'polish': '波兰文',
    'nl': '荷兰文', 'dutch': '荷兰文',
    'sv': '瑞典文', 'swedish': '瑞典文',
}


def lang_code_to_name(code: str) -> str:
    """将 Whisper 语言代码转换为中文语言名称"""
    return LANG_CODE_MAP.get(code.lower(), code)


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: python translate_subtitles.py <srt_file> [chinese_output] [bilingual_output] [batch_size] [--source-lang CODE]")
        print("\nArguments:")
        print("  srt_file          - 输入 SRT 字幕文件")
        print("  chinese_output    - 中文字幕输出路径（可选）")
        print("  bilingual_output  - 双语字幕输出路径（可选）")
        print("  batch_size        - 阶段二每批分配数量（可选，默认 50）")
        print("\nOptions:")
        print("  --source-lang CODE  - 源语言代码（如 en, ja, ko, fr），默认 en")
        print("\nExample:")
        print("  python translate_subtitles.py video_original.srt")
        print("  python translate_subtitles.py video_original.srt video_chinese.srt")
        print("  python translate_subtitles.py video_original.srt video_chinese.srt --source-lang ja")
        print("\nRequires: GROQ_API_KEY environment variable")
        sys.exit(1)

    # 解析 --source-lang 参数
    source_lang_code = "en"
    args = list(sys.argv[1:])
    if "--source-lang" in args:
        idx = args.index("--source-lang")
        if idx + 1 < len(args):
            source_lang_code = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        else:
            args = args[:idx]

    source_lang = lang_code_to_name(source_lang_code)

    srt_file = args[0]
    srt_path = Path(srt_file)

    chinese_output = args[1] if len(args) > 1 else str(
        srt_path.parent / f"{srt_path.stem.replace('_original', '')}_chinese.srt"
    )
    bilingual_output = args[2] if len(args) > 2 else None
    batch_size = int(args[3]) if len(args) > 3 else 50

    glossary_path = srt_path.parent / "glossary.json"
    glossary = load_glossary(str(glossary_path) if glossary_path.exists() else None)

    try:
        subtitles = load_subtitles_from_srt(srt_file)

        if not subtitles:
            print("❌ 未找到有效字幕")
            sys.exit(1)

        translated = translate_subtitles(subtitles, batch_size,
                                         source_lang=source_lang,
                                         glossary=glossary)

        save_translated_srt(translated, chinese_output)

        if bilingual_output:
            save_bilingual_srt(translated, bilingual_output)

        print(f"\n✨ 翻译完成！")
        print(f"   中文字幕: {chinese_output}")
        if bilingual_output:
            print(f"   双语字幕: {bilingual_output}")

    except Exception as e:
        from utils import sanitize_error_message
        print(f"\n❌ 错误: {sanitize_error_message(str(e))}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
