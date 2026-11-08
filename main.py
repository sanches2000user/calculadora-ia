import os
import base64
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = """Voce e um assistente de engenharia mecanica para estudo.
A imagem mostra um problema de mecanica dos fluidos (impresso ou manuscrito),
possivelmente com figura e tabelas.
Devolva a resolucao COMPLETA e RESUMIDA: sem introducao, sem comentarios e
sem explicar o que entendeu.
Formato (vai para um visor minusculo de 21 colunas, paginas de 4 linhas):
use quantas linhas forem necessarias, cada uma com no maximo 21 caracteres,
uma operacao por linha, sem pular nenhum passo que gere numero.
Comece pelos dados (enunciado, tabela, figura), mostre somas explicitas e
conversoes de unidade. Cada passo: formula, substituicao numerica, resultado.
Todo numero usado precisa vir do enunciado, da tabela, da figura ou de uma
linha anterior - nunca invente um valor; se faltar um dado essencial,
escreva apenas ILEGIVEL: <qual dado> e pare.
Calcule voce mesmo os valores numericos, com cuidado, passo a passo.
Para o fator de atrito use Haaland, salvo se o enunciado indicar outra
formula. Texto simples, sem markdown e sem LaTeX, use ^ para potencia.
A ultima linha e sempre: RESP: valor e unidade.
Responda em portugues."""


@app.get("/")
def home():
    return {"status": "Servidor rodando com sucesso!"}


@app.post("/upload")
async def upload_image(request: Request):
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Nenhuma imagem recebida.")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY nao configurada no servidor.")

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": 2000,
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
                            "data": image_base64,
                        },
                    },
                    {"type": "text", "text": "Resolva o problema da imagem."},
                ],
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(ANTHROPIC_URL, json=payload, headers=headers)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout ao chamar a API da Anthropic.")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro API Anthropic ({response.status_code}): {response.text}",
        )

    data = response.json()
    texto = "".join(
        bloco.get("text", "") for bloco in data.get("content", []) if bloco.get("type") == "text"
    )
    if not texto:
        raise HTTPException(status_code=502, detail=f"Resposta sem texto: {response.text}")

    # Pagina o texto em blocos de ate 21 colunas x 4 linhas, do jeito que o
    # firmware da Xiao espera (mesma logica do server.py local).
    linhas = []
    for paragrafo in texto.split("\n"):
        if not paragrafo:
            linhas.append("")
            continue
        while paragrafo:
            linhas.append(paragrafo[:21])
            paragrafo = paragrafo[21:]
    # 7 linhas por pagina = OLED 128x64 (o display que voce vai comprar);
    # se usar um 128x32, troque o 7 por 4 aqui e tambem no firmware.
    LINHAS_POR_PAGINA = 7
    paginas = ["\n".join(linhas[i:i + LINHAS_POR_PAGINA]) for i in range(0, len(linhas), LINHAS_POR_PAGINA)] or [""]

    return JSONResponse({"pages": paginas, "raw": texto})
