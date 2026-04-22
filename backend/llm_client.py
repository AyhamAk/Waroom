"""
Streaming LLM wrapper for planning phases (phases 1-3).
Supports Anthropic and Google Gemini.
"""
import asyncio
from typing import AsyncGenerator


async def stream_message(
    provider: str,
    api_key: str,
    model: str,
    max_tokens: int,
    system: str,
    messages: list,
) -> AsyncGenerator[str, None]:
    """Async generator that yields text chunks."""
    if provider == "anthropic":
        async for chunk in _stream_anthropic(api_key, model, max_tokens, system, messages):
            yield chunk
    elif provider == "gemini":
        async for chunk in _stream_gemini(api_key, model, max_tokens, system, messages):
            yield chunk
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def _stream_anthropic(api_key, model, max_tokens, system, messages):
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Run the blocking stream call in a thread to not block the event loop
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run():
        try:
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, _run)

    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        yield item


async def _stream_gemini(api_key, model, max_tokens, system, messages):
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    gmodel = genai.GenerativeModel(model, generation_config={"max_output_tokens": max_tokens})

    # Build history
    history = []
    if system:
        history.append({"role": "user", "parts": [f"SYSTEM:\n{system}"]})
        history.append({"role": "model", "parts": ["Understood."]})

    for m in messages[:-1]:
        role = "model" if m["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [m["content"]]})

    last = messages[-1]["content"] if messages else ""

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _run():
        try:
            chat = gmodel.start_chat(history=history)
            response = chat.send_message(last, stream=True)
            for chunk in response:
                text = chunk.text
                if text:
                    loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, Exception(str(e)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, _run)

    while True:
        item = await queue.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        yield item
