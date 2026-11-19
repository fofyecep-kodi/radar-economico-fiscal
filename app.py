import streamlit as st
import streamlit.components.v1 as components
import requests
import io
import os
import re
import json
import base64
import hashlib
import textwrap
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="Radar Econômico & Fiscal - Estúdio de Publicação",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
    <style>
    header[data-testid="stHeader"] {
        display: none !important;
    }
    footer {
        display: none !important;
    }
    #MainMenu {
        visibility: hidden !important;
    }
    .stDeployButton {
        display: none !important;
    }
    .block-container {
        padding-top: 1.3rem !important;
        padding-bottom: 1.5rem !important;
    }
    .source-text {
        font-size: 12px;
        color: #9CA3AF;
    }
    .news-card {
        padding: 12px 16px;
        border-radius: 10px;
        background-color: #161B22;
        border-left: 4px solid #38BDF8;
        margin-bottom: 10px;
    }
    .pl-card {
        padding: 12px 16px;
        border-radius: 10px;
        background-color: #161B22;
        border-left: 4px solid #FBBF24;
        margin-bottom: 10px;
    }
    .posted-badge {
        display: inline-block;
        background-color: rgba(74, 222, 128, 0.15);
        color: #4ADE80;
        border: 1px solid rgba(74, 222, 128, 0.4);
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        margin-left: 8px;
    }
    .diag-box {
        background-color: #111827;
        border: 1px solid #1F2937;
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 12px;
        color: #D1D5DB;
        margin-bottom: 12px;
    }
    </style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml, text/html",
    "Cache-Control": "no-cache"
}

TAXA_IMPOSTO_POR_SEGUNDO = 108500.00
ARQUIVO_POSTAGENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postagens_hoje.json")

# --- CONTROLE DE POSTAGENS DO DIA ---

def gerar_chave_item(tipo, titulo, referencia=""):
    base = f"{tipo}|{titulo.strip().lower()}|{referencia.strip().lower()}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()

def carregar_postagens_hoje():
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    dados_padrao = {"data": hoje_str, "itens": {}}

    if "postagens_dia" not in st.session_state:
        st.session_state["postagens_dia"] = dados_padrao.copy()

    if st.session_state["postagens_dia"].get("data") != hoje_str:
        st.session_state["postagens_dia"] = dados_padrao.copy()

    if os.path.exists(ARQUIVO_POSTAGENS):
        try:
            with open(ARQUIVO_POSTAGENS, "r", encoding="utf-8") as f:
                disco = json.load(f)
            if disco.get("data") == hoje_str and isinstance(disco.get("itens"), dict):
                st.session_state["postagens_dia"]["itens"].update(disco["itens"])
        except Exception:
            pass

    return st.session_state["postagens_dia"]["itens"]

def registrar_postagem_hoje(chave, rotulo):
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    hora_str = datetime.now().strftime("%H:%M")
    itens = carregar_postagens_hoje()
    itens[chave] = {"rotulo": rotulo, "hora": hora_str}
    st.session_state["postagens_dia"] = {"data": hoje_str, "itens": itens}

    try:
        with open(ARQUIVO_POSTAGENS, "w", encoding="utf-8") as f:
            json.dump({"data": hoje_str, "itens": itens}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def limpar_postagens_hoje():
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state["postagens_dia"] = {"data": hoje_str, "itens": {}}
    try:
        if os.path.exists(ARQUIVO_POSTAGENS):
            os.remove(ARQUIVO_POSTAGENS)
    except Exception:
        pass

# --- FORMATAÇÃO ---

def formatar_brl(valor_float):
    return "R$ " + f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_pontos(valor_float):
    return f"{valor_float:,.0f}".replace(",", ".") + " pts"

def formatar_variacao(pct_float):
    sinal = "+" if pct_float > 0 else ""
    pct_br = f"{pct_float:.2f}".replace(".", ",")
    return f"{sinal}{pct_br}% hoje"

def formatar_data_rss(pub_date_str):
    if not pub_date_str:
        return ""
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return pub_date_str[:16]

def limpar_html_simples(texto):
    if not texto:
        return ""
    sem_tags = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", sem_tags).strip()

def calcular_impostometro_estimado():
    agora = datetime.now()
    inicio_ano = datetime(agora.year, 1, 1)
    segundos_passados = max(0.0, (agora - inicio_ano).total_seconds())
    return segundos_passados * TAXA_IMPOSTO_POR_SEGUNDO

# --- BUSCA DE DADOS COM DIAGNÓSTICO E MÚLTIPLOS FALLBACKS ---

def _buscar_par_yahoo(simbolo):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}?interval=1d&range=2d"
    resp = requests.get(url, headers=HEADERS, timeout=6)
    resp.raise_for_status()
    dados = resp.json()
    res = dados.get("chart", {}).get("result", [])
    if not res:
        return None
    meta = res[0].get("meta", {})
    atual = meta.get("regularMarketPrice")
    ant = meta.get("chartPreviousClose")
    if atual is None:
        return None
    atual_f = float(atual)
    ant_f = float(ant) if ant else atual_f
    pct = ((atual_f - ant_f) / ant_f * 100) if ant_f else 0.0
    return {"bid": str(atual_f), "pctChange": str(round(pct, 2))}

@st.cache_data(ttl=15, show_spinner=False)
def buscar_cotacoes():
    resultado = {
        "usd": None,
        "eur": None,
        "btc": None,
        "fonte_moedas": "N/D",
        "fonte_btc": "N/D",
        "status_http": "OK",
        "hora_resposta": datetime.now().strftime("%H:%M:%S")
    }

    # 1. AwesomeAPI conjunto
    try:
        url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,BTC-BRL"
        response = requests.get(url, headers=HEADERS, timeout=6)
        resultado["status_http"] = f"AwesomeAPI HTTP {response.status_code}"
        response.raise_for_status()
        dados = response.json()
        if "USDBRL" in dados:
            resultado["usd"] = dados["USDBRL"]
            resultado["fonte_moedas"] = "AwesomeAPI"
        if "EURBRL" in dados:
            resultado["eur"] = dados["EURBRL"]
            resultado["fonte_moedas"] = "AwesomeAPI"
        if "BTCBRL" in dados:
            resultado["btc"] = dados["BTCBRL"]
            resultado["fonte_btc"] = "AwesomeAPI"
    except Exception as e:
        resultado["status_http"] = f"AwesomeAPI falhou ({type(e).__name__})"

    # 2. Yahoo Finance para pares que faltarem
    yahoo_map = {"usd": "USDBRL=X", "eur": "EURBRL=X", "btc": "BTC-BRL"}
    for chave, sim in yahoo_map.items():
        if not resultado[chave]:
            try:
                par = _buscar_par_yahoo(sim)
                if par:
                    resultado[chave] = par
                    if chave in ("usd", "eur"):
                        resultado["fonte_moedas"] = "Yahoo Finance"
                    else:
                        resultado["fonte_btc"] = "Yahoo Finance"
            except Exception:
                pass

    # 3. Frankfurter para moedas que ainda faltarem
    if not resultado["usd"] or not resultado["eur"]:
        try:
            hoje = datetime.now().date()
            inicio = hoje - timedelta(days=5)
            if not resultado["usd"]:
                r_usd = requests.get(
                    f"https://api.frankfurter.app/{inicio}..{hoje}?from=USD&to=BRL",
                    headers=HEADERS, timeout=6
                ).json()
                rates_usd = sorted(r_usd.get("rates", {}).items())
                if len(rates_usd) >= 1:
                    u = float(rates_usd[-1][1]["BRL"])
                    p = float(rates_usd[-2][1]["BRL"]) if len(rates_usd) >= 2 else u
                    pct = ((u - p) / p * 100) if p else 0.0
                    resultado["usd"] = {"bid": str(u), "pctChange": str(round(pct, 2))}
                    resultado["fonte_moedas"] = "Frankfurter"

            if not resultado["eur"]:
                r_eur = requests.get(
                    f"https://api.frankfurter.app/{inicio}..{hoje}?from=EUR&to=BRL",
                    headers=HEADERS, timeout=6
                ).json()
                rates_eur = sorted(r_eur.get("rates", {}).items())
                if len(rates_eur) >= 1:
                    u = float(rates_eur[-1][1]["BRL"])
                    p = float(rates_eur[-2][1]["BRL"]) if len(rates_eur) >= 2 else u
                    pct = ((u - p) / p * 100) if p else 0.0
                    resultado["eur"] = {"bid": str(u), "pctChange": str(round(pct, 2))}
                    resultado["fonte_moedas"] = "Frankfurter"
        except Exception:
            pass

    # 4. CoinGecko para BTC se ainda faltar
    if not resultado["btc"]:
        try:
            url_btc = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl&include_24hr_change=true"
            r_btc = requests.get(url_btc, headers=HEADERS, timeout=6).json()
            if "bitcoin" in r_btc:
                preco_brl = float(r_btc["bitcoin"]["brl"])
                var_24h = float(r_btc["bitcoin"].get("brl_24h_change", 0.0))
                resultado["btc"] = {"bid": str(preco_brl), "pctChange": str(round(var_24h, 2))}
                resultado["fonte_btc"] = "CoinGecko"
        except Exception:
            pass

    resultado["hora_resposta"] = datetime.now().strftime("%H:%M:%S")
    return resultado

@st.cache_data(ttl=30, show_spinner=False)
def buscar_ibovespa():
    try:
        url = "https://brapi.dev/api/quote/%5EBVSP"
        response = requests.get(url, headers=HEADERS, timeout=6)
        response.raise_for_status()
        dados = response.json()
        results = dados.get("results", [])
        if results:
            item = results[0]
            pontos = float(item.get("regularMarketPrice", 0.0))
            pct = float(item.get("regularMarketChangePercent", 0.0))
            if pontos > 0:
                return pontos, pct, False, "Brapi"
    except Exception:
        pass

    try:
        url_yf = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?interval=1d&range=5d"
        response = requests.get(url_yf, headers=HEADERS, timeout=6)
        response.raise_for_status()
        dados = response.json()
        result = dados.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            pontos = float(meta.get("regularMarketPrice", 0.0))
            fechamento_ant = float(meta.get("chartPreviousClose", 0.0))
            if pontos > 0:
                pct = ((pontos - fechamento_ant) / fechamento_ant * 100) if fechamento_ant else 0.0
                return pontos, pct, False, "Yahoo Finance"
    except Exception:
        pass

    return None, None, True, "Indisponível"

@st.cache_data(ttl=1800, show_spinner=False)
def buscar_selic():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        response = requests.get(url, headers=HEADERS, timeout=6)
        response.raise_for_status()
        dados = response.json()
        return float(dados[0]["valor"]), dados[0]["data"], False
    except Exception:
        return 13.75, "Ref. estimada", True

@st.cache_data(ttl=21600, show_spinner=False)
def buscar_ipca_mensal():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json"
        response = requests.get(url, headers=HEADERS, timeout=6)
        response.raise_for_status()
        dados = response.json()
        return float(dados[0]["valor"]), dados[0]["data"], False
    except Exception:
        return 0.44, "Ref. estimada", True

@st.cache_data(ttl=1800, show_spinner=False)
def buscar_historico_ativo(ativo="USD-BRL", dias=30):
    if ativo in ("USD-BRL", "EUR-BRL", "BTC-BRL"):
        try:
            url = f"https://economia.awesomeapi.com.br/json/daily/{ativo}/{dias}"
            response = requests.get(url, headers=HEADERS, timeout=7)
            response.raise_for_status()
            dados = response.json()
            if isinstance(dados, list) and len(dados) > 0:
                serie = {}
                for item in reversed(dados):
                    ts = int(item["timestamp"])
                    data_curta = datetime.fromtimestamp(ts).strftime("%d/%m")
                    serie[data_curta] = float(item["bid"])
                return serie
        except Exception:
            pass

    if ativo == "IBOV":
        range_map = {7: "10d", 30: "1mo", 90: "3mo"}
        yf_range = range_map.get(dias, "1mo")
        try:
            url_yf = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?interval=1d&range={yf_range}"
            response = requests.get(url_yf, headers=HEADERS, timeout=7)
            response.raise_for_status()
            dados = response.json()
            result = dados.get("chart", {}).get("result", [])
            if result:
                timestamps = result[0].get("timestamp", [])
                closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                serie = {}
                for ts, val in zip(timestamps, closes):
                    if val is not None:
                        data_curta = datetime.fromtimestamp(int(ts)).strftime("%d/%m")
                        serie[data_curta] = float(val)
                return serie
        except Exception:
            pass

    return {}

def extrair_imagem_rss_item(item_el):
    enclosure = item_el.find("enclosure")
    if enclosure is not None:
        url_enc = (enclosure.attrib.get("url") or "").strip()
        tipo_enc = (enclosure.attrib.get("type") or "").lower()
        if url_enc and ("image" in tipo_enc or url_enc.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
            return url_enc

    for el in item_el.iter():
        if el.tag.endswith(("content", "thumbnail")):
            u = (el.attrib.get("url") or "").strip()
            if u and u.startswith("http"):
                return u

    desc_raw = item_el.findtext("description") or ""
    match_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_raw, flags=re.IGNORECASE)
    if match_img:
        return match_img.group(1).strip()

    return ""

@st.cache_data(ttl=900, show_spinner=False)
def buscar_og_image_da_pagina(url_noticia):
    if not url_noticia or not url_noticia.startswith("http"):
        return ""
    try:
        resp = requests.get(url_noticia, headers=HEADERS, timeout=4)
        resp.raise_for_status()
        html = resp.text[:25000]
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""

@st.cache_data(ttl=180, show_spinner=False)
def buscar_noticias_rss(categoria="Relevantes"):
    feeds = [
        ("InfoMoney", "https://www.infomoney.com.br/feed/"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"),
    ]

    filtros_tema = {
        "Votações / Congresso": ["aprova", "aprovado", "votação", "vota", "câmara", "senado", "congresso", "projeto", "pl ", "pec "],
        "Impostos & Fiscal": ["imposto", "tributo", "fiscal", "arrecadação", "orçamento", "receita", "governo", "dívida"],
        "Mercado & Juros": ["selic", "dólar", "euro", "inflação", "ipca", "bolsa", "ibovespa", "bitcoin", "juros", "bc", "copom"],
        "Relevantes": [
            "aprova", "aprovado", "votação", "vota", "câmara", "senado",
            "congresso", "projeto", "pl ", "pec ", "imposto", "tributo",
            "fiscal", "selic", "dólar", "inflação", "governo", "ministro",
            "bolsa", "ibovespa", "bitcoin"
        ]
    }
    palavras = filtros_tema.get(categoria, filtros_tema["Relevantes"])

    itens = []
    for fonte, url in feeds:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=6)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            for item in root.findall(".//item")[:20]:
                titulo = limpar_html_simples(item.findtext("title") or "")
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                resumo = limpar_html_simples(item.findtext("description") or "")
                img_url = extrair_imagem_rss_item(item)

                if not titulo:
                    continue

                texto_lower = titulo.lower()
                if categoria != "Todas" and not any(p in texto_lower for p in palavras):
                    continue

                if resumo.lower() == titulo.lower():
                    resumo = ""

                itens.append({
                    "fonte": fonte,
                    "titulo": titulo,
                    "resumo": resumo[:220] + ("..." if len(resumo) > 220 else ""),
                    "link": link,
                    "img_url": img_url,
                    "data_fmt": formatar_data_rss(pub_date)
                })
        except Exception:
            continue

    return itens[:15]

@st.cache_data(ttl=900, show_spinner=False)
def buscar_proposicoes_camara(limite=8):
    try:
        data_inicio = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        url = (
            "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
            f"?dataApresentacaoInicio={data_inicio}&itens={limite}&ordem=DESC&ordenarPor=id"
        )
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
        resp.raise_for_status()
        dados = resp.json().get("dados", [])
        lista = []
        for p in dados:
            sigla = p.get("siglaTipo", "")
            numero = p.get("numero", "")
            ano = p.get("ano", "")
            ementa = (p.get("ementa") or "").strip()
            lista.append({
                "codigo": f"{sigla} {numero}/{ano}".strip(),
                "ementa": ementa[:240] + ("..." if len(ementa) > 240 else ""),
                "id": p.get("id")
            })
        return lista
    except Exception:
        return []

# --- CONTADOR JS ---

def renderizar_contador_js(valor_inicial_float):
    html_code = f"""
    <div style="font-family: sans-serif; padding: 8px 0;">
        <div id="contador-imposto" style="font-size: 32px; font-weight: 700; color: #FBBF24;">
            Carregando...
        </div>
        <div style="font-size: 13px; color: #9CA3AF; margin-top: 4px;">
            Projeção contínua acumulada desde 1º de janeiro (atualização local no navegador).
        </div>
    </div>
    <script>
        let valorAtual = {valor_inicial_float:.2f};
        const taxaPorSegundo = {TAXA_IMPOSTO_POR_SEGUNDO:.2f};
        const el = document.getElementById("contador-imposto");

        function formatarBRL(num) {{
            return "R$ " + num.toLocaleString("pt-BR", {{
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }});
        }}

        function atualizar() {{
            el.textContent = formatarBRL(valorAtual);
            valorAtual += taxaPorSegundo;
        }}

        atualizar();
        setInterval(atualizar, 1000);
    </script>
    """
    components.html(html_code, height=85)

# --- COMPARTILHAMENTO NATIVO DO DISPOSITIVO ---

def renderizar_bloco_publicacao_interativo(png_bytes_io, nome_arquivo, texto_compartilhar, link_url=""):
    png_bytes_io.seek(0)
    b64_png = base64.b64encode(png_bytes_io.read()).decode("utf-8")
    png_bytes_io.seek(0)

    texto_seguro = json.dumps(texto_compartilhar)
    link_seguro = json.dumps(link_url)
    nome_seguro = json.dumps(nome_arquivo)

    html = f"""
    <div style="font-family: sans-serif; display: flex; flex-direction: column; gap: 10px;">
        <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
            <button id="btn-share" style="
                background: linear-gradient(135deg, #2563EB, #0EA5E9);
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 12px 18px;
                font-size: 15px;
                font-weight: 700;
                cursor: pointer;
            ">📤 Compartilhar no Dispositivo</button>

            <a id="btn-dl-fallback" download="{nome_arquivo}" href="data:image/png;base64,{b64_png}" style="
                background: #1F2937;
                color: #E5E7EB;
                border: 1px solid #374151;
                border-radius: 10px;
                padding: 11px 16px;
                font-size: 14px;
                font-weight: 600;
                text-decoration: none;
            ">⬇️ Salvar PNG</a>
        </div>
        <div id="share-status" style="font-size: 13px; color: #9CA3AF;">
            No celular ou navegador compatível, toque em "Compartilhar no Dispositivo" para escolher onde enviar.
        </div>
    </div>

    <script>
        const b64Data = "{b64_png}";
        const fileName = {nome_seguro};
        const shareText = {texto_seguro};
        const shareUrl = {link_seguro};
        const statusEl = document.getElementById("share-status");
        const btnShare = document.getElementById("btn-share");

        function b64ToFile(b64, filename, mimeType) {{
            const byteCharacters = atob(b64);
            const byteArrays = [];
            for (let offset = 0; offset < byteCharacters.length; offset += 512) {{
                const slice = byteCharacters.slice(offset, offset + 512);
                const byteNumbers = new Array(slice.length);
                for (let i = 0; i < slice.length; i++) {{
                    byteNumbers[i] = slice.charCodeAt(i);
                }}
                byteArrays.push(new Uint8Array(byteNumbers));
            }}
            const blob = new Blob(byteArrays, {{ type: mimeType }});
            return new File([blob], filename, {{ type: mimeType }});
        }}

        btnShare.addEventListener("click", async () => {{
            try {{
                if (!navigator.share) {{
                    statusEl.textContent = "Seu navegador não suporta compartilhamento direto. Use o botão 'Salvar PNG' ao lado.";
                    return;
                }}

                const file = b64ToFile(b64Data, fileName, "image/png");
                const payloadComArquivo = {{
                    title: "Radar Econômico & Fiscal",
                    text: shareUrl ? (shareText + "\\n" + shareUrl) : shareText,
                    files: [file]
                }};

                if (navigator.canShare && navigator.canShare({{ files: [file] }})) {{
                    await navigator.share(payloadComArquivo);
                    statusEl.textContent = "✅ Menu de compartilhamento aberto!";
                    return;
                }}

                await navigator.share({{
                    title: "Radar Econômico & Fiscal",
                    text: shareText,
                    url: shareUrl || undefined
                }});
                statusEl.textContent = "✅ Texto/link compartilhado! (Para anexar a imagem neste navegador, use 'Salvar PNG').";
            }} catch (err) {{
                if (err && err.name === "AbortError") {{
                    statusEl.textContent = "Compartilhamento cancelado.";
                }} else {{
                    statusEl.textContent = "Não foi possível abrir o menu nativo aqui. Use 'Salvar PNG' ou abra o site direto no navegador do celular.";
                }}
            }}
        }});
    </script>
    """
    components.html(html, height=105)

# --- GERAÇÃO DE CARDS EDITORIAIS ADAPTATIVOS (PILLOW) ---

def carregar_fonte_segura(nomes_candidatos, tamanho):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for nome in nomes_candidatos:
        caminho = os.path.join(base_dir, nome)
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue
    return ImageFont.load_default()

def baixar_e_ajustar_imagem(url_img, largura_alvo, altura_alvo):
    if not url_img or not url_img.startswith("http"):
        return None
    try:
        r = requests.get(url_img, headers=HEADERS, timeout=5)
        r.raise_for_status()
        foto = Image.open(io.BytesIO(r.content)).convert("RGB")
        if foto.width < 120 or foto.height < 80:
            return None

        escala = max(largura_alvo / foto.width, altura_alvo / foto.height)
        nova_w = int(foto.width * escala)
        nova_h = int(foto.height * escala)
        foto_red = foto.resize((nova_w, nova_h), Image.Resampling.LANCZOS)

        left = max(0, (nova_w - largura_alvo) // 2)
        top = max(0, (nova_h - altura_alvo) // 2)
        return foto_red.crop((left, top, left + largura_alvo, top + altura_alvo))
    except Exception:
        return None

def criar_mascara_arredondada(largura, altura, raio):
    mascara = Image.new("L", (largura, altura), 0)
    d = ImageDraw.Draw(mascara)
    d.rounded_rectangle([0, 0, largura, altura], radius=raio, fill=255)
    return mascara

def gerar_card_editorial(
    chapeu,
    manchete,
    resumo,
    destaque_valor,
    fonte_nome,
    data_hora,
    url_imagem="",
    cor_destaque="#38BDF8",
    formato="Feed (1080x1080)"
):
    eh_stories = "1080x1920" in formato
    largura, altura = (1080, 1920) if eh_stories else (1080, 1080)

    fundo_escuro = "#080C14"
    card_bg = "#111827"
    card_destaque_bg = "#0F172A"
    borda_suave = "#1F2937"

    img = Image.new("RGB", (largura, altura), color=fundo_escuro)
    draw = ImageDraw.Draw(img)

    bold_c = ["ARIALBD.TTF", "ARIBLK.TTF", "ARIAL.TTF", "arialbd.ttf", "arial.ttf"]
    reg_c = ["ARIAL.TTF", "ARIALBD.TTF", "arial.ttf", "arialbd.ttf"]

    f_marca = carregar_fonte_segura(bold_c, 25)
    f_data = carregar_fonte_segura(reg_c, 20)
    f_chapeu = carregar_fonte_segura(bold_c, 24)
    f_destaque = carregar_fonte_segura(bold_c, 84 if not destaque_valor else 78)
    f_manchete = carregar_fonte_segura(bold_c, 44 if eh_stories else 39)
    f_resumo = carregar_fonte_segura(reg_c, 29 if eh_stories else 26)
    f_rodape = carregar_fonte_segura(reg_c, 20)

    margem_x = 64
    topo_y = 105 if eh_stories else 44
    rodape_y = altura - (88 if eh_stories else 54)

    # Cabeçalho editorial
    draw.rounded_rectangle([margem_x, topo_y, margem_x + 140, topo_y + 7], radius=4, fill=cor_destaque)
    draw.text((margem_x, topo_y + 18), "RADAR ECONÔMICO & FISCAL", fill="#F9FAFB", font=f_marca)
    draw.text((margem_x, topo_y + 49), f"{fonte_nome}  •  {data_hora}", fill="#94A3B8", font=f_data)

    bloco_y = topo_y + 92
    foto_w = largura - (margem_x * 2)

    # Tenta carregar imagem apenas se houver URL informada
    foto_pronta = baixar_e_ajustar_imagem(url_imagem, foto_w, 360) if url_imagem else None

    if foto_pronta:
        # Layout com imagem da notícia embaixo (sem espaço sobrando)
        altura_bloco_texto = 455 if eh_stories else 375
        draw.rounded_rectangle(
            [margem_x, bloco_y, largura - margem_x, bloco_y + altura_bloco_texto],
            radius=24,
            fill=card_bg,
            outline=borda_suave,
            width=2
        )
        draw.rounded_rectangle(
            [margem_x, bloco_y + 24, margem_x + 8, bloco_y + altura_bloco_texto - 24],
            radius=4,
            fill=cor_destaque
        )

        inner_x = margem_x + 38
        cur_y = bloco_y + 28
        draw.text((inner_x, cur_y), chapeu.upper(), fill=cor_destaque, font=f_chapeu)
        cur_y += 40

        linhas_manchete = textwrap.wrap(manchete, width=36 if eh_stories else 40)
        for linha in linhas_manchete[:4]:
            draw.text((inner_x, cur_y), linha, fill="#F9FAFB", font=f_manchete)
            cur_y += 48 if eh_stories else 43

        if resumo:
            cur_y += 12
            linhas_resumo = textwrap.wrap(resumo, width=52 if eh_stories else 56)
            for linha in linhas_resumo[:3]:
                if cur_y > bloco_y + altura_bloco_texto - 36:
                    break
                draw.text((inner_x, cur_y), linha, fill="#CBD5E1", font=f_resumo)
                cur_y += 34 if eh_stories else 31

        foto_y = bloco_y + altura_bloco_texto + 24
        foto_h = max(240, rodape_y - foto_y - 22)
        foto_ajustada = baixar_e_ajustar_imagem(url_imagem, foto_w, foto_h)
        if foto_ajustada:
            mascara = criar_mascara_arredondada(foto_w, foto_h, 24)
            img.paste(foto_ajustada, (margem_x, foto_y), mascara)
            draw.rounded_rectangle([margem_x, foto_y, margem_x + foto_w, foto_y + foto_h], radius=24, outline=borda_suave, width=2)
    else:
        # Layout expandido limpo quando não há imagem (indicadores ou proposições)
        card_bot = rodape_y - 24
        draw.rounded_rectangle(
            [margem_x, bloco_y, largura - margem_x, card_bot],
            radius=26,
            fill=card_bg,
            outline=borda_suave,
            width=2
        )
        draw.rounded_rectangle(
            [margem_x, bloco_y + 28, margem_x + 10, card_bot - 28],
            radius=5,
            fill=cor_destaque
        )

        inner_x = margem_x + 44
        cur_y = bloco_y + 42

        draw.text((inner_x, cur_y), chapeu.upper(), fill=cor_destaque, font=f_chapeu)
        cur_y += 52

        if destaque_valor:
            # Cartão interno de destaque numérico
            box_val_top = cur_y
            box_val_bot = cur_y + 155
            draw.rounded_rectangle(
                [inner_x, box_val_top, largura - margem_x - 44, box_val_bot],
                radius=20,
                fill=card_destaque_bg,
                outline=cor_destaque,
                width=2
            )
            draw.text((inner_x + 32, box_val_top + 32), destaque_valor, fill="#FFFFFF", font=f_destaque)
            cur_y = box_val_bot + 44

        linhas_manchete = textwrap.wrap(manchete, width=34 if eh_stories else 38)
        for linha in linhas_manchete[:4]:
            draw.text((inner_x, cur_y), linha, fill="#F9FAFB", font=f_manchete)
            cur_y += 52 if eh_stories else 46

        if resumo:
            cur_y += 20
            linhas_resumo = textwrap.wrap(resumo, width=48 if eh_stories else 54)
            for linha in linhas_resumo[:6]:
                if cur_y > card_bot - 48:
                    break
                draw.text((inner_x, cur_y), linha, fill="#CBD5E1", font=f_resumo)
                cur_y += 38 if eh_stories else 34

    draw.text((margem_x, rodape_y), f"Fonte: {fonte_nome}  •  Radar Econômico & Fiscal", fill="#64748B", font=f_rodape)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def gerar_card_resumo(
    usd_str, usd_var_str, usd_pct_val,
    eur_str, eur_var_str, eur_pct_val,
    btc_str, btc_var_str, btc_pct_val,
    ibov_str, ibov_var_str, ibov_pct_val,
    ipca_str, selic_str, imposto_str, data_hora,
    formato="Feed (1080x1080)"
):
    eh_stories = "1080x1920" in formato
    largura, altura = (1080, 1920) if eh_stories else (1080, 1080)
    img = Image.new("RGB", (largura, altura), color="#080C14")
    draw = ImageDraw.Draw(img)

    bold_c = ["ARIALBD.TTF", "ARIBLK.TTF", "ARIAL.TTF", "arialbd.ttf", "arial.ttf"]
    reg_c = ["ARIAL.TTF", "ARIALBD.TTF", "arial.ttf", "arialbd.ttf"]

    f_titulo = carregar_fonte_segura(bold_c, 42)
    f_sub = carregar_fonte_segura(reg_c, 22)
    f_label = carregar_fonte_segura(reg_c, 23)
    f_valor = carregar_fonte_segura(bold_c, 38)
    f_var = carregar_fonte_segura(reg_c, 21)
    f_imp = carregar_fonte_segura(bold_c, 42)
    f_rodape = carregar_fonte_segura(reg_c, 19)

    oy = 95 if eh_stories else 0
    esp = 230 if eh_stories else 186

    draw.rounded_rectangle([64, 34 + oy, 204, 41 + oy], radius=4, fill="#38BDF8")
    draw.text((64, 52 + oy), "RADAR ECONÔMICO & FISCAL", fill="#FFFFFF", font=f_titulo)
    draw.text((64, 102 + oy), f"Atualizado em {data_hora}", fill="#94A3B8", font=f_sub)

    y1 = 152 + oy
    hb = 180 if eh_stories else 164

    c_usd = "#F87171" if usd_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([64, y1, 524, y1 + hb], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((90, y1 + 16), "DÓLAR (USD)", fill="#94A3B8", font=f_label)
    draw.text((90, y1 + 54), usd_str, fill=c_usd, font=f_valor)
    draw.text((90, y1 + 114), usd_var_str, fill=c_usd, font=f_var)

    c_eur = "#F87171" if eur_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([556, y1, 1016, y1 + hb], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((582, y1 + 16), "EURO (EUR)", fill="#94A3B8", font=f_label)
    draw.text((582, y1 + 54), eur_str, fill=c_eur, font=f_valor)
    draw.text((582, y1 + 114), eur_var_str, fill=c_eur, font=f_var)

    y2 = y1 + esp
    c_btc = "#4ADE80" if btc_pct_val >= 0 else "#F87171"
    draw.rounded_rectangle([64, y2, 524, y2 + hb], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((90, y2 + 16), "BITCOIN (BTC)", fill="#94A3B8", font=f_label)
    draw.text((90, y2 + 54), btc_str, fill="#F59E0B", font=f_valor)
    if btc_var_str:
        draw.text((90, y2 + 114), btc_var_str, fill=c_btc, font=f_var)

    c_ibov = "#4ADE80" if ibov_pct_val >= 0 else "#F87171"
    draw.rounded_rectangle([556, y2, 1016, y2 + hb], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((582, y2 + 16), "IBOVESPA", fill="#94A3B8", font=f_label)
    draw.text((582, y2 + 54), ibov_str, fill="#60A5FA", font=f_valor)
    if ibov_var_str:
        draw.text((582, y2 + 114), ibov_var_str, fill=c_ibov, font=f_var)

    y3 = y2 + esp
    hm = 154 if eh_stories else 140
    draw.rounded_rectangle([64, y3, 524, y3 + hm], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((90, y3 + 16), "TAXA SELIC (META)", fill="#94A3B8", font=f_label)
    draw.text((90, y3 + 58), selic_str, fill="#38BDF8", font=f_valor)

    draw.rounded_rectangle([556, y3, 1016, y3 + hm], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((582, y3 + 16), "IPCA (ÚLTIMO MÊS)", fill="#94A3B8", font=f_label)
    draw.text((582, y3 + 58), ipca_str, fill="#F472B6", font=f_valor)

    y4 = y3 + (178 if eh_stories else 162)
    hi = 210 if eh_stories else 190
    draw.rounded_rectangle([64, y4, 1016, y4 + hi], radius=20, fill="#111827", outline="#1F2937", width=2)
    draw.text((90, y4 + 22), "ARRECADAÇÃO ESTIMADA NO ANO", fill="#94A3B8", font=f_label)
    draw.text((90, y4 + 78), imposto_str, fill="#FBBF24", font=f_imp)

    y_rod = (y4 + hi + 70) if eh_stories else 976
    draw.text((64, y_rod), "Fontes: BCB, AwesomeAPI, Frankfurter, CoinGecko & Yahoo Finance", fill="#64748B", font=f_rodape)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# --- INTERFACE ---

st.title("📊 Radar Econômico & Fiscal — Estúdio de Publicação")
data_atual_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

postados_hoje = carregar_postagens_hoje()

col_btn, col_info_post, col_limpar = st.columns([1.4, 2.6, 1.2])
with col_btn:
    if st.button("🔄 Atualizar Dados Agora"):
        buscar_cotacoes.clear()
        buscar_ibovespa.clear()
        buscar_noticias_rss.clear()
        buscar_proposicoes_camara.clear()
        buscar_og_image_da_pagina.clear()
        st.rerun()

with col_info_post:
    st.info(f"📌 Postagens registradas hoje: **{len(postados_hoje)}** (avisa repetição sem bloquear)")

with col_limpar:
    if postados_hoje and st.button("🧹 Zerar histórico de hoje"):
        limpar_postagens_hoje()
        st.rerun()

cotacoes_data = buscar_cotacoes()
dolar = cotacoes_data["usd"]
euro = cotacoes_data["eur"]
btc = cotacoes_data["btc"]
fonte_moedas = cotacoes_data["fonte_moedas"]
fonte_btc = cotacoes_data["fonte_btc"]

selic_valor, selic_data, selic_fallback = buscar_selic()
ipca_valor, ipca_data, ipca_fallback = buscar_ipca_mensal()
ibov_pontos, ibov_pct, ibov_indisponivel, fonte_ibov = buscar_ibovespa()

st.markdown(
    f'<div class="diag-box">🩺 <strong>Diagnóstico de atualização:</strong> Tela renderizada às <strong>{data_atual_str[14:]}</strong> | '
    f'Cotações: <strong>{cotacoes_data["status_http"]}</strong> (resp. às <strong>{cotacoes_data["hora_resposta"]}</strong>) | '
    f'Moedas: <strong>{fonte_moedas}</strong> • BTC: <strong>{fonte_btc}</strong> • Ibovespa: <strong>{fonte_ibov}</strong></div>',
    unsafe_allow_html=True
)

usd_formatado = "Indisponível"
usd_var_str = "0,00% hoje"
usd_pct_num = 0.0
valor_usd_float = None

eur_formatado = "Indisponível"
eur_var_str = "0,00% hoje"
eur_pct_num = 0.0
valor_eur_float = None

btc_formatado = "Indisponível"
btc_var_str = ""
btc_pct_num = 0.0
valor_btc_float = None

ibov_formatado = "Indisponível"
ibov_var_str = ""
ibov_pct_num = 0.0

ipca_formatada = "Indisponível"
selic_formatada = "Indisponível"

col1, col2, col3, col4 = st.columns(4)

with col1:
    if dolar:
        valor_usd_float = float(dolar["bid"])
        usd_pct_num = float(dolar["pctChange"])
        usd_formatado = formatar_brl(valor_usd_float)
        usd_var_str = formatar_variacao(usd_pct_num)
        st.metric(label="💵 Dólar (USD)", value=usd_formatado, delta=usd_var_str)
        st.caption(f"Fonte: {fonte_moedas}")
    else:
        st.error("Erro ao carregar Dólar")

with col2:
    if euro:
        valor_eur_float = float(euro["bid"])
        eur_pct_num = float(euro["pctChange"])
        eur_formatado = formatar_brl(valor_eur_float)
        eur_var_str = formatar_variacao(eur_pct_num)
        st.metric(label="💶 Euro (EUR)", value=eur_formatado, delta=eur_var_str)
        st.caption(f"Fonte: {fonte_moedas}")
    else:
        st.error("Erro ao carregar Euro")

with col3:
    if btc:
        valor_btc_float = float(btc["bid"])
        btc_pct_num = float(btc["pctChange"])
        btc_formatado = formatar_brl(valor_btc_float)
        btc_var_str = formatar_variacao(btc_pct_num)
        st.metric(label="₿ Bitcoin (BTC)", value=btc_formatado, delta=btc_var_str)
        st.caption(f"Fonte: {fonte_btc}")
    else:
        st.error("Erro ao carregar BTC")

with col4:
    if not ibov_indisponivel and ibov_pontos is not None:
        ibov_pct_num = ibov_pct or 0.0
        ibov_formatado = formatar_pontos(ibov_pontos)
        ibov_var_str = formatar_variacao(ibov_pct_num)
        st.metric(label="📉 Ibovespa", value=ibov_formatado, delta=ibov_var_str)
        st.caption(f"Fonte: {fonte_ibov}")
    else:
        st.metric(label="📉 Ibovespa", value="Indisponível", delta="Sem retorno público", delta_color="off")

col5, col6 = st.columns(2)

with col5:
    if selic_valor is not None:
        selic_formatada = f"{selic_valor:.2f}".replace(".", ",") + "% a.a."
        legenda_selic = f"{selic_data} (contingência)" if selic_fallback else f"Ref: {selic_data}"
        st.metric(label="🏦 Taxa Selic (Meta Copom)", value=selic_formatada, delta=legenda_selic, delta_color="off")
    else:
        st.error("Erro ao carregar Selic")

with col6:
    if ipca_valor is not None:
        sinal_ipca = "+" if ipca_valor > 0 else ""
        ipca_formatada = f"{sinal_ipca}{ipca_valor:.2f}".replace(".", ",") + "% a.m."
        legenda_ipca = f"{ipca_data} (contingência)" if ipca_fallback else f"Ref: {ipca_data}"
        st.metric(label="🏷️ Inflação / IPCA Mensal", value=ipca_formatada, delta=legenda_ipca, delta_color="off")
    else:
        st.error("Erro ao carregar IPCA")

st.divider()

aba1, aba2, aba3 = st.tabs([
    "📤 Estúdio de Publicação",
    "📰 Notícias & Câmara",
    "📈 Gráficos, Conversor & Resumo"
])

imposto_atual_float = calcular_impostometro_estimado()
imposto_atual_fmt = formatar_brl(imposto_atual_float)

noticias_cache = buscar_noticias_rss("Relevantes")
proposicoes_cache = buscar_proposicoes_camara(8)

with aba1:
    st.subheader("📤 Abrir Postagem e Compartilhar")
    st.caption("Escolha o item, visualize a postagem na tela e use o botão de compartilhar do dispositivo.")

    formato_estudio = st.radio(
        "Formato da postagem",
        options=["Feed (1080x1080)", "Stories / Status (1080x1920)"],
        horizontal=True,
        key="formato_estudio"
    )
    sufixo_estudio = "stories" if "1080x1920" in formato_estudio else "feed"

    tipo_postagem = st.selectbox(
        "O que você quer publicar agora?",
        options=["Notícia (RSS)", "Indicador", "Proposição da Câmara"]
    )

    link_referencia = ""
    texto_legenda = ""
    img_card = None
    nome_arq_card = ""
    chave_atual = ""
    rotulo_atual = ""

    if tipo_postagem == "Notícia (RSS)":
        if noticias_cache:
            opcoes_news = {f"[{n['fonte']}] {n['titulo']}": n for n in noticias_cache}
            escolha_news = st.selectbox("Escolha a notícia", options=list(opcoes_news.keys()))
            item_n = opcoes_news[escolha_news]
            link_referencia = item_n.get("link") or ""
            texto_legenda = f"{item_n['titulo']} ({item_n['fonte']})"
            chave_atual = gerar_chave_item("noticia", item_n["titulo"], item_n["fonte"])
            rotulo_atual = item_n["titulo"][:80]

            img_url_final = item_n.get("img_url") or buscar_og_image_da_pagina(link_referencia)
            img_card = gerar_card_editorial(
                chapeu=f"NOTÍCIA • {item_n['data_fmt'] or 'ATUALIZAÇÃO'}",
                manchete=item_n["titulo"],
                resumo=item_n["resumo"] or "Acompanhe os desdobramentos econômicos e políticos na íntegra.",
                destaque_valor="",
                fonte_nome=item_n["fonte"],
                data_hora=data_atual_str,
                url_imagem=img_url_final,
                cor_destaque="#38BDF8",
                formato=formato_estudio
            )
            nome_arq_card = f"post_noticia_{sufixo_estudio}_{datetime.now().strftime('%H%M')}.png"
        else:
            st.info("Nenhuma notícia disponível no momento.")

    elif tipo_postagem == "Indicador":
        catalogo_indicadores = {
            "Dólar (USD)": ("CÂMBIO • MERCADO", "Dólar Comercial (USD)", f"Variação: {usd_var_str}", usd_formatado, fonte_moedas, "#4ADE80"),
            "Euro (EUR)": ("CÂMBIO • MERCADO", "Euro (EUR)", f"Variação: {eur_var_str}", eur_formatado, fonte_moedas, "#60A5FA"),
            "Bitcoin (BTC)": ("CRIPTOATIVOS", "Bitcoin (BTC)", f"Variação: {btc_var_str}", btc_formatado, fonte_btc, "#F59E0B"),
            "Ibovespa": ("BOLSA • B3", "Ibovespa (^BVSP)", f"Variação: {ibov_var_str}", ibov_formatado, fonte_ibov, "#38BDF8"),
            "Taxa Selic": ("JUROS • COPOM", "Taxa Selic (Meta Anual)", f"Data de referência: {selic_data}", selic_formatada, "Banco Central", "#38BDF8"),
            "IPCA Mensal": ("INFLAÇÃO • IBGE/BCB", "IPCA Mensal", f"Data de referência: {ipca_data}", ipca_formatada, "Banco Central", "#F472B6"),
            "Arrecadação Estimada": ("CONTAS PÚBLICAS", "Arrecadação Estimada no Ano", "Projeção contínua acumulada desde 1º de janeiro no país.", imposto_atual_fmt, "Estimativa Fiscal", "#FBBF24"),
        }
        ind_sel = st.selectbox("Escolha o indicador", options=list(catalogo_indicadores.keys()))
        chap_i, tit_i, res_i, dest_i, font_i, cor_i = catalogo_indicadores[ind_sel]
        texto_legenda = f"{tit_i}: {dest_i} ({res_i}) - Fonte: {font_i}"
        chave_atual = gerar_chave_item("indicador", ind_sel, dest_i)
        rotulo_atual = f"Indicador: {ind_sel}"

        img_card = gerar_card_editorial(
            chapeu=chap_i,
            manchete=tit_i,
            resumo=res_i,
            destaque_valor=dest_i,
            fonte_nome=font_i,
            data_hora=data_atual_str,
            url_imagem="",
            cor_destaque=cor_i,
            formato=formato_estudio
        )
        nome_arq_card = f"post_{ind_sel.lower().replace(' ', '_')}_{sufixo_estudio}_{datetime.now().strftime('%H%M')}.png"

    else:
        if proposicoes_cache:
            opcoes_pl = {f"{p['codigo']} — {p['ementa'][:70]}": p for p in proposicoes_cache}
            escolha_pl = st.selectbox("Escolha a proposição", options=list(opcoes_pl.keys()))
            item_p = opcoes_pl[escolha_pl]
            link_referencia = f"https://www.camara.leg.br/proposicoesWeb/fichadetailid?idProposicao={item_p['id']}" if item_p.get("id") else ""
            texto_legenda = f"{item_p['codigo']}: {item_p['ementa']}"
            chave_atual = gerar_chave_item("camara", item_p["codigo"], item_p["ementa"])
            rotulo_atual = f"{item_p['codigo']} - {item_p['ementa'][:60]}"

            img_card = gerar_card_editorial(
                chapeu="CÂMARA DOS DEPUTADOS",
                manchete=item_p["codigo"],
                resumo=item_p["ementa"],
                destaque_valor="",
                fonte_nome="Dados Abertos Câmara",
                data_hora=data_atual_str,
                url_imagem="",
                cor_destaque="#FBBF24",
                formato=formato_estudio
            )
            nome_arq_card = f"post_camara_{sufixo_estudio}_{datetime.now().strftime('%H%M')}.png"
        else:
            st.info("Nenhuma proposição da Câmara disponível no momento.")

    if chave_atual and chave_atual in postados_hoje:
        st.warning(f"⚠️ Este item já foi marcado como postado hoje às **{postados_hoje[chave_atual]['hora']}**.")

    if img_card is not None:
        st.image(img_card, caption="Postagem pronta na tela", width=440)
        renderizar_bloco_publicacao_interativo(
            png_bytes_io=img_card,
            nome_arquivo=nome_arq_card,
            texto_compartilhar=texto_legenda,
            link_url=link_referencia
        )

        if st.button("✅ Marcar como postado hoje", key="mk_estudio_item"):
            registrar_postagem_hoje(chave_atual, rotulo_atual)
            st.rerun()

    if link_referencia:
        st.markdown(f"🔗 **Link da fonte:** [{link_referencia}]({link_referencia})")

    if postados_hoje:
        st.divider()
        st.markdown("**Histórico de hoje:**")
        for info in postados_hoje.values():
            st.markdown(f"- `{info['hora']}` — {info['rotulo']}")

with aba2:
    st.subheader("📰 Linha de Notícias Econômicas e Políticas")
    categoria_escolhida = st.selectbox(
        "Filtrar manchetes por tema",
        options=["Relevantes", "Votações / Congresso", "Impostos & Fiscal", "Mercado & Juros", "Todas"]
    )
    noticias = buscar_noticias_rss(categoria=categoria_escolhida)

    if noticias:
        for item in noticias:
            chave_item = gerar_chave_item("noticia", item["titulo"], item["fonte"])
            badge_html = ""
            if chave_item in postados_hoje:
                badge_html = f'<span class="posted-badge">Já postado hoje às {postados_hoje[chave_item]["hora"]}</span>'

            link_md = f" — [Ler fonte]({item['link']})" if item["link"] else ""
            data_txt = f" • {item['data_fmt']}" if item["data_fmt"] else ""
            st.markdown(
                f'<div class="news-card"><strong>[{item["fonte"]}]</strong> {item["titulo"]}{badge_html}{link_md}<br><span class="source-text">{data_txt.lstrip(" • ")}</span></div>',
                unsafe_allow_html=True
            )
    else:
        st.info("Nenhuma manchete encontrada para esse filtro no momento.")

    st.divider()

    st.subheader("🏛️ Proposições Recentes na Câmara dos Deputados")
    if proposicoes_cache:
        for prop in proposicoes_cache:
            chave_prop = gerar_chave_item("camara", prop["codigo"], prop["ementa"])
            badge_pl = ""
            if chave_prop in postados_hoje:
                badge_pl = f'<span class="posted-badge">Já postado hoje às {postados_hoje[chave_prop]["hora"]}</span>'

            url_camara = f"https://www.camara.leg.br/proposicoesWeb/fichadetailid?idProposicao={prop['id']}" if prop["id"] else ""
            link_prop = f" — [Ficha na Câmara]({url_camara})" if url_camara else ""
            st.markdown(
                f'<div class="pl-card"><strong>{prop["codigo"]}</strong>{badge_pl}{link_prop}<br><span>{prop["ementa"]}</span></div>',
                unsafe_allow_html=True
            )
    else:
        st.info("Consulta de proposições da Câmara temporariamente indisponível.")

with aba3:
    st.subheader("Histórico de Cotações e Índices")
    c_ativo, c_dias = st.columns([2, 1])
    with c_ativo:
        ativo_escolhido = st.selectbox(
            "Indicador",
            options=["USD-BRL", "EUR-BRL", "BTC-BRL", "IBOV"],
            format_func=lambda x: {
                "USD-BRL": "Dólar Comercial (USD)",
                "EUR-BRL": "Euro (EUR)",
                "BTC-BRL": "Bitcoin (BTC)",
                "IBOV": "Ibovespa (^BVSP)"
            }[x]
        )
    with c_dias:
        dias_escolhidos = st.selectbox("Período", options=[7, 30, 90], index=1, format_func=lambda d: f"Últimos {d} dias")

    serie_hist = buscar_historico_ativo(ativo=ativo_escolhido, dias=dias_escolhidos)
    if serie_hist:
        st.line_chart(serie_hist, height=280)
    else:
        st.info("Histórico temporariamente indisponível para este indicador.")

    st.divider()

    st.subheader("💱 Conversor Rápido (BRL ↔ Moedas)")
    conv_col1, conv_col2, conv_col3 = st.columns(3)
    with conv_col1:
        valor_reais = st.number_input("Valor em Reais (R$)", min_value=0.0, value=1000.0, step=100.0)
    with conv_col2:
        if valor_usd_float and valor_usd_float > 0:
            st.metric("Equivalente em Dólar", f"US$ {valor_reais / valor_usd_float:,.2f}")
        else:
            st.metric("Equivalente em Dólar", "Indisponível")
    with conv_col3:
        if valor_btc_float and valor_btc_float > 0:
            st.metric("Equivalente em Bitcoin", f"{valor_reais / valor_btc_float:.6f} BTC")
        elif valor_eur_float and valor_eur_float > 0:
            st.metric("Equivalente em Euro", f"€ {valor_reais / valor_eur_float:,.2f}")
        else:
            st.metric("Equivalente em Cripto/Euro", "Indisponível")

    st.divider()

    st.subheader("⏱️ Estimativa de Arrecadação Tributária no Ano")
    renderizar_contador_js(imposto_atual_float)

    st.divider()

    st.subheader("📸 Resumo Geral (Todos os Indicadores)")
    formato_resumo = st.radio(
        "Formato do resumo",
        options=["Feed (1080x1080)", "Stories / Status (1080x1920)"],
        horizontal=True,
        key="formato_resumo"
    )
    chave_resumo = gerar_chave_item("resumo", "Card Resumo Geral", data_atual_str[:10])
    if chave_resumo in postados_hoje:
        st.warning(f"⚠️ Você já marcou o **Resumo Geral** como postado hoje às **{postados_hoje[chave_resumo]['hora']}**.")

    imagem_resumo = gerar_card_resumo(
        usd_str=usd_formatado,
        usd_var_str=usd_var_str,
        usd_pct_val=usd_pct_num,
        eur_str=eur_formatado,
        eur_var_str=eur_var_str,
        eur_pct_val=eur_pct_num,
        btc_str=btc_formatado,
        btc_var_str=btc_var_str,
        btc_pct_val=btc_pct_num,
        ibov_str=ibov_formatado,
        ibov_var_str=ibov_var_str,
        ibov_pct_val=ibov_pct_num,
        ipca_str=ipca_formatada,
        selic_str=selic_formatada,
        imposto_str=imposto_atual_fmt,
        data_hora=data_atual_str,
        formato=formato_resumo
    )
    sufixo_resumo = "stories" if "1080x1920" in formato_resumo else "feed"
    st.image(imagem_resumo, caption="Resumo pronto na tela", width=440)
    renderizar_bloco_publicacao_interativo(
        png_bytes_io=imagem_resumo,
        nome_arquivo=f"radar_resumo_{sufixo_resumo}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
        texto_compartilhar=f"Radar Econômico & Fiscal ({data_atual_str}) - Dólar: {usd_formatado} | Euro: {eur_formatado} | Selic: {selic_formatada}",
        link_url=""
    )

    if st.button("✅ Marcar resumo como postado hoje", key="mk_resumo"):
        registrar_postagem_hoje(chave_resumo, "Resumo Geral")
        st.rerun()

st.divider()
st.markdown(
    '<p class="source-text">Fontes: Banco Central do Brasil (SGS), AwesomeAPI, Frankfurter, CoinGecko, Brapi/Yahoo Finance, Dados Abertos da Câmara e feeds RSS públicos.</p>',
    unsafe_allow_html=True
)