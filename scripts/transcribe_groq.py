#!/usr/bin/env python3
"""
使用 Groq Whisper API 快速转录音频/视频
比本地 whisper 快 50+ 倍
"""

import argparse
import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path

try:
    from groq import Groq
except ImportError:
    print("❌ 请先安装 groq: pip install groq")
    sys.exit(1)


def extract_audio(video_path: str, audio_path: str, bitrate: str = '64k',
                   sample_rate: int = 16000, channels: int = 1) -> bool:
    """从视频提取音频（Groq API 限制 25MB，用 mp3 压缩）"""
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-vn', '-acodec', 'libmp3lame', '-ab', bitrate,
        '-ar', str(sample_rate), '-ac', str(channels),
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


MAX_FILE_SIZE_MB = 25


def extract_audio_within_limit(video_path: str, audio_path: str,
                               sample_rate: int = 16000, channels: int = 1) -> bool:
    """提取音频并确保文件大小 < 25MB，自动降低比特率重试"""
    bitrates = ['64k', '32k', '16k']
    source_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
    print(f"📐 原始文件大小: {source_size_mb:.1f} MB")

    for bitrate in bitrates:
        print(f"🔧 尝试比特率 {bitrate} 压缩音频...")
        if not extract_audio(video_path, audio_path, bitrate,
                             sample_rate=sample_rate, channels=channels):
            print(f"❌ 比特率 {bitrate} 压缩失败")
            continue

        file_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)
        print(f"📏 压缩后大小: {file_size_mb:.1f} MB (比特率: {bitrate})")

        if file_size_mb < MAX_FILE_SIZE_MB:
            print(f"✅ 文件大小符合要求 (<{MAX_FILE_SIZE_MB}MB)")
            return True
        else:
            print(f"⚠️ 文件仍超过 {MAX_FILE_SIZE_MB}MB，尝试更低比特率...")

    print(f"❌ 所有比特率均无法将文件压缩到 {MAX_FILE_SIZE_MB}MB 以下")
    print(f"💡 建议：请先裁剪视频长度后再试（可用 ffmpeg 截取片段）")
    return False


def transcribe_with_groq(file_path: str, language: str = None,
                         sample_rate: int = 16000, channels: int = 1) -> dict:
    """
    使用 Groq Whisper API 转录

    Args:
        file_path: 音频或视频文件路径
        language: 语言代码（可选，如 'en', 'zh', 'ja'），不指定则自动检测
        sample_rate: 音频采样率（默认 16000Hz）
        channels: 音频声道数（默认 1 单声道）

    Returns:
        dict: {
            'text': 完整文本,
            'srt': SRT 格式字幕,
            'language': 检测到的语言
        }
    """
    api_key = os.environ.get('GROQ_API_KEY', '').strip()
    if not api_key:
        raise ValueError("❌ 未设置 GROQ_API_KEY 或值为空\n"
                        "   1. 申请 Key: https://console.groq.com/keys\n"
                        "   2. 设置: export GROQ_API_KEY='gsk_...'")
    if not api_key.startswith('gsk_'):
        raise ValueError("❌ GROQ_API_KEY 格式不正确（应以 'gsk_' 开头）\n"
                        "   请检查是否复制了完整的 Key: https://console.groq.com/keys")

    client = Groq(api_key=api_key)
    file_path = Path(file_path)

    # 检查文件大小，如果是视频或文件太大，先提取/压缩音频
    input_file = file_path
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv'}
    needs_extraction = file_path.suffix.lower() in video_extensions or file_size_mb > 20

    # 使用 TemporaryDirectory context manager 确保临时文件清理（含 KeyboardInterrupt）
    with tempfile.TemporaryDirectory(prefix='groq_transcribe_') as tmp_dir:
        os.chmod(tmp_dir, 0o700)
        if needs_extraction:
            print(f"📦 提取音频并压缩...")
            temp_audio = os.path.join(tmp_dir, 'temp_audio.mp3')
            if not extract_audio_within_limit(str(file_path), temp_audio,
                                                 sample_rate=sample_rate, channels=channels):
                raise RuntimeError(
                    f"❌ 音频文件超过 {MAX_FILE_SIZE_MB}MB 限制，无法上传到 Groq API。\n"
                    f"💡 请先裁剪视频长度，例如：\n"
                    f"   ffmpeg -i \"{file_path}\" -t 3600 -c copy trimmed.mp4"
                )
            os.chmod(temp_audio, 0o600)
            input_file = Path(temp_audio)

        print(f"🎙️ 正在转录 (Groq Whisper)...")

        max_retries = 3
        transcription = None
        with open(input_file, 'rb') as f:
            file_data = f.read()

        for retry in range(max_retries):
            try:
                transcription = client.audio.transcriptions.create(
                    file=(input_file.name, file_data),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    language=language,
                    timestamp_granularities=["word"],
                )
                break
            except Exception as e:
                error_str = str(e).lower()
                status_code = getattr(e, 'status_code', None)

                # 不可重试的错误：认证失败、无效文件等
                if status_code in (401, 403, 404, 422) or 'auth' in error_str or 'invalid' in error_str:
                    raise

                # 可重试的错误：网络超时、服务器错误 5xx 等
                if retry < max_retries - 1:
                    wait = (retry + 1) * 2  # 递增等待：2s, 4s
                    from utils import sanitize_error_message
                    print(f"⚠️ 转录失败，{wait}秒后重试({retry + 1}/{max_retries - 1})... 错误: {sanitize_error_message(str(e))}")
                    time.sleep(wait)
                else:
                    print(f"❌ 转录失败，已重试 {max_retries - 1} 次")
                    raise

        # 构建 SRT：优先用 word 级时间戳按句子重建，精度远优于 segment 级
        srt_content = ""
        words = getattr(transcription, 'words', None)

        if words and len(words) > 0:
            # 用 word 级时间戳按句子边界重建 segment
            segments = words_to_sentences(words)
            print(f"🎯 使用 word 级时间戳重建字幕 ({len(words)} 词 → {len(segments)} 条)")
        elif hasattr(transcription, 'segments') and transcription.segments:
            # 回退到 segment 级 + 拆分长 segment
            segments = list(transcription.segments)
            orig_count = len(segments)
            segments = split_long_segments(segments)
            if len(segments) > orig_count:
                print(f"✂️ 拆分长字幕: {orig_count} → {len(segments)} 条")
        else:
            segments = []

        # 修正首条字幕时间戳：利用 word 级时间戳推断真实起始
        # Whisper 常给首几个词错误的时间戳（如 start=0），需要智能修正
        if segments and words and len(words) > 0:
            segments[0] = dict(segments[0])
            segments[0]['start'] = estimate_first_sentence_start(
                words, segments[0], str(file_path)
            )

        # 延长字幕显示时间：避免字幕消失太早
        # 规则：间隔>1s → end+1s；间隔<=1s → end=下条start
        segments = extend_subtitle_duration(segments)

        for i, seg in enumerate(segments, 1):
            start = format_timestamp(seg['start'])
            end = format_timestamp(seg['end'])
            text = seg['text'].strip()
            if text:
                srt_content += f"{i}\n{start} --> {end}\n{text}\n\n"

        detected_language = getattr(transcription, 'language', 'unknown')

        print(f"✅ 转录完成")
        print(f"   语言: {detected_language}")
        print(f"   字幕条数: {len(segments)}")

        return {
            'text': transcription.text,
            'srt': srt_content,
            'language': detected_language,
            'segments': transcription.segments if hasattr(transcription, 'segments') else []
        }


def extend_subtitle_duration(segments: list) -> list:
    """
    延长字幕显示时间，避免字幕消失太早。

    规则：
    - 如果当前字幕 end 与下条字幕 start 间隔 > 1秒：当前 end += 1秒
    - 如果间隔 <= 1秒：当前 end = 下条 start（无缝衔接）
    - 最后一条字幕：end += 1秒
    """
    if not segments:
        return segments

    result = [dict(seg) for seg in segments]

    for i in range(len(result)):
        if i < len(result) - 1:
            gap = result[i + 1]['start'] - result[i]['end']
            if gap > 1.0:
                result[i]['end'] = round(result[i]['end'] + 1.0, 3)
            else:
                result[i]['end'] = result[i + 1]['start']
        else:
            # 最后一条字幕延长1秒
            result[i]['end'] = round(result[i]['end'] + 1.0, 3)

    return result


def words_to_sentences(words: list, max_duration: float = 6.0) -> list:
    """
    将 word 级时间戳按句子边界重组为 segment。
    先在句末标点（. ? !）处断句，再对超长句子在逗号处拆分。

    Args:
        words: Groq Whisper 返回的 words 列表，每项含 word/start/end
        max_duration: 单条字幕最大时长（秒），超过则在逗号处拆分

    Returns:
        list: segment 列表，每项含 start/end/text
    """
    import re
    if not words:
        return []

    # 第一步：按句末标点断句
    raw_segments = []
    current_words = []
    current_text = ""

    for w in words:
        word = w.get('word', '').strip()
        if not word:
            continue

        current_words.append(w)
        current_text = (current_text + " " + word).strip() if current_text else word

        if re.search(r'[.?!]$', word):
            raw_segments.append({
                'start': current_words[0]['start'],
                'end': current_words[-1]['end'],
                'text': current_text,
                'words': list(current_words)
            })
            current_words = []
            current_text = ""

    if current_words:
        raw_segments.append({
            'start': current_words[0]['start'],
            'end': current_words[-1]['end'],
            'text': current_text,
            'words': list(current_words)
        })

    # 第二步：对超长句子在逗号处拆分
    segments = []
    for seg in raw_segments:
        duration = seg['end'] - seg['start']
        if duration <= max_duration:
            segments.append({
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text']
            })
            continue

        # 找逗号断点，用词级时间戳精确切分
        seg_words = seg['words']
        split_segments = _split_at_commas(seg_words, max_duration)
        segments.extend(split_segments)

    return segments


def _split_at_commas(words: list, max_duration: float) -> list:
    """
    在逗号处拆分超长句子，利用词级时间戳精确切分。
    """
    import re

    # 找所有逗号位置（词以 , 结尾的）
    comma_indices = []
    for i, w in enumerate(words):
        word = w.get('word', '').strip()
        if re.search(r',$', word) and i < len(words) - 1:
            comma_indices.append(i)

    if not comma_indices:
        # 没有逗号，无法拆分，保持原样
        return [{
            'start': words[0]['start'],
            'end': words[-1]['end'],
            'text': ' '.join(w.get('word', '').strip() for w in words)
        }]

    # 在逗号处切分，确保每段不超过 max_duration
    segments = []
    chunk_start_idx = 0

    for ci in comma_indices:
        chunk_words = words[chunk_start_idx:ci + 1]
        chunk_duration = chunk_words[-1]['end'] - chunk_words[0]['start']

        if chunk_duration >= max_duration * 0.4:
            # 这个片段够长了，切出来
            text = ' '.join(w.get('word', '').strip() for w in chunk_words)
            segments.append({
                'start': chunk_words[0]['start'],
                'end': chunk_words[-1]['end'],
                'text': text
            })
            chunk_start_idx = ci + 1

    # 处理剩余的词
    if chunk_start_idx < len(words):
        remaining = words[chunk_start_idx:]
        text = ' '.join(w.get('word', '').strip() for w in remaining)
        segments.append({
            'start': remaining[0]['start'],
            'end': remaining[-1]['end'],
            'text': text
        })

    return segments


def split_long_segments(segments: list, max_chars: int = 60, max_duration: float = 4.0) -> list:
    """
    拆分过长的 Whisper segment，确保每条字幕简短易读。

    拆分策略：
    1. 按句子边界拆分（. ? ! 等）
    2. 如果单句仍超长，按从句边界拆分（, ; : — 等）
    3. 按文本长度比例分配时间

    Args:
        segments: Whisper 返回的 segment 列表
        max_chars: 单条字幕最大字符数（默认 60）
        max_duration: 单条字幕最大持续时间秒数（默认 4.0）

    Returns:
        list: 拆分后的 segment 列表
    """
    import re
    result = []

    for seg in segments:
        text = seg['text'].strip()
        start = seg['start']
        end = seg['end']
        duration = end - start

        # 不需要拆分的短 segment
        if len(text) <= max_chars and duration <= max_duration:
            result.append(seg)
            continue

        # 先尝试按句子拆分（. ? !）
        parts = re.split(r'(?<=[.?!])\s+', text)
        if len(parts) <= 1:
            # 单句过长，按从句拆分（, ; :）
            parts = re.split(r'(?<=[,;:])\s+', text)

        if len(parts) <= 1:
            # 无法拆分，保持原样
            result.append(seg)
            continue

        # 按文本长度比例分配时间
        total_chars = sum(len(p) for p in parts)
        current_time = start

        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            char_ratio = len(part) / total_chars
            part_duration = duration * char_ratio
            part_end = current_time + part_duration if i < len(parts) - 1 else end

            result.append({
                'start': round(current_time, 3),
                'end': round(part_end, 3),
                'text': part
            })
            current_time = part_end

    return result


def estimate_first_sentence_start(words: list, first_segment: dict,
                                   file_path: str) -> float:
    """
    利用 Whisper 词级时间戳 + silencedetect 推断首句真实起始时间。

    Whisper 经常给首几个词错误的时间戳（如 start=0.0，duration=3s），
    但后续词的时间戳通常是准确的。

    策略：
    1. 找到首句中第一个时长合理（<1.0s）的词 → 该词时间戳可信
    2. 从该词向前推算前面几个词的时间（每词约 0.35s）
    3. 用 silencedetect 找到最近的音频段起始点进行交叉验证
    4. 取两者中较晚的值（确保字幕不早于音频）
    """
    # 找出属于首句的词（end <= 首句 end + 1s 容差）
    seg_end = first_segment['end']
    first_words = []
    for w in words:
        w_start = w.get('start', 0)
        if w_start <= seg_end + 1.0:
            first_words.append(w)
        else:
            break

    if not first_words:
        return first_segment['start']

    # 找第一个时长合理的词（duration < 1.0s）
    reliable_idx = None
    for i, w in enumerate(first_words):
        duration = w.get('end', 0) - w.get('start', 0)
        if duration < 1.0 and duration > 0:
            reliable_idx = i
            break

    if reliable_idx is not None and reliable_idx > 0:
        # 有不可靠的前置词，从可靠词向前推算
        reliable_start = first_words[reliable_idx].get('start', 0)
        num_preceding = reliable_idx
        # 英语平均每词约 0.35s
        estimated_start = reliable_start - (num_preceding * 0.35)

        # 用 silencedetect 交叉验证：找到 estimated_start 附近最近的音频段起始
        audio_segments = detect_audio_segments(file_path)
        best_audio_start = find_nearest_audio_start(audio_segments, estimated_start)

        if best_audio_start is not None:
            # 取两者中较晚的值，确保字幕不早于真实音频
            final_start = max(estimated_start, best_audio_start)
        else:
            final_start = estimated_start

        final_start = max(0, final_start)
        print(f"🎯 首句时间修正: 可靠词[{reliable_idx}] '{first_words[reliable_idx].get('word','')}' "
              f"在 {reliable_start:.2f}s → 向前推 {num_preceding} 词 → 起始 {final_start:.2f}s")
        return final_start

    elif reliable_idx == 0:
        # 第一个词就是可靠的，直接使用
        return first_words[0].get('start', first_segment['start'])

    else:
        # 所有词都不可靠，回退到 silencedetect
        audio_segments = detect_audio_segments(file_path)
        if audio_segments:
            # 找最后一个在 first_segment['end'] 之前开始的音频段
            for seg in reversed(audio_segments):
                if seg['start'] < first_segment['end']:
                    print(f"🔇 词级时间戳不可靠，使用音频段起始: {seg['start']:.2f}s")
                    return seg['start']
        return first_segment['start']


def detect_audio_segments(file_path: str, silence_thresh: str = '-25dB',
                          min_silence_dur: float = 0.3) -> list:
    """
    用 silencedetect 获取所有音频段（非静音段）的起止时间。

    Returns:
        list of dict: [{'start': float, 'end': float}, ...]
    """
    import re as _re
    cmd = [
        'ffmpeg', '-i', file_path,
        '-af', f'silencedetect=noise={silence_thresh}:d={min_silence_dur}',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    silence_ends = [float(m) for m in _re.findall(r'silence_end:\s*([\d.]+)', stderr)]
    silence_starts = [float(m) for m in _re.findall(r'silence_start:\s*([\d.]+)', stderr)]

    # 构建音频段列表
    audio_segments = []
    for i, s_end in enumerate(silence_ends):
        # 音频段开始于 silence_end，结束于下一个 silence_start
        a_start = s_end
        # 找对应的 silence_start（在 s_end 之后的第一个）
        a_end = None
        for ss in silence_starts:
            if ss > s_end:
                a_end = ss
                break
        if a_end:
            audio_segments.append({'start': a_start, 'end': a_end})

    return audio_segments


def find_nearest_audio_start(audio_segments: list, target_time: float,
                             tolerance: float = 2.0) -> float:
    """
    找到 target_time 附近（±tolerance）最近的音频段起始时间。
    """
    best = None
    best_dist = float('inf')
    for seg in audio_segments:
        dist = abs(seg['start'] - target_time)
        if dist < best_dist and dist <= tolerance:
            best = seg['start']
            best_dist = dist
    return best


def detect_speech_start(file_path: str, silence_thresh: str = '-30dB',
                        min_silence_dur: float = 0.5) -> float:
    """
    使用 FFmpeg silencedetect 检测音频中语音实际开始的时间点。

    Args:
        file_path: 音频或视频文件路径
        silence_thresh: 静音阈值（默认 -30dB）
        min_silence_dur: 最短静音持续时间（默认 0.5 秒）

    Returns:
        float: 语音开始的秒数（如果一开始就有语音则返回 0.0）
    """
    cmd = [
        'ffmpeg', '-i', file_path,
        '-af', f'silencedetect=noise={silence_thresh}:d={min_silence_dur}',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    # 查找第一个 silence_end，即语音开始的时间
    import re
    matches = re.findall(r'silence_end:\s*([\d.]+)', stderr)
    if matches:
        return float(matches[0])

    # 没有检测到静音 → 一开始就有语音
    return 0.0


def format_timestamp(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳格式 HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def save_srt(srt_content: str, output_path: str):
    """保存 SRT 文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    print(f"💾 已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='使用 Groq Whisper API 快速转录音频/视频')
    parser.add_argument('input', help='视频或音频文件路径')
    parser.add_argument('language', nargs='?', default=None,
                        help='语言代码（如 en, zh, ja），不指定则自动检测')
    parser.add_argument('output', nargs='?', default=None,
                        help='输出 SRT 文件路径（默认与输入同名 .srt）')
    parser.add_argument('--sample-rate', type=int, default=16000,
                        help='音频采样率（默认: 16000）')
    parser.add_argument('--channels', type=int, default=1,
                        help='音频声道数（默认: 1 单声道）')

    args = parser.parse_args()

    input_file = args.input
    language = args.language

    # 兼容旧用法：第二个参数如果是 .srt 文件则作为输出路径
    if language and language.endswith('.srt'):
        output_path = language
        language = None
    elif args.output:
        output_path = args.output
    else:
        output_path = str(Path(input_file).with_suffix('.srt'))

    # 语言代码校验
    if language and len(language) > 3:
        language = None

    try:
        result = transcribe_with_groq(input_file, language,
                                      sample_rate=args.sample_rate,
                                      channels=args.channels)
        save_srt(result['srt'], output_path)

        print(f"\n📊 转录结果:")
        print(f"   语言: {result['language']}")
        print(f"   文件: {output_path}")

    except Exception as e:
        from utils import sanitize_error_message
        print(f"❌ 错误: {sanitize_error_message(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
