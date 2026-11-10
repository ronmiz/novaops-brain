"""Every model call in the project goes through this file.

Spec 6.6: "Keep model calls behind one small function so a provider swap touches one
place." Embeddings and Converse both live here; nothing else imports boto3's
bedrock-runtime client.
"""
import functools
import json

import boto3

from . import config


@functools.cache
def _bedrock():
    return boto3.client("bedrock-runtime", region_name=config.REGION)


def chat_model(**kwargs):
    """The LangChain chat model the agent graph uses — same Bedrock model, same seam."""
    from langchain_aws import ChatBedrockConverse
    return ChatBedrockConverse(model=config.MODEL_ID, region_name=config.REGION,
                               temperature=0, **kwargs)


def embed(text: str) -> list[float]:
    """Titan V2, normalized — so inner product == cosine (same as Lessons 6-7)."""
    resp = _bedrock().invoke_model(
        modelId=config.EMBED_MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": config.EMBED_DIM, "normalize": True}),
    )
    return json.loads(resp["body"].read())["embedding"]


def converse(prompt: str, *, system: str | None = None, tool: dict | None = None,
             max_tokens: int = 1000, temperature: float = 0.0) -> dict:
    """One Bedrock Converse call. With `tool`, the call is FORCED to use it and the
    tool's input dict is returned (structured output); otherwise {"text": ...}."""
    kwargs = {
        "modelId": config.MODEL_ID,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system:
        kwargs["system"] = [{"text": system}]
    if tool:
        kwargs["toolConfig"] = {
            "tools": [tool],
            "toolChoice": {"tool": {"name": tool["toolSpec"]["name"]}},
        }
    content = _bedrock().converse(**kwargs)["output"]["message"]["content"]
    if tool:
        return next((b["toolUse"]["input"] for b in content if "toolUse" in b), {})
    return {"text": "".join(b.get("text", "") for b in content)}
