"""Unit tests for platform-aware proxy routing in sources._yt_proxy_for_url."""
import os

import pytest

from meeting_intelligence import sources


class TestYtProxyForUrl:
    """Proxy routing: YouTube → MEETING_YT_PROXY, VK/Rutube/unknown → direct."""

    def test_youtube_uses_default_socks_proxy(self):
        saved = os.environ.pop("MEETING_YT_PROXY", None)
        try:
            assert sources._yt_proxy_for_url(
                "https://www.youtube.com/watch?v=abc"
            ) == "socks5://127.0.0.1:12334"
        finally:
            if saved is not None:
                os.environ["MEETING_YT_PROXY"] = saved

    def test_youtube_honors_env_override(self):
        os.environ["MEETING_YT_PROXY"] = "socks5://127.0.0.1:9999"
        try:
            assert sources._yt_proxy_for_url(
                "https://youtu.be/xyz"
            ) == "socks5://127.0.0.1:9999"
        finally:
            del os.environ["MEETING_YT_PROXY"]

    def test_youtube_mobile_and_music_subdomains(self):
        for url in (
            "https://m.youtube.com/watch?v=1",
            "https://music.youtube.com/watch?v=2",
        ):
            assert sources._yt_proxy_for_url(url) == "socks5://127.0.0.1:12334"

    @pytest.mark.parametrize(
        "url",
        [
            "https://vkvideo.ru/video-59405817_456240137",
            "https://vk.com/video123",
            "https://vk.ru/video456",
            "https://rutube.ru/video/c063a37d69982b0f54965b5cb1bc553b/",
            "https://www.rutube.ru/watch/abc",
            "https://example.com/some/video",
            "https://dion.vc/video/84eedcc0",
        ],
    )
    def test_direct_or_unknown_domains_empty_proxy(self, url):
        # Remove env override so the test asserts pure routing, not env leakage.
        saved = os.environ.pop("MEETING_YT_PROXY", None)
        try:
            assert sources._yt_proxy_for_url(url) == ""
        finally:
            if saved is not None:
                os.environ["MEETING_YT_PROXY"] = saved
