import os
import time
import base64
import httpx
from fastapi import FastAPI, Request, HTTPException, Path
from fastapi.responses import JSONResponse

app = FastAPI()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-haiku-5-5"
LINHAS_POR_PAGINA = 7
MAX_IMAGENS_POR_SESSAO = 10
SESSAO_EXPIRA_SEGUNDOS = 15 * 60
TIMEOUT_ANTHROPIC_SEGUNDOS = 120  # era 60; com mais fotos, o processamento demora mais

SYSTEM_PROMPT = """Voce e um assistente de engenharia mecanica para estudo.
As imagens mostram partes (podem ser 1 ou varias fotos) de um problema de
mecanica dos fluidos (impresso ou manuscrito), possivelmente com figura e
tabelas. Junte as informacoes de todas as imagens recebidas como se fossem
pedacos do mesmo enunciado antes de resolver.
Devolva a resolucao COMPLETA e RESUMIDA: sem introducao, sem comentarios e
sem explicar o que entendeu.
Formato (vai para um visor minusculo de 21 colunas, paginas de linhas):
use quantas linhas forem necessarias, cada uma com no maximo 21 caracteres,
uma operacao por linha, sem pular nenhum passo que gere numero.
Comece pelos dados (enunciado, tabela, figura), mostre somas explicitas e
conversoes de unidade. Cada passo: formula, substituicao numerica, resultado.
Todo numero usado precisa vir das imagens ou de uma linha anterior - nunca
invente um valor; se faltar um dado essencial mesmo somando todas as
imagens, escreva apenas ILEGIVEL: <qual dado> e pare.
Calcule voce mesmo os valores numericos, com cuidado, passo a passo.
Para o fator de atrito use Haaland, salvo se o enunciado indicar outra
formula. Texto simples, sem markdown e sem LaTeX, use ^ para potencia.
A ultima linha e sempre: RESP: valor e unidade.
Responda em portugues."""

sessoes: dict[str, dict] = {}


def limpa_sessoes_velhas():
    agora = time.time()
    expiradas = [sid for sid, s in sessoes.items() if agora - s["criada_em"] > SESSAO_EXPIRA_SEGUNDOS]
    for sid in expiradas:
        del sessoes[sid]


def monta_paginas(texto: str) -> list[str]:
    linhas = []
    for paragrafo in texto.split("\n"):
        if not paragrafo:
            linhas.append("")
            continue
        while paragrafo:
            linhas.append(paragrafo[:21])
            paragrafo = paragrafo[21:]
    return ["\n".join(linhas[i:i + LINHAS_POR_PAGINA]) for i in range(0, len(linhas), LINHAS_POR_PAGINA)] or [""]


@app.get("/")
def home():
    limpa_sessoes_velhas()
    return {"status": "Servidor rodando com sucesso!", "sessoes_abertas": len(sessoes)}


@app.post("/capture/{session_id}")
async def capture(request: Request, session_id: str = Path(...)):
    limpa_sessoes_velhas()
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Nenhuma imagem recebida.")

    sessao = sessoes.setdefault(session_id, {"imagens": [], "criada_em": time.time()})
    if len(sessao["imagens"]) >= MAX_IMAGENS_POR_SESSAO:
        raise HTTPException(status_code=400, detail=f"Maximo de {MAX_IMAGENS_POR_SESSAO} fotos por exercicio.")
    sessao["imagens"].append(image_bytes)
    print(f"[capture] sessao={session_id} fotos_agora={len(sessao['imagens'])} tamanho_bytes={len(image_bytes)}")
    return {"status": "ok", "fotos_na_sessao": len(sessao["imagens"])}


@app.post("/solve/{session_id}")
async def solve(session_id: str = Path(...)):
    limpa_sessoes_velhas()
    sessao = sessoes.get(session_id)
    if not sessao or not sessao["imagens"]:
        raise HTTPException(status_code=400, detail="Nenhuma foto nesta sessao. Mande fotos para /capture antes.")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY nao configurada no servidor.")

    n_fotos = len(sessao["imagens"])
    print(f"[solve] sessao={session_id} enviando {n_fotos} fotos pra API...")

    conteudo = []
    for img in sessao["imagens"]:
        conteudo.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(img).decode("utf-8")},
        })
    conteudo.append({"type": "text", "text": "Resolva o problema mostrado nessas imagens (sao partes do mesmo exercicio)."})

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
    "model": MODEL,
    "max_tokens": 6000,
    "thinking": {"type": "disabled"},
    "system": SYSTEM_PROMPT,
    "messages": [{"role": "user", "content": conteudo}],
}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_ANTHROPIC_SEGUNDOS) as client:
            response = await client.post(ANTHROPIC_URL, json=payload, headers=headers)
    except httpx.TimeoutException:
        print(f"[solve] sessao={session_id} TIMEOUT apos {TIMEOUT_ANTHROPIC_SEGUNDOS}s com {n_fotos} fotos")
        raise HTTPException(status_code=504, detail="Timeout ao chamar a API da Anthropic.")
    finally:
        del sessoes[session_id]

    if response.status_code != 200:
        print(f"[solve] sessao={session_id} erro Anthropic {response.status_code}: {response.text[:300]}")
        raise HTTPException(status_code=502, detail=f"Erro API Anthropic ({response.status_code}): {response.text}")

    data = response.json()
    texto = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    if not texto:
        raise HTTPException(status_code=502, detail=f"Resposta sem texto: {response.text}")

    paginas = monta_paginas(texto)
    print(f"[solve] sessao={session_id} sucesso: {len(paginas)} paginas geradas")
    return JSONResponse({"pages": paginas, "raw": texto})


@app.post("/upload")
async def upload_image_legado(request: Request):
    limpa_sessoes_velhas()
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Nenhuma imagem recebida.")
    sid = f"legado-{time.time()}"
    sessoes[sid] = {"imagens": [image_bytes], "criada_em": time.time()}
    return await solve(sid)


# ---- Rotas simples, sem ID de sessao, para o firmware com OLED/botoes ----
SESSAO_UNICA = "dispositivo-unico"

@app.post("/capture")
async def capture_simples(request: Request):
    return await capture(request, session_id=SESSAO_UNICA)

@app.get("/solve")
async def solve_simples():
    return await solve(session_id=SESSAO_UNICA)

@app.get("/reset")
async def reset_simples():
    if SESSAO_UNICA in sessoes:
        del sessoes[SESSAO_UNICA]
    return {"status": "sessao limpa"}
