import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if os.name == "nt":
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    os.environ.setdefault(
        "HF_HOME",
        str(Path(__file__).resolve().parents[2] / ".model-cache"),
    )


class EmptyDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    section: str | None
    page: int | None
    chunk_hash: str


def _page_number(chunk: Any) -> int | None:
    for item in chunk.meta.doc_items:
        if item.prov:
            return int(item.prov[0].page_no)
    return None


def _section(chunk: Any) -> str | None:
    if not chunk.meta.headings:
        return None
    return " > ".join(heading.strip() for heading in chunk.meta.headings if heading.strip()) or None


def parse_and_chunk(path: Path, chunk_size: int, overlap: int) -> list[ParsedChunk]:
    import tiktoken
    from docling.chunking import HybridChunker
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.settings import InferenceSettings, scoped
    from docling.document_converter import DocumentConverter
    from docling_core.transforms.chunker import DocChunk
    from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

    with scoped(inference=InferenceSettings(compile_torch_models=False)):
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.PPTX, InputFormat.MD]
        )
        conversion = converter.convert(path)
    encoding = tiktoken.get_encoding("cl100k_base")
    tokenizer = OpenAITokenizer(
        tokenizer=encoding,
        max_tokens=chunk_size - overlap,
    )
    chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)

    chunks: list[ParsedChunk] = []
    previous_tokens: list[int] = []
    for raw_chunk in chunker.chunk(conversion.document):
        if not isinstance(raw_chunk, DocChunk):
            continue
        text = raw_chunk.text.strip()
        if not text:
            continue
        tokens = encoding.encode(text)
        if previous_tokens and overlap:
            overlap_text = encoding.decode(previous_tokens[-overlap:]).strip()
            if overlap_text:
                text = f"{overlap_text}\n{text}"
        final_tokens = encoding.encode(text)
        if len(final_tokens) > chunk_size:
            final_tokens = final_tokens[:chunk_size]
            text = encoding.decode(final_tokens).strip()
        chunks.append(
            ParsedChunk(
                text=text,
                section=_section(raw_chunk),
                page=_page_number(raw_chunk),
                chunk_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
        previous_tokens = tokens

    if not chunks:
        raise EmptyDocumentError("No readable text was found in the document.")
    return chunks
