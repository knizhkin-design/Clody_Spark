#!/usr/bin/env python3
"""
Индексатор корпуса Клоди Спарк.
Поддерживает corpus-annotations.md и ЖЖ-посты (lj/).

Стратегия чанкинга:
    < SHORT    символов → embed напрямую (full_text)
    >= SHORT   символов → разбить на абзацы, каждый абзац:
                              < SHORT  → embed напрямую
                              >= SHORT → аннотация через GPT-4o-mini → embed

Использование:
    python scripts/indexer.py                        # корпус
    python scripts/indexer.py --source lj            # ЖЖ-посты
    python scripts/indexer.py --source lj --limit 50 # первые 50 постов (тест)
    python scripts/indexer.py --stats
    python scripts/indexer.py --search "запрос"
"""

import json
import re
import sys
import argparse
from pathlib import Path

import chromadb
from openai import OpenAI

# ── Константы ─────────────────────────────────────────────────────────────────

CONFIG_FILE     = Path.home() / ".config/clody_spark/openai.json"
CHROMA_DIR      = Path.home() / ".config/clody_spark/chroma"
REPO_ROOT       = Path(__file__).parent.parent
CORPUS_FILE     = REPO_ROOT / "corpus-annotations.md"
LJ_DIR          = REPO_ROOT / "lj"
COLLECTION_NAME = "clody_spark"

SHORT = 600   # символов — порог: короткий текст кладём как есть


# ── Инфраструктура ────────────────────────────────────────────────────────────

def load_api_key() -> str:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)["api_key"]


def get_collection(client=None):
    if client is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def embed(texts: list[str], oai: OpenAI) -> list[list[float]]:
    response = oai.embeddings.create(
        model="text-embedding-3-large",
        input=texts,
    )
    return [item.embedding for item in response.data]


def annotate(text: str, oai: OpenAI, context: str = "") -> str:
    """Краткая аннотация через GPT-4o-mini. context — подсказка (дата, заголовок)."""
    system = (
        "Ты помогаешь индексировать тексты из дневника. "
        "Напиши очень краткую аннотацию (2–4 предложения) для семантического поиска: "
        "о чём текст, какие ключевые идеи, настроение. Без вступлений."
    )
    user = f"{context}\n\n{text}".strip() if context else text
    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        max_tokens=200,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


# ── Чанкинг ───────────────────────────────────────────────────────────────────

def split_paragraphs(text: str) -> list[str]:
    """Делит на абзацы, склеивает слишком короткие с соседом."""
    raw    = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    merged = []
    buf    = ""
    for p in raw:
        if buf and len(buf) + len(p) + 2 < SHORT // 2:
            buf += "\n\n" + p          # склеиваем короткие
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)
    return merged


def get_embed_items(
    doc_id: str,
    text: str,
    meta_base: dict,
    oai: OpenAI,
    context: str = "",
) -> list[dict]:
    """
    Возвращает список готовых к записи чанков:
    [{"id": ..., "embed_text": ..., "document": ..., "metadata": ...}]
    """
    text = text.strip()
    if not text:
        return []

    if len(text) < SHORT:
        # Короткий — берём как есть
        return [{
            "id":         doc_id,
            "embed_text": text,
            "document":   text,
            "metadata":   {**meta_base, "strategy": "full_text", "chunk": 0},
        }]

    # Длинный — разбиваем на абзацы
    paragraphs = split_paragraphs(text)

    if len(paragraphs) == 1:
        # Единый длинный абзац — одна аннотация
        ann = annotate(text, oai, context)
        return [{
            "id":         doc_id,
            "embed_text": ann,
            "document":   text[:500],   # preview для отображения
            "metadata":   {**meta_base, "strategy": "annotation", "chunk": 0},
        }]

    # Несколько абзацев — каждый независимо
    items = []
    for i, para in enumerate(paragraphs):
        chunk_id = f"{doc_id}__c{i}"
        if len(para) < SHORT:
            items.append({
                "id":         chunk_id,
                "embed_text": para,
                "document":   para,
                "metadata":   {**meta_base, "strategy": "full_text", "chunk": i},
            })
        else:
            ann = annotate(para, oai, context)
            items.append({
                "id":         chunk_id,
                "embed_text": ann,
                "document":   para[:500],
                "metadata":   {**meta_base, "strategy": "annotation", "chunk": i},
            })
    return items


# ── Источник: corpus-annotations.md ──────────────────────────────────────────

def parse_corpus_annotations(path: Path) -> list[dict]:
    text    = path.read_text(encoding="utf-8")
    entries = []
    current_section = ""

    for line in text.splitlines():
        m = re.match(r"^## (.+)", line)
        if m:
            current_section = m.group(1).strip()
            continue
        m = re.match(r"^\*\*(.+?)\*\* — \*(.+?)\*", line)
        if m:
            entries.append({
                "id": m.group(1).strip(), "title": m.group(2).strip(),
                "section": current_section, "annotation": "", "_pending": True,
            })
            continue
        if entries and entries[-1].get("_pending") and line.strip():
            entries[-1]["annotation"] = line.strip()
            entries[-1]["_pending"]   = False

    for e in entries:
        e.pop("_pending", None)
    return [e for e in entries if e["annotation"]]


def index_corpus(oai: OpenAI, collection, verbose=True):
    entries      = parse_corpus_annotations(CORPUS_FILE)
    existing_ids = set(collection.get(include=[])["ids"])
    new_entries  = [e for e in entries if e["id"] not in existing_ids]

    if verbose:
        print(f"Корпус: найдено {len(entries)}, новых {len(new_entries)}")
    if not new_entries:
        return

    texts   = [e["annotation"] for e in new_entries]
    vectors = embed(texts, oai)

    collection.add(
        ids        = [e["id"] for e in new_entries],
        embeddings = vectors,
        documents  = [e["annotation"] for e in new_entries],
        metadatas  = [
            {"title": e["title"], "section": e["section"],
             "source": "corpus", "strategy": "annotation", "chunk": 0}
            for e in new_entries
        ],
    )
    if verbose:
        print(f"Корпус: добавлено {len(new_entries)}. Итого в базе: {collection.count()}")


# ── Источник: lj/ ────────────────────────────────────────────────────────────

def parse_lj_post(path: Path) -> dict | None:
    """Парсит один ЖЖ-пост. Возвращает None если пост пустой."""
    raw  = path.read_text(encoding="utf-8")
    # Хедер / тело
    if "---" in raw:
        header, _, body = raw.partition("---")
    else:
        header, body = "", raw

    # Заголовок
    title_m = re.search(r"^# (.+)", header, re.MULTILINE)
    title   = title_m.group(1).strip() if title_m else ""
    if title == "(без заголовка)":
        title = ""

    # Дата
    date_m = re.search(r"\*\*Дата:\*\*\s*(.+)", header)
    date   = date_m.group(1).strip() if date_m else ""

    # Теги
    tags_m = re.search(r"\*\*Теги:\*\*\s*(.+)", header)
    tags   = tags_m.group(1).strip() if tags_m else ""

    body = body.strip()
    if not body:
        return None

    # ID из имени файла (напр. lj_2004-10-07_1)
    stem   = path.stem                     # "2004-10-07-1"
    doc_id = "lj_" + stem

    return {
        "id":      doc_id,
        "title":   title or stem,
        "date":    date,
        "tags":    tags,
        "body":    body,
        "context": f"Дата: {date}. Заголовок: {title}." if (date or title) else "",
    }


def index_lj(oai: OpenAI, collection, limit: int = 0, verbose=True):
    posts = sorted(LJ_DIR.rglob("*.md"))
    if limit:
        posts = posts[:limit]

    existing_ids = set(collection.get(include=[])["ids"])
    total_added  = 0

    for path in posts:
        post = parse_lj_post(path)
        if not post:
            continue

        # Пропускаем если все чанки этого поста уже есть
        # (проверяем базовый id и id__c0)
        if post["id"] in existing_ids or f"{post['id']}__c0" in existing_ids:
            continue

        meta_base = {
            "title":  post["title"],
            "date":   post["date"],
            "tags":   post["tags"],
            "source": "lj",
        }

        items = get_embed_items(
            doc_id  = post["id"],
            text    = post["body"],
            meta_base = meta_base,
            oai     = oai,
            context = post["context"],
        )
        if not items:
            continue

        # Эмбеддим батчем
        vectors = embed([it["embed_text"] for it in items], oai)

        collection.add(
            ids        = [it["id"]       for it in items],
            embeddings = vectors,
            documents  = [it["document"] for it in items],
            metadatas  = [it["metadata"] for it in items],
        )
        total_added += len(items)

        if verbose:
            chunks_info = f"{len(items)} chunk(s)" if len(items) > 1 else "1 chunk"
            strategy    = items[0]["metadata"]["strategy"]
            print(f"  {post['id']} [{strategy}] {chunks_info}")

    if verbose:
        print(f"\nЖЖ: добавлено {total_added} чанков. Итого в базе: {collection.count()}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def stats(collection):
    count = collection.count()
    print(f"Записей в базе: {count}")
    if count > 0:
        # По источникам
        for src in ("corpus", "lj"):
            res = collection.get(where={"source": src}, include=["metadatas"])
            print(f"  {src}: {len(res['ids'])}")


def search(query: str, oai: OpenAI, collection, n=5):
    vector  = embed([query], oai)[0]
    results = collection.query(
        query_embeddings=[vector],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    print(f"\nПоиск: «{query}»\n")
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        score  = 1 - dist
        source = meta.get("source", "?")
        title  = meta.get("title", "—")
        date   = meta.get("date", "")
        label  = f"{title} ({date})" if date else title
        print(f"[{score:.3f}] [{source}] {label}")
        print(f"  {doc[:200]}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["corpus", "lj"], default="corpus")
    parser.add_argument("--limit",  type=int, default=0, help="Лимит постов ЖЖ (0 = все)")
    parser.add_argument("--stats",  action="store_true")
    parser.add_argument("--search", metavar="QUERY")
    args = parser.parse_args()

    api_key    = load_api_key()
    oai_client = OpenAI(api_key=api_key)
    chroma     = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col        = get_collection(chroma)

    if args.stats:
        stats(col)
    elif args.search:
        search(args.search, oai_client, col)
    elif args.source == "lj":
        index_lj(oai_client, col, limit=args.limit)
    else:
        index_corpus(oai_client, col)
