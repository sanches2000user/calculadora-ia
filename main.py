import os
import base64
from fastapi import FastAPI, Request, Response
import requests

app = FastAPI()
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY").

SYSTEM_PROMPT = (
    "Você é um assistente acadêmico de alto nível em Engenharia Mecânica. "
    "Resolva o problema da imagem de forma extremamente rigorosa e completa, para nota máxima em prova universitária. Porém lembre-se que tenho um shield display oled de 0.9pol I2C então tem que caber na tela dele e tentar não ter tantas e tantas páginas (blocos), acredito que um limite de 30 seria o ideal, mas veja aí, pois tem resoluções que precisarão de apenas 6, outras 15, outras 20 a 30 eu imagino. precisa ter o necessário para entendimento de onde saíram os valores e sem exagerar na quantidade de informações."
    "1. Indique explicitamente todas as hipóteses simplificadoras. "
    "2. Desenvolva toda a formulação algébrica e literal antes de inserir valores numéricos. "
    "3. Mostre o passo a passo da substituição e o resultado com unidades corretas. "
    "4. Se a imagem estiver cortada ou ilegível, inicie com '[ERRO_CAMERA]' e diga o que falta em poucas palavras. "
    "Caso contrário, divida a resposta final em blocos claros para leitura sequencial."
)

@app.post("/upload")
async def process_image(request: Request):
    image_data = await request.body()
    base64_image = base64.b64encode(image_data).decode("utf-8")
    
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1200,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_image
                        }
                    },
                    {
                        "type": "text",
                        "text": "Resolva esta questão de forma completa e rigorosa."
                    }
                ]
            }
        ]
    }
    
    response = requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
    res_json = response.json()
    
    try:
        texto_resposta = res_json["content"][0]["text"]
        return Response(content=texto_resposta, media_type="text/plain")
    except Exception as e:
        return Response(content=f"Erro ao processar Claude: {str(e)}", media_type="text/plain")