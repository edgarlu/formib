#!/usr/bin/env python3
"""
下载视频和字幕
支持 YouTube、Twitter/X、Instagram、TikTok 和本地视频文件
使用 yt-dlp 下载在线视频（最高 1080p）
"""

import sys
import json
import shutil
import subprocess
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("❌ Error: yt-dlp not installed")
    print("Please install: pip install yt-dlp")
    sys.exit(1)

from utils import (
    validate_url,
    validate_twitter_url,
    validate_instagram_url,
    validate_tiktok_url,
    validate_local_video,
    detect_source_type,
    sanitize_filename,
    format_file_size,
    get_video_duration_display,
    ensure_directory
)


def get_video_duration(video_path: str) -> float:
    """
    使用 ffprobe 获取视频时长

    Args:
        video_path: 视频文件路径

    Returns:
        float: 视频时长（秒）
    """
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def scale_to_1080p(video_path: Path) -> Path:
    """
    将视频缩放到 1920x1080 分辨率

    Args:
        video_path: 原视频路径

    Returns:
        Path: 处理后的视频路径
    """
    output_path = video_path.parent / f"{video_path.stem}_1080p{video_path.suffix}"

    # 使用 ffmpeg 缩放，保持宽高比，不足部分用黑边填充
    cmd = [
        'ffmpeg', '-y', '-i', str(video_path),
        '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black',
        '-c:a', 'copy',
        str(output_path)
    ]

    print(f"   📐 缩放视频到 1920x1080...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0 and output_path.exists():
        # 删除原文件，重命名新文件
        video_path.unlink()
        output_path.rename(video_path)
        print(f"   ✅ 缩放完成")
        return video_path
    else:
        print(f"   ⚠️ 缩放失败，保留原分辨率")
        if output_path.exists():
            output_path.unlink()
        return video_path


def download_youtube(url: str, output_dir: Path) -> dict:
    """下载 YouTube 视频（不下载字幕，统一用 Groq Whisper 转录）"""
    ydl_opts = {
        # 优先下载 1080p (1920x1080)
        'format': 'bestvideo[height=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
        'writesubtitles': False,
        'writeautomaticsub': False,
        'writethumbnail': False,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [_progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("\n📊 获取视频信息...")
        info = ydl.extract_info(url, download=False)

        title = info.get('title', 'Unknown')
        duration = info.get('duration', 0)
        video_id = info.get('id', 'unknown')

        print(f"   标题: {title}")
        print(f"   时长: {get_video_duration_display(duration)}")
        print(f"   视频ID: {video_id}")

        print(f"\n📥 开始下载...")
        info = ydl.extract_info(url, download=True)

        video_filename = ydl.prepare_filename(info)
        video_path = Path(video_filename)

        # 缩放到 1920x1080
        video_path = scale_to_1080p(video_path)
        file_size = video_path.stat().st_size if video_path.exists() else 0

        return {
            'video_path': str(video_path),
            'subtitle_path': None,
            'title': title,
            'duration': duration,
            'file_size': file_size,
            'video_id': video_id,
            'source_type': 'youtube'
        }


def download_twitter(url: str, output_dir: Path) -> dict:
    """下载 Twitter/X 视频（不下载字幕，统一用 Groq Whisper 转录）"""
    ydl_opts = {
        # 优先下载最高质量
        'format': 'best[ext=mp4]/best',
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
        'writesubtitles': False,
        'writeautomaticsub': False,
        'writethumbnail': False,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [_progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("\n📊 获取 Twitter 视频信息...")
        info = ydl.extract_info(url, download=False)

        title = info.get('title', info.get('description', 'Twitter Video')[:50])
        duration = info.get('duration', 0)
        video_id = info.get('id', 'unknown')

        print(f"   标题: {title}")
        print(f"   时长: {get_video_duration_display(duration) if duration else '未知'}")
        print(f"   视频ID: {video_id}")

        print(f"\n📥 开始下载...")
        info = ydl.extract_info(url, download=True)

        video_filename = ydl.prepare_filename(info)
        video_path = Path(video_filename)

        file_size = video_path.stat().st_size if video_path.exists() else 0

        # 如果没有获取到时长，用 ffprobe 获取
        if not duration and video_path.exists():
            duration = get_video_duration(str(video_path))

        # 缩放到 1920x1080
        video_path = scale_to_1080p(video_path)
        file_size = video_path.stat().st_size if video_path.exists() else 0

        return {
            'video_path': str(video_path),
            'subtitle_path': None,
            'title': title,
            'duration': duration,
            'file_size': file_size,
            'video_id': video_id,
            'source_type': 'twitter'
        }


def download_instagram(url: str, output_dir: Path) -> dict:
    """下载 Instagram 视频（不下载字幕，统一用 Groq Whisper 转录）"""
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
        'writesubtitles': False,
        'writeautomaticsub': False,
        'writethumbnail': False,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [_progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("\n📊 获取 Instagram 视频信息...")
        info = ydl.extract_info(url, download=False)

        title = info.get('title', info.get('description', 'Instagram Video')[:50])
        duration = info.get('duration', 0)
        video_id = info.get('id', 'unknown')

        print(f"   标题: {title}")
        print(f"   时长: {get_video_duration_display(duration) if duration else '未知'}")
        print(f"   视频ID: {video_id}")

        print(f"\n📥 开始下载...")
        info = ydl.extract_info(url, download=True)

        video_filename = ydl.prepare_filename(info)
        video_path = Path(video_filename)

        file_size = video_path.stat().st_size if video_path.exists() else 0

        # 如果没有获取到时长，用 ffprobe 获取
        if not duration and video_path.exists():
            duration = get_video_duration(str(video_path))

        # 缩放到 1920x1080
        video_path = scale_to_1080p(video_path)
        file_size = video_path.stat().st_size if video_path.exists() else 0

        return {
            'video_path': str(video_path),
            'subtitle_path': None,
            'title': title,
            'duration': duration,
            'file_size': file_size,
            'video_id': video_id,
            'source_type': 'instagram'
        }


def download_tiktok(url: str, output_dir: Path) -> dict:
    """下载 TikTok 视频（不下载字幕，统一用 Groq Whisper 转录）"""
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
        'writesubtitles': False,
        'writeautomaticsub': False,
        'writethumbnail': False,
        'quiet': False,
        'no_warnings': False,
        'progress_hooks': [_progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("\n📊 获取 TikTok 视频信息...")
        info = ydl.extract_info(url, download=False)

        title = info.get('title', info.get('description', 'TikTok Video')[:50])
        duration = info.get('duration', 0)
        video_id = info.get('id', 'unknown')

        print(f"   标题: {title}")
        print(f"   时长: {get_video_duration_display(duration) if duration else '未知'}")
        print(f"   视频ID: {video_id}")

        print(f"\n📥 开始下载...")
        info = ydl.extract_info(url, download=True)

        video_filename = ydl.prepare_filename(info)
        video_path = Path(video_filename)

        file_size = video_path.stat().st_size if video_path.exists() else 0

        # 如果没有获取到时长，用 ffprobe 获取
        if not duration and video_path.exists():
            duration = get_video_duration(str(video_path))

        # 缩放到 1920x1080
        video_path = scale_to_1080p(video_path)
        file_size = video_path.stat().st_size if video_path.exists() else 0

        return {
            'video_path': str(video_path),
            'subtitle_path': None,
            'title': title,
            'duration': duration,
            'file_size': file_size,
            'video_id': video_id,
            'source_type': 'tiktok'
        }


def process_local_video(path: str, output_dir: Path) -> dict:
    """处理本地视频文件"""
    source_path = Path(path).expanduser().resolve()

    if not source_path.exists():
        raise ValueError(f"本地视频文件不存在: {path}")

    # 复制到输出目录
    video_id = source_path.stem
    dest_path = output_dir / source_path.name

    print(f"\n📂 处理本地视频...")
    print(f"   源文件: {source_path}")

    if source_path != dest_path:
        print(f"   复制到: {dest_path}")
        shutil.copy2(source_path, dest_path)
    else:
        dest_path = source_path

    # 获取视频信息
    duration = get_video_duration(str(dest_path))
    file_size = dest_path.stat().st_size

    print(f"   时长: {get_video_duration_display(duration)}")
    print(f"   大小: {format_file_size(file_size)}")

    # 查找同名字幕文件
    subtitle_path = None
    for ext in ['.srt', '.vtt', '.ass', '.en.srt', '.en.vtt', '.zh.srt', '.zh.vtt']:
        potential_sub = source_path.with_suffix(ext)
        if potential_sub.exists():
            subtitle_path = potential_sub
            # 复制字幕到输出目录
            if source_path.parent != output_dir:
                dest_sub = output_dir / potential_sub.name
                shutil.copy2(potential_sub, dest_sub)
                subtitle_path = dest_sub
            break

    # 缩放到 1920x1080
    dest_path = scale_to_1080p(dest_path)
    file_size = dest_path.stat().st_size

    return {
        'video_path': str(dest_path),
        'subtitle_path': str(subtitle_path) if subtitle_path else None,
        'title': source_path.stem,
        'duration': duration,
        'file_size': file_size,
        'video_id': video_id,
        'source_type': 'local'
    }


def download_video(source: str, output_dir: str = None) -> dict:
    """
    下载或处理视频

    支持:
    - YouTube URL
    - Twitter/X URL
    - Instagram URL
    - TikTok URL
    - 本地视频文件路径

    Args:
        source: YouTube/Twitter/Instagram/TikTok URL 或本地文件路径
        output_dir: 输出目录，默认为当前目录

    Returns:
        dict: {
            'video_path': 视频文件路径,
            'subtitle_path': 字幕文件路径,
            'title': 视频标题,
            'duration': 视频时长（秒）,
            'file_size': 文件大小（字节）,
            'video_id': 视频ID,
            'source_type': 来源类型 ('youtube', 'twitter', 'instagram', 'tiktok', 'local')
        }

    Raises:
        ValueError: 无效的来源
        Exception: 下载/处理失败
    """
    # 检测来源类型
    source_type = detect_source_type(source)

    if source_type == 'unknown':
        raise ValueError(f"无法识别的来源: {source}\n支持: YouTube URL, Twitter/X URL, Instagram URL, TikTok URL, 或本地视频文件路径")

    # 设置输出目录
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)

    output_dir = ensure_directory(output_dir)

    source_names = {
        'youtube': 'YouTube',
        'twitter': 'Twitter/X',
        'instagram': 'Instagram',
        'tiktok': 'TikTok',
        'local': '本地文件'
    }

    print(f"🎬 开始处理视频...")
    print(f"   来源类型: {source_names[source_type]}")
    print(f"   输入: {source}")
    print(f"   输出目录: {output_dir}")

    try:
        if source_type == 'youtube':
            result = download_youtube(source, output_dir)
        elif source_type == 'twitter':
            result = download_twitter(source, output_dir)
        elif source_type == 'instagram':
            result = download_instagram(source, output_dir)
        elif source_type == 'tiktok':
            result = download_tiktok(source, output_dir)
        else:  # local
            result = process_local_video(source, output_dir)

        video_path = Path(result['video_path'])
        print(f"\n✅ 视频处理完成: {video_path.name}")
        print(f"   大小: {format_file_size(result['file_size'])}")
        print(f"   📝 下一步: 使用 Groq Whisper 转录字幕")

        return result

    except Exception as e:
        print(f"\n❌ 处理失败: {str(e)}")
        raise


def _progress_hook(d):
    """下载进度回调"""
    if d['status'] == 'downloading':
        # 显示下载进度
        if 'downloaded_bytes' in d and 'total_bytes' in d and d['total_bytes']:
            percent = d['downloaded_bytes'] / d['total_bytes'] * 100
            downloaded = format_file_size(d['downloaded_bytes'])
            total = format_file_size(d['total_bytes'])
            speed = d.get('speed', 0)
            speed_str = format_file_size(speed) + '/s' if speed else 'N/A'

            # 使用 \r 实现进度条覆盖
            bar_length = 30
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)

            print(f"\r   [{bar}] {percent:.1f}% - {downloaded}/{total} - {speed_str}", end='', flush=True)
        elif 'downloaded_bytes' in d:
            # 无总大小信息时，只显示已下载
            downloaded = format_file_size(d['downloaded_bytes'])
            speed = d.get('speed', 0)
            speed_str = format_file_size(speed) + '/s' if speed else 'N/A'
            print(f"\r   下载中... {downloaded} - {speed_str}", end='', flush=True)

    elif d['status'] == 'finished':
        print()  # 换行


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("Usage: python download_video.py <source> [output_dir]")
        print("\n支持的来源:")
        print("  - YouTube URL:    https://youtube.com/watch?v=xxx")
        print("  - Twitter URL:    https://x.com/user/status/xxx")
        print("  - Instagram URL:  https://www.instagram.com/reel/xxx")
        print("  - TikTok URL:     https://www.tiktok.com/@user/video/xxx")
        print("  - 本地文件:       /path/to/video.mp4")
        print("\nExamples:")
        print("  python download_video.py https://youtube.com/watch?v=Ckt1cj0xjRM")
        print("  python download_video.py https://x.com/user/status/123456789")
        print("  python download_video.py https://www.instagram.com/reel/ABC123/")
        print("  python download_video.py https://www.tiktok.com/@user/video/1234567890")
        print("  python download_video.py ~/Videos/my_video.mp4")
        print("  python download_video.py ~/Videos/my_video.mp4 ~/Downloads")
        sys.exit(1)

    source = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = download_video(source, output_dir)

        # 输出 JSON 结果（供其他脚本使用）
        print("\n" + "="*60)
        print("处理结果 (JSON):")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
