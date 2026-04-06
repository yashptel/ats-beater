from app.services.latex.sanitizer import (
    convert_markdown_emphasis,
    handle_special_chars,
    sanitize_special_chars,
    strip_markdown_emphasis,
)


def test_handle_special_chars_basic():
    assert handle_special_chars("Hello & World") == r"Hello \& World"
    assert handle_special_chars("50%") == r"50\%"
    assert handle_special_chars("$100") == r"\$100"
    assert handle_special_chars("item #1") == r"item \#1"
    assert handle_special_chars("under_score") == r"under\_score"


def test_handle_special_chars_braces():
    assert handle_special_chars("{test}") == r"\{test\}"


def test_sanitize_special_chars_nested():
    data = {
        "name": "John & Jane",
        "items": ["100%", "$50"],
        "nested": {"key": "val_ue"},
    }
    result = sanitize_special_chars(data)
    assert result["name"] == r"John \& Jane"
    assert result["items"][0] == r"100\%"
    assert result["items"][1] == r"\$50"
    assert result["nested"]["key"] == r"val\_ue"


def test_sanitize_special_chars_non_string():
    assert sanitize_special_chars(42) == 42
    assert sanitize_special_chars(None) is None


def test_asterisk_not_escaped():
    """Asterisks pass through handle_special_chars untouched."""
    assert handle_special_chars("**bold**") == "**bold**"
    assert handle_special_chars("*italic*") == "*italic*"


def test_convert_markdown_bold():
    assert convert_markdown_emphasis("**Redis**") == r"\textbf{Redis}"


def test_convert_markdown_italic():
    assert convert_markdown_emphasis("*emphasis*") == r"\textit{emphasis}"


def test_convert_markdown_mixed():
    result = convert_markdown_emphasis("**bold** and *italic*")
    assert result == r"\textbf{bold} and \textit{italic}"


def test_convert_markdown_with_special_chars():
    """Sanitizer runs first, then emphasis conversion — escaped chars inside bold work."""
    text = "**40%**"
    sanitized = handle_special_chars(text)  # → "**40\%**"
    result = convert_markdown_emphasis(sanitized)
    assert result == r"\textbf{40\%}"


def test_convert_no_markers():
    """Plain text without markers passes through unchanged."""
    assert convert_markdown_emphasis("plain text here") == "plain text here"


def test_convert_empty_string():
    assert convert_markdown_emphasis("") == ""


def test_convert_multiple_bold():
    """Multiple bold segments on the same line all convert."""
    result = convert_markdown_emphasis("Used **Redis** and **PostgreSQL** for caching")
    assert result == r"Used \textbf{Redis} and \textbf{PostgreSQL} for caching"


def test_convert_unclosed_bold():
    """Unclosed bold markers are left as-is (no conversion)."""
    assert convert_markdown_emphasis("**unclosed bold") == "**unclosed bold"


def test_convert_lone_asterisk():
    """A single asterisk with no matching pair is left as-is."""
    assert convert_markdown_emphasis("5 * 3 = 15") == "5 * 3 = 15"


def test_convert_triple_asterisk():
    """Triple asterisks (***text***) produce nested bold+italic."""
    result = convert_markdown_emphasis("***bold italic***")
    assert result == r"\textbf{\textit{bold italic}}"


def test_convert_adjacent_bold_italic():
    """Adjacent **bold** immediately followed by *italic* both convert."""
    result = convert_markdown_emphasis("**bold** *italic*")
    assert result == r"\textbf{bold} \textit{italic}"


def test_convert_bold_with_spaces_inside():
    """Bold content can contain spaces."""
    result = convert_markdown_emphasis("**multiple words here**")
    assert result == r"\textbf{multiple words here}"


def test_convert_with_escaped_braces():
    """Emphasis conversion works on text that already has escaped braces from sanitizer."""
    # Simulates: original "{config}" → sanitized "\{config\}" → then emphasis conversion
    text = r"Deployed \{config\} with **Kubernetes**"
    result = convert_markdown_emphasis(text)
    assert result == r"Deployed \{config\} with \textbf{Kubernetes}"


def test_strip_markdown_emphasis():
    assert strip_markdown_emphasis("**bold** and *italic*") == "bold and italic"
    assert strip_markdown_emphasis("no markers") == "no markers"


def test_strip_triple_asterisk():
    assert strip_markdown_emphasis("***bold italic***") == "bold italic"


def test_strip_empty_string():
    assert strip_markdown_emphasis("") == ""
