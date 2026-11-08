import os
import base64
from fastapi import FastAPI, Request, HTTPException
import requests

app = FastAPI()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

@app.get("/")
def home():
    return {"status": "Servidor rodando com sucesso!"}

@app.post("/upload")
async def upload_image(request: Request):
    try:
        image_bytes = await request.body()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Nenhuma imagem recebida.")

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 1500,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": "Resolva esta questão de engenharia ou cálculo passo a passo, de forma rigorosa, acadêmica e detalhada, ideal para revisão de professor."
                        }
                    ]
                }
            ]
        }

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            timeout=45
        )

        if response.status_code != 200:
            return f"Erro API Anthropic ({response.status_code}): {response.text}"

        response_data = response.json()
        
        if "content" in response_data and len(response_data["content"]) > 0:
            return response_data["content"][0].get("text", "Erro: Texto vazio na resposta.")
        else:
            return f"Erro estrutura Claude: {response.text}"

    except Exception as e:
        return f"Erro interno no servidor: {str(e)}"
