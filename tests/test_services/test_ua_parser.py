from app.services.roast.ua_parser import parse_user_agent


def test_parse_none():
    result = parse_user_agent(None)
    assert result == {"platform": None, "os": None, "browser": None}


def test_parse_empty():
    result = parse_user_agent("")
    assert result == {"platform": None, "os": None, "browser": None}


def test_chrome_windows():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    result = parse_user_agent(ua)
    assert result["platform"] is None
    assert result["os"] == "Windows"
    assert result["browser"] == "Chrome"


def test_safari_ios():
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    result = parse_user_agent(ua)
    assert result["platform"] is None
    assert result["os"] == "iOS"
    assert result["browser"] == "Safari"


def test_whatsapp_android():
    ua = "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 WhatsApp/2.24.1.6"
    result = parse_user_agent(ua)
    assert result["platform"] == "WhatsApp"
    assert result["os"] == "Android"
    assert result["browser"] == "Chrome"


def test_linkedin_inapp():
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/21A329 [LinkedInApp]"
    result = parse_user_agent(ua)
    assert result["platform"] == "LinkedIn"
    assert result["os"] == "iOS"


def test_twitter_bot():
    ua = "Twitterbot/1.0"
    result = parse_user_agent(ua)
    assert result["platform"] == "Twitter"


def test_edge_windows():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    result = parse_user_agent(ua)
    assert result["os"] == "Windows"
    assert result["browser"] == "Edge"


def test_firefox_linux():
    ua = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
    result = parse_user_agent(ua)
    assert result["os"] == "Linux"
    assert result["browser"] == "Firefox"


def test_safari_macos():
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    result = parse_user_agent(ua)
    assert result["os"] == "macOS"
    assert result["browser"] == "Safari"


def test_facebook_inapp():
    ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 FBAN/FBIOS;FBAV/438.0"
    result = parse_user_agent(ua)
    assert result["platform"] == "Facebook"
    assert result["os"] == "iOS"


def test_telegram():
    ua = "TelegramBot (like TwitterBot)"
    result = parse_user_agent(ua)
    assert result["platform"] == "Telegram"
