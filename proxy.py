import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

app = FastAPI()
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.environ.get("GROQ_API_KEY")
)

# اصطياد المسار بكلا الشكلين لمنع أي التافاف من الأداة
@app.post("/messages")
@app.post("/v1/messages")
async def handle_messages(request: Request):
    body = await request.json()
    groq_messages = []
    
    if "system" in body:
        groq_messages.append({"role": "system", "content": body["system"]})
        
    for msg in body.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join([item.get("text", "") for item in content if item.get("type") == "text"])
        groq_messages.append({"role": msg.get("role"), "content": content})

    try:
        chat_completion = client.chat.completions.create(
            messages=groq_messages,
            model="llama-3.1-70b-versatile",
            max_tokens=body.get("max_tokens", 1024)
        )
        return JSONResponse(content={
            "id": chat_completion.id,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": chat_completion.choices[0].message.content}],
            "model": "claude-3-5-sonnet-20240620",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 100}
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3000)
