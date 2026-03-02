#!/usr/bin/env python3
"""
MCP-сервер: search_corpus — семантический поиск по корпусу Клоди Спарк.

Запуск (Claude Code добавит автоматически через settings):
    python scripts/mcp_search.py
"""

import json
import sys
from pathlib import Path

import chromadb
from openai import OpenAI

CONFIG_FILE     = Path.home() / ".config/clody_spark/openai.json"
CHROMA_DIR      = Path.home() / ".config/clody_spark/chroma"
COLLECTION_NAME = "clody_spark"

REPO_ROOT = Path(__file__).parent.parent


def load_api_key():
    with open(CONFIG_FILE) as f:
        return json.load(f)["api_key"]


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


def search_corpus(query: str, n: int = 5, source: str | None = None) -> list[dict]:
    api_key = load_api_key()
    oai     = OpenAI(api_key=api_key)

    response = oai.embeddings.create(
        model="text-embedding-3-large",
        input=[query],
    )
    vector = response.data[0].embedding

    collection = get_collection()
    where = {"source": source} if source else None
    results    = collection.query(
        query_embeddings=[vector],
        n_results=n,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "score":   round(1 - dist, 3),
            "id":      meta.get("id", ""),
            "title":   meta.get("title", ""),
            "section": meta.get("section", ""),
            "excerpt": doc[:300],
        })
    return hits


# ── MCP protocol (stdio) ──────────────────────────────────────────────────────

TOOLS = [
    {
        "name":        "search_corpus",
        "description": (
            "Семантический поиск по корпусу текстов Клоди Спарк. "
            "Возвращает наиболее близкие по смыслу тексты. "
            "Используй source='corpus' для поиска по собственным философским текстам, "
            "source='lj' для ЖЖ-архива, source='poetry' для стихов. "
            "Без source — поиск по всем источникам сразу."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type":        "string",
                    "description": "Поисковый запрос на русском или английском",
                },
                "n": {
                    "type":        "integer",
                    "description": "Количество результатов (по умолчанию 5)",
                    "default":     5,
                },
                "source": {
                    "type":        "string",
                    "description": "Фильтр источника: 'corpus', 'lj', 'poetry', 'telegram'. Без этого параметра — все источники.",
                    "enum":        ["corpus", "lj", "poetry", "telegram"],
                },
            },
            "required": ["query"],
        },
    }
]


def send(obj: dict):
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def handle(request: dict) -> dict | None:
    method = request.get("method")
    rid    = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities":    {"tools": {}},
                "serverInfo":      {"name": "clody-search", "version": "1.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name   = request["params"]["name"]
        args   = request["params"].get("arguments", {})
        if name == "search_corpus":
            hits = search_corpus(args["query"], args.get("n", 5), args.get("source"))
            text = ""
            for h in hits:
                text += f"[{h['score']}] {h['title']} ({h['section']})\n"
                text += f"  {h['excerpt']}\n\n"
            return {
                "jsonrpc": "2.0", "id": rid,
                "result":  {"content": [{"type": "text", "text": text.strip()}]},
            }
        return {
            "jsonrpc": "2.0", "id": rid,
            "error":   {"code": -32601, "message": f"Unknown tool: {name}"},
        }

    if method == "notifications/initialized":
        return None  # уведомление, ответ не нужен

    return {
        "jsonrpc": "2.0", "id": rid,
        "error":   {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main():
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request  = json.loads(raw_line)
            response = handle(request)
            if response is not None:
                send(response)
        except Exception as e:
            send({"jsonrpc": "2.0", "id": None,
                  "error": {"code": -32603, "message": str(e)}})


if __name__ == "__main__":
    main()
