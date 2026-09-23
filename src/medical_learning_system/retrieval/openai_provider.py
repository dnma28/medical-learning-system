from __future__ import annotations

import os
from functools import partial

from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

from .rag_anything_adapter import RAGAnythingAdapter, RAGConfig


def build_openai_rag(config: RAGConfig):
    """Build a RAG-Anything engine using OpenAI-compatible model functions.

    API keys are read from environment variables and are never stored in Git.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    base_url = os.getenv("OPENAI_BASE_URL") or None
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    vision_model = os.getenv("VISION_MODEL", "gpt-4o")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    embedding_dim = int(os.getenv("EMBEDDING_DIM", "3072"))

    def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
        return openai_complete_if_cache(
            llm_model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    def vision_model_func(
        prompt,
        system_prompt=None,
        history_messages=[],
        image_data=None,
        messages=None,
        **kwargs,
    ):
        if messages:
            return openai_complete_if_cache(
                vision_model,
                "",
                system_prompt=None,
                history_messages=[],
                messages=messages,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )

        if image_data:
            message_list = []
            if system_prompt:
                message_list.append({"role": "system", "content": system_prompt})
            message_list.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            },
                        },
                    ],
                }
            )
            return openai_complete_if_cache(
                vision_model,
                "",
                system_prompt=None,
                history_messages=[],
                messages=message_list,
                api_key=api_key,
                base_url=base_url,
                **kwargs,
            )

        return llm_model_func(prompt, system_prompt, history_messages, **kwargs)

    embedding_func = EmbeddingFunc(
        embedding_dim=embedding_dim,
        max_token_size=8192,
        func=partial(
            openai_embed.func,
            model=embedding_model,
            api_key=api_key,
            base_url=base_url,
        ),
    )

    adapter = RAGAnythingAdapter(config)
    return adapter.build_engine(
        llm_model_func=llm_model_func,
        vision_model_func=vision_model_func,
        embedding_func=embedding_func,
    )
