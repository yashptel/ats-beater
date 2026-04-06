import re


def parse_user_agent(ua: str | None) -> dict:
    """Parse a User-Agent string into platform, os, and browser."""
    if not ua:
        return {"platform": None, "os": None, "browser": None}

    # Platform detection (in-app browsers / social referrers)
    platform = None
    platform_patterns = [
        (r"WhatsApp", "WhatsApp"),
        (r"Telegram", "Telegram"),
        (r"Twitter|TwitterBot", "Twitter"),
        (r"LinkedInApp|LinkedInBot", "LinkedIn"),
        (r"FBAN|FBAV|Facebook", "Facebook"),
        (r"Slack", "Slack"),
        (r"Discord", "Discord"),
    ]
    for pattern, name in platform_patterns:
        if re.search(pattern, ua, re.IGNORECASE):
            platform = name
            break

    # OS detection
    os_name = None
    if re.search(r"iPhone|iPad|iPod", ua):
        os_name = "iOS"
    elif re.search(r"Android", ua):
        os_name = "Android"
    elif re.search(r"Windows", ua):
        os_name = "Windows"
    elif re.search(r"Macintosh|Mac OS", ua):
        os_name = "macOS"
    elif re.search(r"Linux", ua):
        os_name = "Linux"

    # Browser detection (order matters — specific before generic)
    browser = None
    if re.search(r"Edg(e|/)", ua):
        browser = "Edge"
    elif re.search(r"OPR|Opera", ua):
        browser = "Opera"
    elif re.search(r"SamsungBrowser", ua):
        browser = "Samsung"
    elif re.search(r"Firefox", ua):
        browser = "Firefox"
    elif re.search(r"CriOS|Chrome(?!.*Edg)", ua):
        browser = "Chrome"
    elif re.search(r"Safari(?!.*Chrome)", ua):
        browser = "Safari"

    return {"platform": platform, "os": os_name, "browser": browser}
