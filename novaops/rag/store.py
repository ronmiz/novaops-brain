"""OpenSearch Serverless: client, index mapping, ingest.

Lesson 7's client.py carried over: SigV4 to `aoss`, the collection resolved by name
(OPENSEARCH_COLLECTION), and the credential split — OPENSEARCH_AWS_* (Ron's own
account, which owns the collection) vs the default AWS_* keys used for Bedrock.

    python -m novaops.rag.store          # (re)create the index and ingest all 102 docs
"""
import functools
import os
import time

import boto3
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection, helpers

from .. import config, llm
from .documents import embedding_text, load_chunks

INDEX_BODY = {
    "settings": {"index": {"knn": True}},
    "mappings": {"properties": {
        "vector": {"type": "knn_vector", "dimension": config.EMBED_DIM,
                   "method": {"name": "hnsw", "space_type": "innerproduct"}},
        "text": {"type": "text"},
        "source": {"type": "keyword"},
        "collection": {"type": "keyword"},
        "title": {"type": "keyword"},
        "section": {"type": "keyword"},
        "audience": {"type": "keyword"},        # the permission boundary — filtered at retrieval
        "doc_date": {"type": "date", "format": "yyyy-MM-dd"},
    }},
}


def _aoss_session() -> boto3.Session:
    key = os.environ.get("OPENSEARCH_AWS_ACCESS_KEY_ID")
    secret = os.environ.get("OPENSEARCH_AWS_SECRET_ACCESS_KEY")
    if key and secret:
        return boto3.Session(aws_access_key_id=key, aws_secret_access_key=secret,
                             region_name=config.REGION)
    return boto3.Session(region_name=config.REGION)


def _endpoint() -> str:
    if os.environ.get("OPENSEARCH_ENDPOINT"):
        return os.environ["OPENSEARCH_ENDPOINT"]
    name = os.environ.get("OPENSEARCH_COLLECTION")
    if not name:
        raise SystemExit("Set OPENSEARCH_COLLECTION in lessons/.env (Lesson 7 setup).")
    details = _aoss_session().client("opensearchserverless").batch_get_collection(
        names=[name]).get("collectionDetails", [])
    if not details or not details[0].get("collectionEndpoint"):
        raise SystemExit(f"Collection '{name}' not found or not ACTIVE.")
    return details[0]["collectionEndpoint"]


@functools.cache
def client() -> OpenSearch:
    host = _endpoint().replace("https://", "").rstrip("/")
    auth = AWSV4SignerAuth(_aoss_session().get_credentials(), config.REGION, "aoss")
    # NextGen scales to zero when idle; the first request warms it up (~10 s).
    return OpenSearch(hosts=[{"host": host, "port": 443}], http_auth=auth, use_ssl=True,
                      verify_certs=True, connection_class=RequestsHttpConnection,
                      timeout=120, max_retries=3, retry_on_timeout=True)


def rebuild_index() -> int:
    """Drop and recreate the index, then embed and bulk-load every chunk."""
    os_client = client()
    if os_client.indices.exists(index=config.INDEX_NAME):
        os_client.indices.delete(index=config.INDEX_NAME)
    os_client.indices.create(index=config.INDEX_NAME, body=INDEX_BODY)

    chunks = load_chunks(config.DOCS_DIR)
    print(f"{len(chunks)} chunks from {len({c['source'] for c in chunks})} documents. Embedding...")
    for i, chunk in enumerate(chunks, 1):
        chunk["vector"] = llm.embed(embedding_text(chunk))
        if i % 50 == 0 or i == len(chunks):
            print(f"  embedded {i}/{len(chunks)}")
    # aoss assigns ids itself — a caller-supplied _id is rejected.
    # Small batches: each chunk carries a 1024-float vector (~20 KB of JSON); the default
    # 500-doc batch is a ~10 MB request that timed out on upload.
    helpers.bulk(os_client, [{"_index": config.INDEX_NAME, "_source": c} for c in chunks],
                 chunk_size=50, max_chunk_bytes=2 * 1024 * 1024)

    deadline = time.time() + 60
    while time.time() < deadline:
        if os_client.count(index=config.INDEX_NAME)["count"] >= len(chunks):
            break
        time.sleep(2)
    count = os_client.count(index=config.INDEX_NAME)["count"]
    print(f"Index '{config.INDEX_NAME}': {count} chunks searchable.")
    return count


if __name__ == "__main__":
    rebuild_index()
