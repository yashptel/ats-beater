import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path
from app.config import get_settings
from app.exceptions import LaTeXCompilationError
from logging import getLogger

logger = getLogger(__name__)

RESUME_CLS_PATH = Path(__file__).parent.parent.parent.parent / "resume.cls"
PDFLATEX_TIMEOUT = 90  # seconds per pass
PDFLATEX_PASSES = 2  # two passes for hyperref bookmarks/cross-references


def _extract_errors(log_text: str) -> str:
    """Extract meaningful error lines from pdflatex log output.

    Looks for lines starting with '!' (LaTeX errors) and grabs surrounding context.
    Falls back to the last 20 lines if no '!' errors are found.
    """
    lines = log_text.splitlines()
    error_blocks = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("!"):
            # Grab the error line + up to 4 lines of context after it
            block = lines[i : i + 5]
            error_blocks.append("\n".join(block))
            i += 5
        else:
            i += 1

    if error_blocks:
        return "\n\n".join(error_blocks)

    # No '!' errors — check for common warning patterns
    warnings = [l for l in lines if re.search(r"(Undefined|Missing|Too many|Emergency stop)", l)]
    if warnings:
        return "\n".join(warnings[:10])

    # Last resort: tail of log
    return "\n".join(lines[-20:])


async def _run_pdflatex(tmp_path: Path, env: dict, pass_num: int) -> tuple[int, bytes, bytes]:
    """Run a single pdflatex pass. Returns (returncode, stdout, stderr)."""
    process = await asyncio.create_subprocess_exec(
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "resume.tex",
        cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=PDFLATEX_TIMEOUT)
    except asyncio.TimeoutError:
        process.kill()
        raise LaTeXCompilationError(f"LaTeX compilation timed out on pass {pass_num} (>{PDFLATEX_TIMEOUT}s)")

    return process.returncode, stdout, stderr


async def compile_latex(latex_code: str) -> bytes:
    """Compile LaTeX code to PDF bytes.

    Runs pdflatex twice for proper cross-references and hyperref bookmarks.
    Raises LaTeXCompilationError on failure.
    """
    settings = get_settings()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Copy resume.cls into temp directory
        cls_dest = tmp_path / "resume.cls"
        if RESUME_CLS_PATH.exists():
            shutil.copy2(str(RESUME_CLS_PATH), str(cls_dest))
        else:
            raise LaTeXCompilationError(f"resume.cls not found at {RESUME_CLS_PATH}")

        # Write .tex file
        tex_path = tmp_path / "resume.tex"
        tex_path.write_text(latex_code, encoding="utf-8")

        # Ensure pdflatex is in PATH
        tex_bin_path = settings.LATEX_BIN_PATH
        env = os.environ.copy()
        if tex_bin_path not in env.get("PATH", ""):
            env["PATH"] = tex_bin_path + os.pathsep + env.get("PATH", "")

        pdf_path = tmp_path / "resume.pdf"
        log_path = tmp_path / "resume.log"

        # Run pdflatex twice (cross-references + hyperref bookmarks)
        for pass_num in range(1, PDFLATEX_PASSES + 1):
            returncode, stdout, stderr = await _run_pdflatex(tmp_path, env, pass_num)

            if returncode != 0:
                # Check if PDF was still produced despite errors (common with nonstopmode warnings)
                if pdf_path.exists() and pdf_path.stat().st_size > 0:
                    logger.warning(f"pdflatex pass {pass_num} returned {returncode} but PDF exists, continuing")
                else:
                    # Read log file for better error diagnostics
                    if log_path.exists():
                        log_text = log_path.read_text(encoding="utf-8", errors="replace")
                        error_detail = _extract_errors(log_text)
                    else:
                        stdout_str = stdout.decode("utf-8", errors="replace")
                        error_detail = _extract_errors(stdout_str)

                    logger.error(f"LaTeX compilation failed on pass {pass_num}:\n{error_detail}")
                    raise LaTeXCompilationError(f"LaTeX compilation failed:\n{error_detail}")

        if not pdf_path.exists():
            raise LaTeXCompilationError("PDF file not found after compilation")

        return pdf_path.read_bytes()
