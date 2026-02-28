#!/usr/bin/env python3
"""
Индексатор корпуса Клоди Спарк.
Парсит corpus-annotations.md, создаёт эмбеддинги через OpenAI,
сохраняет в ChromaDB.

Использование:
    python scripts/indexer.py                  # индексировать corpus-annotations.md
    python scripts/indexer.py --stats          # статистика по базе
    python scripts/indexer.py --search "запрос"  # тестовый поиск
"""

import json
import re
import sys
import argparse
from pathlib import Path

import chromadb
from openai import OpenAI

# Пути
CONFIG_FILE = Path.home() / ".config/clody_spark/openai.json"
CHROMA_DIR  = Path.home() / ".config/clody_spark/chroma"
REPO_ROOT   = Path(__file__).parent.parent
CORPUS_FILE = REPO_ROOT / "corpus-annotations.md"

COLLECTION_NAME = "clody_spark"


def load_api_key():
    with open(CONFIG_FILE) as f:
        return json.load(f)["api_key"]


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


def parse_corpus_annotations(path: Path) -> list[dict]:
    """
    Парсит corpus-annotations.md.
    Каждый элемент: filename, title, annotation, section.
    """
    text = path.read_text(encoding="utf-8")
    entries = []
    current_section = ""

    for line in text.splitlines():
        # Раздел (## heading)
        section_match = re.match(r"^## (.+)", line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        # Запись: **filename** — *Title*
        entry_match = re.match(r"^\*\*(.+?)\*\* — \*(.+?)\*", line)
        if entry_match:
            filename = entry_match.group(1).strip()
            title    = entry_match.group(2).strip()
            # Следующая непустая строка — аннотация
            entries.append({
                "id":       filename,
                "title":    title,
                "section":  current_section,
                "annotation": "",
                "_pending": True,
            })
            continue

        # Аннотация — строка после заголовка записи
        if entries and entries[-1].get("_pending") and line.strip():
            entries[-1]["annotation"] = line.strip()
            entries[-1]["_pending"] = False

    # Убираем служебное поле
    for e in entries:
        e.pop("_pending", None)

    return [e for e in entries if e["annotation"]]


def embed(texts: list[str], client: OpenAI) -> list[list[float]]:
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=texts,
    )
    return [item.embedding for item in response.data]


def index_corpus(verbose=True):
    api_key    = load_api_key()
    oai_client = OpenAI(api_key=api_key)
    collection = get_collection()

    entries = parse_corpus_annotations(CORPUS_FILE)
    if verbose:
        print(f"Найдено записей: {len(entries)}")

    # Проверяем, что уже проиндексировано
    existing_ids = set(collection.get(include=[])["ids"])
    new_entries  = [e for e in entries if e["id"] not in existing_ids]

    if not new_entries:
        print("Все записи уже в базе.")
        return

    if verbose:
        print(f"Новых для индексации: {len(new_entries)}")

    # Текст для эмбеддинга = аннотация (наше ключевое решение)
    texts     = [e["annotation"] for e in new_entries]
    vectors   = embed(texts, oai_client)

    collection.add(
        ids        = [e["id"] for e in new_entries],
        embeddings = vectors,
        documents  = [e["annotation"] for e in new_entries],
        metadatas  = [
            {
                "title":   e["title"],
                "section": e["section"],
                "source":  "corpus",
                "type":    "annotation",
            }
            for e in new_entries
        ],
    )

    if verbose:
        print(f"Добавлено: {len(new_entries)} записей.")
        print(f"Итого в базе: {collection.count()}")


def stats():
    collection = get_collection()
    count = collection.count()
    print(f"Записей в базе: {count}")
    if count > 0:
        sample = collection.get(limit=3, include=["metadatas", "documents"])
        print("\nПримеры:")
        for i, (doc, meta) in enumerate(zip(sample["documents"], sample["metadatas"])):
            print(f"\n[{i+1}] {meta.get('title', '—')} ({meta.get('section', '—')})")
            print(f"    {doc[:120]}...")


def search(query: str, n=5):
    api_key    = load_api_key()
    oai_client = OpenAI(api_key=api_key)
    collection = get_collection()

    vector = embed([query], oai_client)[0]
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
        score = 1 - dist  # cosine similarity
        print(f"[{score:.3f}] {meta['title']}")
        print(f"         {doc[:150]}...")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats",  action="store_true", help="Статистика базы")
    parser.add_argument("--search", metavar="QUERY",     help="Тестовый поиск")
    args = parser.parse_args()

    if args.stats:
        stats()
    elif args.search:
        search(args.search)
    else:
        index_corpus()
