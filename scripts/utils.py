#!/usr/bin/env python3
"""
通用工具函数
提供时间格式转换、文件名清理、路径处理等功能
"""

import re
import os
from pathlib import Path
from datetime import datetime


def time_to_seconds(time_str: str) -> float:
    """
    将时间字符串转换为秒数

    支持格式:
    - HH:MM:SS.mmm
    - MM:SS.mmm
    - SS.mmm

    Args:
        time_str: 时间字符串

    Returns:
        float: 秒数

    Examples:
        >>> time_to_seconds("01:23:45.678")
        5025.678
        >>> time_to_seconds("23:45.678")
        1425.678
        >>> time_to_seconds("45.678")
        45.678
    """
    # 移除空格
    time_str = time_str.strip()

    # 分割时间部分
    parts = time_str.split(':')

    if len(parts) == 3:
        # HH:MM:SS.mmm
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        # MM:SS.mmm
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    else:
        # SS.mmm
        return float(parts[0])


def seconds_to_time(seconds: float, include_hours: bool = True, use_comma: bool = False) -> str:
    """
    将秒数转换为时间字符串

    Args:
        seconds: 秒数
        include_hours: 是否包含小时（即使为0）
        use_comma: 使用逗号分隔毫秒（SRT 格式需要）

    Returns:
        str: 时间字符串

    Examples:
        >>> seconds_to_time(5025.678)
        '01:23:45.678'
        >>> seconds_to_time(1425.678, include_hours=False)
        '23:45.678'
        >>> seconds_to_time(5025.678, use_comma=True)
        '01:23:45,678'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    separator = ',' if use_comma else '.'

    if include_hours or hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', separator)
    else:
        return f"{minutes:02d}:{secs:06.3f}".replace('.', separator)


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    清理文件名，移除非法字符

    Args:
        filename: 原始文件名
        max_length: 最大长度

    Returns:
        str: 清理后的文件名

    Examples:
        >>> sanitize_filename("Hello: World?")
        'Hello_World'
        >>> sanitize_filename("AGI 不是时间点，是指数曲线")
        'AGI_不是时间点_是指数曲线'
    """
    # 移除或替换非法字符
    # Windows/Mac/Linux 通用的非法字符
    illegal_chars = r'[<>:"/\\|?*]'
    filename = re.sub(illegal_chars, '_', filename)

    # 移除开头和结尾的空格和点
    filename = filename.strip('. ')

    # 替换空格为下划线
    filename = filename.replace(' ', '_')

    # 移除连续的下划线
    filename = re.sub(r'_+', '_', filename)

    # 限制长度
    if len(filename) > max_length:
        # 保留扩展名
        name, ext = os.path.splitext(filename)
        if ext:
            max_name_length = max_length - len(ext)
            filename = name[:max_name_length] + ext
        else:
            filename = filename[:max_length]

    return filename


def create_output_dir(base_dir: str = None) -> Path:
    """
    创建输出目录（带时间戳）

    Args:
        base_dir: 基础目录，默认为当前工作目录下的 youtube-clips

    Returns:
        Path: 输出目录路径

    Examples:
        >>> create_output_dir()
        PosixPath('/path/to/current/dir/youtube-clips/20260121_143022')
    """
    if base_dir is None:
        base_dir = Path.cwd() / "youtube-clips"
    else:
        base_dir = Path(base_dir)

    # 创建带时间戳的子目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base_dir / timestamp

    # 创建目录
    output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为人类可读格式

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        str: 格式化后的大小

    Examples:
        >>> format_file_size(1024)
        '1.0 KB'
        >>> format_file_size(1536)
        '1.5 KB'
        >>> format_file_size(1048576)
        '1.0 MB'
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def parse_time_range(time_range: str) -> tuple:
    """
    解析时间范围字符串

    Args:
        time_range: 时间范围字符串，如 "00:00 - 03:15" 或 "00:00-03:15"

    Returns:
        tuple: (start_seconds, end_seconds)

    Examples:
        >>> parse_time_range("00:00 - 03:15")
        (0.0, 195.0)
        >>> parse_time_range("01:30:00-01:33:15")
        (5400.0, 5595.0)
    """
    # 移除空格并分割
    parts = time_range.replace(' ', '').split('-')
    if len(parts) != 2:
        raise ValueError(f"Invalid time range format: {time_range}")

    start_time = time_to_seconds(parts[0])
    end_time = time_to_seconds(parts[1])

    if start_time >= end_time:
        raise ValueError(f"Start time must be before end time: {time_range}")

    return start_time, end_time


def adjust_subtitle_time(time_seconds: float, offset: float) -> float:
    """
    调整字幕时间戳（用于剪辑后的字幕）

    Args:
        time_seconds: 原始时间（秒）
        offset: 偏移量（秒），通常是剪辑起始时间

    Returns:
        float: 调整后的时间

    Examples:
        >>> adjust_subtitle_time(125.5, 120.0)
        5.5
    """
    adjusted = time_seconds - offset
    return max(0.0, adjusted)  # 确保不为负数


def get_video_duration_display(seconds: float) -> str:
    """
    获取视频时长的显示格式

    Args:
        seconds: 时长（秒）

    Returns:
        str: 格式化的时长

    Examples:
        >>> get_video_duration_display(125.5)
        '02:05'
        >>> get_video_duration_display(3725.5)
        '1:02:05'
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def sanitize_error_message(msg: str) -> str:
    """
    清理错误消息中的敏感信息（如 API Key）

    Args:
        msg: 原始错误消息

    Returns:
        str: 脱敏后的消息
    """
    # 匹配 gsk_ 开头的 Groq API Key（通常为 gsk_ + 一串字母数字）
    sanitized = re.sub(r'gsk_[A-Za-z0-9_-]+', 'gsk_***REDACTED***', msg)

    # 同时脱敏环境变量中的原始 API Key 值（如果出现在错误信息中）
    raw_key = os.environ.get('GROQ_API_KEY', '').strip()
    if raw_key and len(raw_key) > 8 and raw_key in sanitized:
        sanitized = sanitized.replace(raw_key, 'gsk_***REDACTED***')

    return sanitized


def validate_url(url: str) -> bool:
    """
    验证 YouTube URL 格式

    Args:
        url: YouTube URL

    Returns:
        bool: 是否有效

    Examples:
        >>> validate_url("https://youtube.com/watch?v=Ckt1cj0xjRM")
        True
        >>> validate_url("https://youtu.be/Ckt1cj0xjRM")
        True
        >>> validate_url("invalid_url")
        False
    """
    # 支持的 YouTube URL 格式
    patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'https?://(?:www\.)?youtu\.be/[\w-]+',
        r'https?://(?:www\.)?youtube\.com/embed/[\w-]+',
    ]

    return any(re.match(pattern, url) for pattern in patterns)


def validate_twitter_url(url: str) -> bool:
    """
    验证 Twitter/X URL 格式

    Args:
        url: Twitter/X URL

    Returns:
        bool: 是否有效

    Examples:
        >>> validate_twitter_url("https://twitter.com/user/status/123456")
        True
        >>> validate_twitter_url("https://x.com/user/status/123456")
        True
        >>> validate_twitter_url("invalid_url")
        False
    """
    patterns = [
        r'https?://(?:www\.)?twitter\.com/\w+/status/\d+',
        r'https?://(?:www\.)?x\.com/\w+/status/\d+',
        r'https?://(?:www\.)?twitter\.com/i/status/\d+',
        r'https?://(?:www\.)?x\.com/i/status/\d+',
    ]

    return any(re.match(pattern, url) for pattern in patterns)


def validate_instagram_url(url: str) -> bool:
    """
    验证 Instagram URL 格式

    Args:
        url: Instagram URL

    Returns:
        bool: 是否有效

    Examples:
        >>> validate_instagram_url("https://www.instagram.com/p/ABC123/")
        True
        >>> validate_instagram_url("https://www.instagram.com/reel/ABC123/")
        True
        >>> validate_instagram_url("https://www.instagram.com/tv/ABC123/")
        True
        >>> validate_instagram_url("https://instagr.am/p/ABC123/")
        True
        >>> validate_instagram_url("invalid_url")
        False
    """
    patterns = [
        r'https?://(?:www\.)?instagram\.com/p/[\w-]+',
        r'https?://(?:www\.)?instagram\.com/reel/[\w-]+',
        r'https?://(?:www\.)?instagram\.com/tv/[\w-]+',
        r'https?://(?:www\.)?instagr\.am/[\w-]+',
    ]

    return any(re.match(pattern, url) for pattern in patterns)


def validate_tiktok_url(url: str) -> bool:
    """
    验证 TikTok URL 格式

    Args:
        url: TikTok URL

    Returns:
        bool: 是否有效

    Examples:
        >>> validate_tiktok_url("https://www.tiktok.com/@user/video/1234567890")
        True
        >>> validate_tiktok_url("https://vm.tiktok.com/ABC123/")
        True
        >>> validate_tiktok_url("https://vt.tiktok.com/ABC123/")
        True
        >>> validate_tiktok_url("invalid_url")
        False
    """
    patterns = [
        r'https?://(?:www\.)?tiktok\.com/@[\w.]+/video/\d+',
        r'https?://vm\.tiktok\.com/[\w-]+',
        r'https?://vt\.tiktok\.com/[\w-]+',
    ]

    return any(re.match(pattern, url) for pattern in patterns)


def validate_local_video(path: str) -> bool:
    """
    验证本地视频文件是否存在且格式有效

    Args:
        path: 本地文件路径

    Returns:
        bool: 是否有效

    Examples:
        >>> validate_local_video("/path/to/video.mp4")
        True  # if file exists
        >>> validate_local_video("/nonexistent/video.mp4")
        False
    """
    video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v'}

    path = Path(path).expanduser().resolve()

    if not path.exists():
        return False

    if not path.is_file():
        return False

    return path.suffix.lower() in video_extensions


def detect_source_type(source: str) -> str:
    """
    检测输入源的类型

    Args:
        source: URL 或本地路径

    Returns:
        str: 'youtube', 'twitter', 'instagram', 'tiktok', 'local', 或 'unknown'

    Examples:
        >>> detect_source_type("https://youtube.com/watch?v=abc123")
        'youtube'
        >>> detect_source_type("https://x.com/user/status/123")
        'twitter'
        >>> detect_source_type("https://www.instagram.com/reel/ABC123/")
        'instagram'
        >>> detect_source_type("https://www.tiktok.com/@user/video/123")
        'tiktok'
        >>> detect_source_type("/path/to/video.mp4")
        'local'
    """
    if validate_url(source):
        return 'youtube'
    elif validate_twitter_url(source):
        return 'twitter'
    elif validate_instagram_url(source):
        return 'instagram'
    elif validate_tiktok_url(source):
        return 'tiktok'
    elif validate_local_video(source):
        return 'local'
    else:
        return 'unknown'


def ensure_directory(path: Path) -> Path:
    """
    确保目录存在，不存在则创建

    Args:
        path: 目录路径

    Returns:
        Path: 目录路径
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


if __name__ == "__main__":
    # 测试代码
    print("Testing utils.py...")

    # 测试时间转换
    assert time_to_seconds("01:23:45.678") == 5025.678
    assert time_to_seconds("23:45.678") == 1425.678
    assert time_to_seconds("45.678") == 45.678

    # 测试文件名清理
    assert sanitize_filename("Hello: World?") == "Hello_World"
    assert sanitize_filename("AGI 不是时间点，是指数曲线") == "AGI_不是时间点_是指数曲线"

    # 测试时间范围解析
    assert parse_time_range("00:00 - 03:15") == (0.0, 195.0)
    assert parse_time_range("01:30:00-01:33:15") == (5400.0, 5595.0)

    # 测试 URL 验证
    assert validate_url("https://youtube.com/watch?v=Ckt1cj0xjRM") == True
    assert validate_url("https://youtu.be/Ckt1cj0xjRM") == True
    assert validate_url("invalid_url") == False

    print("✅ All tests passed!")
