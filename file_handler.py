import base64
import os
from typing import Optional

# File extensions by category
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
PDF_EXTS = {".pdf"}
WORD_EXTS = {".docx"}
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".toml", ".ini", ".xml", ".html"}
CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".rb", ".rs", ".swift", ".kt", ".sh", ".bash", ".zsh",
    ".sql", ".r", ".m", ".scala", ".php",
}

MAX_TEXT_CHARS = 20_000  # truncate very large files to avoid overflowing context


def get_file_category(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in WORD_EXTS:
        return "word"
    if ext in TEXT_EXTS:
        return "text"
    if ext in CODE_EXTS:
        return "code"
    return "unsupported"


def _ext_to_mime(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except ImportError:
        return "[pypdf not installed — cannot extract PDF text]"
    except Exception as e:
        return f"[PDF extraction error: {e}]"


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document
        import io
        doc = Document(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        return "[python-docx not installed — cannot extract Word text]"
    except Exception as e:
        return f"[DOCX extraction error: {e}]"


def _truncate(text: str) -> str:
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS] + f"\n\n[... truncated at {MAX_TEXT_CHARS} characters ...]"
    return text


def build_image_message(data: bytes, filename: str, caption: Optional[str]) -> dict:
    mime = _ext_to_mime(filename)
    b64 = base64.b64encode(data).decode("utf-8")
    image_url = f"data:{mime};base64,{b64}"

    content = []
    if caption:
        content.append({"type": "text", "text": caption})
    else:
        content.append({"type": "text", "text": "What can you tell me about this image?"})
    content.append({"type": "image_url", "image_url": {"url": image_url}})

    return {"role": "user", "content": content}


def build_text_message(extracted: str, filename: str, caption: Optional[str], category: str) -> dict:
    extracted = _truncate(extracted)

    if category == "code":
        ext = os.path.splitext(filename)[1].lstrip(".")
        file_block = f"```{ext}\n{extracted}\n```"
    else:
        file_block = extracted

    if caption:
        text = f"{caption}\n\n**File: {filename}**\n\n{file_block}"
    else:
        text = f"**File: {filename}**\n\n{file_block}"

    return {"role": "user", "content": text}


def process_file(data: bytes, filename: str, caption: Optional[str]) -> dict:
    """
    Returns a message dict ready to append to the session.
    Raises ValueError for unsupported file types.
    """
    category = get_file_category(filename)

    if category == "image":
        return build_image_message(data, filename, caption)

    if category == "pdf":
        extracted = _extract_pdf(data)
    elif category == "word":
        extracted = _extract_docx(data)
    elif category in ("text", "code"):
        try:
            extracted = data.decode("utf-8")
        except UnicodeDecodeError:
            extracted = data.decode("latin-1", errors="replace")
    else:
        supported = sorted(IMAGE_EXTS | PDF_EXTS | WORD_EXTS | TEXT_EXTS | CODE_EXTS)
        raise ValueError(
            f"지원하지 않는 파일 형식이에요.\n"
            f"지원 형식: {', '.join(supported)}"
        )

    return build_text_message(extracted, filename, caption, category)
