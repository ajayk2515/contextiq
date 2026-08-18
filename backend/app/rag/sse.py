import json

from pydantic import BaseModel


def sse_event(event: str, payload: BaseModel) -> str:
    data = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"
