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
    page_title="Radar Studio — Central de Conteúdo & Dados",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- ESTILO VISUAL PREMIUM E RESPONSIVO ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    header[data-testid="stHeader"], footer, #MainMenu, .stDeployButton {
        display: none !important;
        visibility: hidden !important;
    }
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        max-width: 1180px;
    }
    .hero-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 55%, #0B1120 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 16px 20px;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
    }
    .hero-title {
        font-size: 22px;
        font-weight: 800;
        color: #F8FAFC;
        margin: 0;
        letter-spacing: -0.4px;
    }
    .hero-sub {
        font-size: 13px;
        color: #94A3B8;
        margin-top: 3px;
    }
    .status-pill {
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.35);
        color: #7DD3FC;
        padding: 5px 11px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
    }
    .kpi-box {
        background: #111827;
        border: 1px solid #1F2937;
        border-radius: 14px;
        padding: 13px 15px;
        margin-bottom: 6px;
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 700;
        color: #9CA3AF;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }
    .kpi-val {
        font-size: 22px;
        font-weight: 800;
        color: #F9FAFB;
        margin: 3px 0;
    }
    .kpi-delta-up { color: #4ADE80; font-size: 12px; font-weight: 600; }
    .kpi-delta-down { color: #F87171; font-size: 12px; font-weight: 600; }
    .kpi-delta-neutral { color: #94A3B8; font-size: 12px; font-weight: 500; }

    .feed-item {
        background: #111827;
        border: 1px solid #1F2937;
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 6px;
    }
    .feed-meta {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }
    .feed-title {
        font-size: 15px;
        font-weight: 700;
        color: #F3F4F6;
        line-height: 1.35;
        margin-bottom: 5px;
    }
    .feed-desc {
        font-size: 13px;
        color: #9CA3AF;
        line-height: 1.4;
    }
    .posted-badge {
        display: inline-block;
        background-color: rgba(74, 222, 128, 0.14);
        color: #4ADE80;
        border: 1px solid rgba(74, 222, 128, 0.35);
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        margin-left: 8px;
    }
    </style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml, text/html, */*",
    "Cache-Control": "no-cache"
}

TAXA_IMPOSTO_POR_SEGUNDO = 108500.00
ARQUIVO_POSTAGENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postagens_hoje.json")

# --- PERSISTÊNCIA DO HISTÓRICO DIÁRIO ---

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
        return "Hoje"
    try:
        dt = parsedate_to_datetime(pub_date_str)
        return dt.strftime("%d/%m às %H:%M")
    except Exception:
        return pub_date_str[:16]

def limpar_html_simples(texto):
    if not texto:
        return ""
    sem_tags = re.sub(r"<[^>]+>", " ", texto)
    sem_entidades = (
        sem_tags.replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )
    return re.sub(r"\s+", " ", sem_entidades).strip()

def calcular_impostometro_estimado():
    agora = datetime.now()
    inicio_ano = datetime(agora.year, 1, 1)
    segundos_passados = max(0.0, (agora - inicio_ano).total_seconds())
    return segundos_passados * TAXA_IMPOSTO_POR_SEGUNDO

# --- BUSCA DE COTAÇÕES E INDICADORES ---

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
        resultado["status_http"] = f"Fallback ({type(e).__name__})"

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

# --- FEEDS RSS MULTI-EDITORIA ---

FEEDS_POR_EDITORIA = {
    "economia": [
        ("InfoMoney", "https://www.infomoney.com.br/feed/"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"),
        ("G1 Economia", "https://g1.globo.com/rss/g1/economia/"),
        ("UOL Economia", "https://rss.uol.com.br/feed/economia.xml"),
    ],
    "gerais": [
        ("G1 Brasil", "https://g1.globo.com/rss/g1/brasil/"),
        ("G1 Mundo", "https://g1.globo.com/rss/g1/mundo/"),
        ("Folha Poder", "https://feeds.folha.uol.com.br/poder/rss091.xml"),
        ("Folha Cotidiano", "https://feeds.folha.uol.com.br/cotidiano/rss091.xml"),
        ("UOL Notícias", "https://rss.uol.com.br/feed/noticias.xml"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"),
    ],
    "entretenimento": [
        ("Gshow", "https://gshow.globo.com/rss/gshow/"),
        ("UOL Splash", "https://www.uol.com.br/splash/rss.xml"),
        ("G1 Pop & Arte", "https://g1.globo.com/rss/g1/pop-arte/"),
        ("Superinteressante", "https://super.abril.com.br/feed/"),
        ("TecMundo", "https://rss.tecmundo.com.br/feed"),
    ]
}

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
        html = resp.text[:30000]
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""

@st.cache_data(ttl=240, show_spinner=False)
def buscar_feed_editoria(editoria="economia", portal_filtro="Todos os portais"):
    lista_feeds = FEEDS_POR_EDITORIA.get(editoria, [])
    itens = []
    titulos_vistos = set()

    for fonte, url in lista_feeds:
        if portal_filtro != "Todos os portais" and fonte != portal_filtro:
            continue
        try:
            resp = requests.get(url, headers=HEADERS, timeout=6)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            for item in root.findall(".//item")[:12]:
                titulo = limpar_html_simples(item.findtext("title") or "")
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                resumo = limpar_html_simples(item.findtext("description") or "")
                img_url = extrair_imagem_rss_item(item)

                if not titulo or titulo.lower() in titulos_vistos:
                    continue
                titulos_vistos.add(titulo.lower())

                if resumo.lower() == titulo.lower():
                    resumo = ""

                itens.append({
                    "fonte": fonte,
                    "titulo": titulo,
                    "resumo": resumo[:230] + ("..." if len(resumo) > 230 else ""),
                    "link": link,
                    "img_url": img_url,
                    "data_fmt": formatar_data_rss(pub_date)
                })
        except Exception:
            continue

    return itens[:24]

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

# --- CONTADOR JS (SEM CONFLITO DE CHAVES) ---

def renderizar_contador_js(valor_inicial_float):
    html_code = """
    <div style="font-family: Inter, sans-serif; padding: 6px 0;">
        <div id="contador-imposto" style="font-size: 30px; font-weight: 800; color: #FBBF24;">
            Carregando...
        </div>
        <div style="font-size: 12px; color: #9CA3AF; margin-top: 4px;">
            Estimativa acumulada desde 1º de janeiro (atualização em tempo real no navegador).
        </div>
    </div>
    <script>
        let valorAtual = __VALOR_INICIAL__;
        const taxaPorSegundo = __TAXA_SEGUNDO__;
        const el = document.getElementById("contador-imposto");

        function formatarBRL(num) {
            return "R$ " + num.toLocaleString("pt-BR", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        }

        function atualizar() {
            el.textContent = formatarBRL(valorAtual);
            valorAtual += taxaPorSegundo;
        }

        atualizar();
        setInterval(atualizar, 1000);
    </script>
    """.replace("__VALOR_INICIAL__", f"{valor_inicial_float:.2f}").replace("__TAXA_SEGUNDO__", f"{TAXA_IMPOSTO_POR_SEGUNDO:.2f}")
    components.html(html_code, height=80)

# --- COMPARTILHAMENTO NATIVO DO DISPOSITIVO ---

def renderizar_bloco_publicacao_interativo(png_bytes_io, nome_arquivo, texto_compartilhar, link_url=""):
    png_bytes_io.seek(0)
    b64_png = base64.b64encode(png_bytes_io.read()).decode("utf-8")
    png_bytes_io.seek(0)

    texto_seguro = json.dumps(texto_compartilhar)
    link_seguro = json.dumps(link_url)
    nome_seguro = json.dumps(nome_arquivo)

    html = """
    <div style="font-family: Inter, sans-serif; display: flex; flex-direction: column; gap: 8px; margin-top: 4px;">
        <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
            <button id="btn-share" style="
                background: linear-gradient(135deg, #2563EB, #0EA5E9);
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 12px 18px;
                font-size: 14px;
                font-weight: 700;
                cursor: pointer;
                flex: 1;
                min-width: 190px;
            ">📤 Compartilhar no Dispositivo</button>

            <a id="btn-dl-fallback" download="__NOME_ARQ_ATTR__" href="data:image/png;base64,__B64_PNG__" style="
                background: #1F2937;
                color: #E5E7EB;
                border: 1px solid #374151;
                border-radius: 10px;
                padding: 11px 16px;
                font-size: 13px;
                font-weight: 600;
                text-decoration: none;
                text-align: center;
            ">⬇️ Baixar PNG</a>
        </div>
        <div id="share-status" style="font-size: 12px; color: #9CA3AF;">
            Toque em Compartilhar para abrir WhatsApp, Instagram ou outro app do celular.
        </div>
    </div>

    <script>
        const b64Data = "__B64_PNG__";
        const fileName = __NOME_JSON__;
        const shareText = __TEXTO_JSON__;
        const shareUrl = __LINK_JSON__;
        const statusEl = document.getElementById("share-status");
        const btnShare = document.getElementById("btn-share");

        function b64ToFile(b64, filename, mimeType) {
            const byteCharacters = atob(b64);
            const byteArrays = [];
            for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                const slice = byteCharacters.slice(offset, offset + 512);
                const byteNumbers = new Array(slice.length);
                for (let i = 0; i < slice.length; i++) {
                    byteNumbers[i] = slice.charCodeAt(i);
                }
                byteArrays.push(new Uint8Array(byteNumbers));
            }
            const blob = new Blob(byteArrays, { type: mimeType });
            return new File([blob], filename, { type: mimeType });
        }

        btnShare.addEventListener("click", async () => {
            try {
                if (!navigator.share) {
                    statusEl.textContent = "Compartilhamento direto indisponível aqui. Use 'Baixar PNG'.";
                    return;
                }

                const file = b64ToFile(b64Data, fileName, "image/png");
                const payloadComArquivo = {
                    title: "Radar Studio",
                    text: shareUrl ? (shareText + "\\n" + shareUrl) : shareText,
                    files: [file]
                };

                if (navigator.canShare && navigator.canShare({ files: [file] })) {
                    await navigator.share(payloadComArquivo);
                    statusEl.textContent = "✅ Menu de compartilhamento aberto!";
                    return;
                }

                await navigator.share({
                    title: "Radar Studio",
                    text: shareText,
                    url: shareUrl || undefined
                });
                statusEl.textContent = "✅ Texto/link compartilhados! Para a imagem, toque em 'Baixar PNG'.";
            } catch (err) {
                if (err && err.name === "AbortError") {
                    statusEl.textContent = "Compartilhamento cancelado.";
                } else {
                    statusEl.textContent = "Não foi possível abrir o menu nativo aqui. Use 'Baixar PNG'.";
                }
            }
        });
    </script>
    """
    html = (
        html.replace("__B64_PNG__", b64_png)
        .replace("__NOME_ARQ_ATTR__", nome_arquivo)
        .replace("__NOME_JSON__", nome_seguro)
        .replace("__TEXTO_JSON__", texto_seguro)
        .replace("__LINK_JSON__", link_seguro)
    )
    components.html(html, height=96)

# --- GERAÇÃO DE CARDS EDITORIAIS PREMIUM (PILLOW) ---

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

    fundo_base = "#070B12"
    card_bg = "#101726"
    borda_sutil = "#1E293B"

    img = Image.new("RGB", (largura, altura), color=fundo_base)
    draw = ImageDraw.Draw(img)

    bold_c = ["ARIALBD.TTF", "ARIBLK.TTF", "ARIAL.TTF", "arialbd.ttf", "arial.ttf"]
    reg_c = ["ARIAL.TTF", "ARIALBD.TTF", "arial.ttf", "arialbd.ttf"]

    f_marca = carregar_fonte_segura(bold_c, 24)
    f_data = carregar_fonte_segura(reg_c, 20)
    f_chapeu = carregar_fonte_segura(bold_c, 23)
    f_destaque = carregar_fonte_segura(bold_c, 84)
    f_manchete = carregar_fonte_segura(bold_c, 44 if eh_stories else 38)
    f_resumo = carregar_fonte_segura(reg_c, 29 if eh_stories else 25)
    f_rodape = carregar_fonte_segura(reg_c, 20)

    margem_x = 64
    topo_y = 105 if eh_stories else 44
    rodape_y = altura - (88 if eh_stories else 54)
    foto_w = largura - (margem_x * 2)

    draw.rounded_rectangle([margem_x, topo_y, margem_x + 120, topo_y + 7], radius=4, fill=cor_destaque)
    draw.text((margem_x, topo_y + 18), "RADAR STUDIO • INFORMAÇÃO", fill="#F8FAFC", font=f_marca)
    draw.text((margem_x, topo_y + 49), f"{fonte_nome}  •  {data_hora}", fill="#94A3B8", font=f_data)

    bloco_y = topo_y + 92
    foto_pronta = baixar_e_ajustar_imagem(url_imagem, foto_w, 360) if url_imagem else None

    if foto_pronta:
        altura_bloco_texto = 460 if eh_stories else 380
        draw.rounded_rectangle(
            [margem_x, bloco_y, largura - margem_x, bloco_y + altura_bloco_texto],
            radius=24,
            fill=card_bg,
            outline=borda_sutil,
            width=2
        )
        draw.rounded_rectangle(
            [margem_x, bloco_y + 26, margem_x + 9, bloco_y + altura_bloco_texto - 26],
            radius=5,
            fill=cor_destaque
        )

        inner_x = margem_x + 38
        cur_y = bloco_y + 28
        draw.text((inner_x, cur_y), chapeu.upper(), fill=cor_destaque, font=f_chapeu)
        cur_y += 40

        linhas_manchete = textwrap.wrap(manchete, width=36 if eh_stories else 40)
        for linha in linhas_manchete[:4]:
            draw.text((inner_x, cur_y), linha, fill="#F8FAFC", font=f_manchete)
            cur_y += 48 if eh_stories else 43

        if resumo:
            cur_y += 12
            linhas_resumo = textwrap.wrap(resumo, width=52 if eh_stories else 56)
            for linha in linhas_resumo[:3]:
                if cur_y > bloco_y + altura_bloco_texto - 34:
                    break
                draw.text((inner_x, cur_y), linha, fill="#CBD5E1", font=f_resumo)
                cur_y += 34 if eh_stories else 31

        foto_y = bloco_y + altura_bloco_texto + 24
        foto_h = max(240, rodape_y - foto_y - 22)
        foto_ajustada = baixar_e_ajustar_imagem(url_imagem, foto_w, foto_h)
        if foto_ajustada:
            mascara = criar_mascara_arredondada(foto_w, foto_h, 24)
            img.paste(foto_ajustada, (margem_x, foto_y), mascara)
            draw.rounded_rectangle([margem_x, foto_y, margem_x + foto_w, foto_y + foto_h], radius=24, outline=borda_sutil, width=2)
    else:
        card_bot = rodape_y - 24
        draw.rounded_rectangle(
            [margem_x, bloco_y, largura - margem_x, card_bot],
            radius=28,
            fill=card_bg,
            outline=borda_sutil,
            width=2
        )
        draw.rounded_rectangle(
            [margem_x, bloco_y + 32, margem_x + 11, card_bot - 32],
            radius=6,
            fill=cor_destaque
        )

        inner_x = margem_x + 48
        cur_y = bloco_y + 46

        draw.text((inner_x, cur_y), chapeu.upper(), fill=cor_destaque, font=f_chapeu)
        cur_y += 54

        if destaque_valor:
            box_val_top = cur_y
            box_val_bot = cur_y + 160
            draw.rounded_rectangle(
                [inner_x, box_val_top, largura - margem_x - 48, box_val_bot],
                radius=22,
                fill="#0B1120",
                outline=cor_destaque,
                width=2
            )
            draw.text((inner_x + 34, box_val_top + 34), destaque_valor, fill="#FFFFFF", font=f_destaque)
            cur_y = box_val_bot + 46

        linhas_manchete = textwrap.wrap(manchete, width=34 if eh_stories else 38)
        for linha in linhas_manchete[:5]:
            draw.text((inner_x, cur_y), linha, fill="#F8FAFC", font=f_manchete)
            cur_y += 52 if eh_stories else 46

        if resumo:
            cur_y += 22
            linhas_resumo = textwrap.wrap(resumo, width=48 if eh_stories else 54)
            for linha in linhas_resumo[:7]:
                if cur_y > card_bot - 48:
                    break
                draw.text((inner_x, cur_y), linha, fill="#CBD5E1", font=f_resumo)
                cur_y += 38 if eh_stories else 34

    draw.text((margem_x, rodape_y), f"Fonte: {fonte_nome}  •  Radar Studio", fill="#64748B", font=f_rodape)

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
    img = Image.new("RGB", (largura, altura), color="#070B12")
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
    draw.rounded_rectangle([64, y1, 524, y1 + hb], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((90, y1 + 16), "DÓLAR (USD)", fill="#94A3B8", font=f_label)
    draw.text((90, y1 + 54), usd_str, fill=c_usd, font=f_valor)
    draw.text((90, y1 + 114), usd_var_str, fill=c_usd, font=f_var)

    c_eur = "#F87171" if eur_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([556, y1, 1016, y1 + hb], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((582, y1 + 16), "EURO (EUR)", fill="#94A3B8", font=f_label)
    draw.text((582, y1 + 54), eur_str, fill=c_eur, font=f_valor)
    draw.text((582, y1 + 114), eur_var_str, fill=c_eur, font=f_var)

    y2 = y1 + esp
    c_btc = "#4ADE80" if btc_pct_val >= 0 else "#F87171"
    draw.rounded_rectangle([64, y2, 524, y2 + hb], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((90, y2 + 16), "BITCOIN (BTC)", fill="#94A3B8", font=f_label)
    draw.text((90, y2 + 54), btc_str, fill="#F59E0B", font=f_valor)
    if btc_var_str:
        draw.text((90, y2 + 114), btc_var_str, fill=c_btc, font=f_var)

    c_ibov = "#4ADE80" if ibov_pct_val >= 0 else "#F87171"
    draw.rounded_rectangle([556, y2, 1016, y2 + hb], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((582, y2 + 16), "IBOVESPA", fill="#94A3B8", font=f_label)
    draw.text((582, y2 + 54), ibov_str, fill="#60A5FA", font=f_valor)
    if ibov_var_str:
        draw.text((582, y2 + 114), ibov_var_str, fill=c_ibov, font=f_var)

    y3 = y2 + esp
    hm = 154 if eh_stories else 140
    draw.rounded_rectangle([64, y3, 524, y3 + hm], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((90, y3 + 16), "TAXA SELIC (META)", fill="#94A3B8", font=f_label)
    draw.text((90, y3 + 58), selic_str, fill="#38BDF8", font=f_valor)

    draw.rounded_rectangle([556, y3, 1016, y3 + hm], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((582, y3 + 16), "IPCA (ÚLTIMO MÊS)", fill="#94A3B8", font=f_label)
    draw.text((582, y3 + 58), ipca_str, fill="#F472B6", font=f_valor)

    y4 = y3 + (178 if eh_stories else 162)
    hi = 210 if eh_stories else 190
    draw.rounded_rectangle([64, y4, 1016, y4 + hi], radius=20, fill="#101726", outline="#1E293B", width=2)
    draw.text((90, y4 + 22), "ARRECADAÇÃO ESTIMADA NO ANO", fill="#94A3B8", font=f_label)
    draw.text((90, y4 + 78), imposto_str, fill="#FBBF24", font=f_imp)

    y_rod = (y4 + hi + 70) if eh_stories else 976
    draw.text((64, y_rod), "Fontes: BCB, AwesomeAPI, Frankfurter, CoinGecko & Yahoo Finance", fill="#64748B", font=f_rodape)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# --- BUSCA DE DADOS INICIAIS ---

data_atual_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
postados_hoje = carregar_postagens_hoje()

cotacoes_data = buscar_cotacoes()
dolar = cotacoes_data["usd"]
euro = cotacoes_data["eur"]
btc = cotacoes_data["btc"]
fonte_moedas = cotacoes_data["fonte_moedas"]
fonte_btc = cotacoes_data["fonte_btc"]

selic_valor, selic_data, selic_fallback = buscar_selic()
ipca_valor, ipca_data, ipca_fallback = buscar_ipca_mensal()
ibov_pontos, ibov_pct, ibov_indisponivel, fonte_ibov = buscar_ibovespa()

usd_formatado = formatar_brl(float(dolar["bid"])) if dolar else "Indisponível"
usd_pct_num = float(dolar["pctChange"]) if dolar else 0.0
usd_var_str = formatar_variacao(usd_pct_num) if dolar else "0,00% hoje"

eur_formatado = formatar_brl(float(euro["bid"])) if euro else "Indisponível"
eur_pct_num = float(euro["pctChange"]) if euro else 0.0
eur_var_str = formatar_variacao(eur_pct_num) if euro else "0,00% hoje"

btc_formatado = formatar_brl(float(btc["bid"])) if btc else "Indisponível"
btc_pct_num = float(btc["pctChange"]) if btc else 0.0
btc_var_str = formatar_variacao(btc_pct_num) if btc else ""

ibov_formatado = formatar_pontos(ibov_pontos) if (not ibov_indisponivel and ibov_pontos) else "Indisponível"
ibov_pct_num = ibov_pct or 0.0
ibov_var_str = formatar_variacao(ibov_pct_num) if (not ibov_indisponivel and ibov_pontos) else ""

selic_formatada = f"{selic_valor:.2f}".replace(".", ",") + "% a.a." if selic_valor is not None else "Indisponível"
sinal_ipca = "+" if (ipca_valor is not None and ipca_valor > 0) else ""
ipca_formatada = f"{sinal_ipca}{ipca_valor:.2f}".replace(".", ",") + "% a.m." if ipca_valor is not None else "Indisponível"

imposto_atual_float = calcular_impostometro_estimado()
imposto_atual_fmt = formatar_brl(imposto_atual_float)

if "item_estudio" not in st.session_state:
    st.session_state["item_estudio"] = {
        "tipo": "indicador",
        "chapeu": "CÂMBIO • MERCADO",
        "manchete": "Dólar Comercial (USD)",
        "resumo": f"Cotação atualizada ({usd_var_str}).",
        "destaque": usd_formatado,
        "fonte": fonte_moedas,
        "link": "",
        "img_url": "",
        "cor": "#4ADE80"
    }

if "abrir_modal_estudio" not in st.session_state:
    st.session_state["abrir_modal_estudio"] = False

def acionar_card_no_modal(payload_item):
    st.session_state["item_estudio"] = payload_item
    st.session_state["abrir_modal_estudio"] = True
    st.rerun()

# --- MODAL FLUTUANTE DE PUBLICAÇÃO (RÁPIDO NO CELULAR E DESKTOP) ---

@st.dialog("🎨 Estúdio de Publicação", width="medium")
def mostrar_modal_publicacao():
    item_sel = st.session_state["item_estudio"]
    postados_atual = carregar_postagens_hoje()

    formato_card = st.radio(
        "Formato",
        options=["Feed (1080x1080)", "Stories (1080x1920)"],
        horizontal=True,
        key="formato_modal_radio"
    )
    sufixo_f = "stories" if "1080x1920" in formato_card else "feed"

    with st.expander("✏️ Ajustar texto do card (opcional)", expanded=False):
        manchete_edit = st.text_input("Título / Manchete", value=item_sel["manchete"], key="edit_tit_modal")
        resumo_edit = st.text_area("Resumo / Legenda", value=item_sel["resumo"], height=75, key="edit_res_modal")
    if "manchete_edit" not in locals():
        manchete_edit = item_sel["manchete"]
        resumo_edit = item_sel["resumo"]

    img_url_final = item_sel.get("img_url") or (
        buscar_og_image_da_pagina(item_sel.get("link", "")) if item_sel.get("link") else ""
    )

    chave_estudio = gerar_chave_item(item_sel["tipo"], item_sel["manchete"], item_sel["fonte"])
    if chave_estudio in postados_atual:
        st.warning(f"⚠️ Já postado hoje às **{postados_atual[chave_estudio]['hora']}** (você ainda pode repetir).")

    card_pronto = gerar_card_editorial(
        chapeu=item_sel["chapeu"],
        manchete=manchete_edit,
        resumo=resumo_edit,
        destaque_valor=item_sel.get("destaque", ""),
        fonte_nome=item_sel["fonte"],
        data_hora=data_atual_str,
        url_imagem=img_url_final,
        cor_destaque=item_sel.get("cor", "#38BDF8"),
        formato=formato_card
    )

    st.image(card_pronto, use_container_width=True)

    texto_comp = f"{manchete_edit} ({item_sel['fonte']})"
    renderizar_bloco_publicacao_interativo(
        png_bytes_io=card_pronto,
        nome_arquivo=f"post_{item_sel['tipo']}_{sufixo_f}_{datetime.now().strftime('%H%M')}.png",
        texto_compartilhar=texto_comp,
        link_url=item_sel.get("link", "")
    )

    c_mk, c_fechar = st.columns(2)
    with c_mk:
        if st.button("✅ Marcar como postado", key="btn_mk_modal", use_container_width=True):
            registrar_postagem_hoje(chave_estudio, manchete_edit[:80])
            st.session_state["abrir_modal_estudio"] = False
            st.rerun()
    with c_fechar:
        if st.button("✖️ Fechar", key="btn_close_modal", use_container_width=True):
            st.session_state["abrir_modal_estudio"] = False
            st.rerun()

    if item_sel.get("link"):
        st.markdown(f"🔗 **Link da fonte:** [{item_sel['link']}]({item_sel['link']})")

# --- TOPO EDITORIAL ---
st.markdown(f"""
    <div class="hero-banner">
        <div>
            <div class="hero-title">📡 Radar Studio — Central de Conteúdo & Mercado</div>
            <div class="hero-sub">Toque em "Criar Card" em qualquer item para abrir o card na hora por cima da tela.</div>
        </div>
        <div class="status-pill">
            🕒 {data_atual_str[14:]} • {cotacoes_data["status_http"]} • 📌 {len(postados_hoje)} postados hoje
        </div>
    </div>
""", unsafe_allow_html=True)

b_col1, b_col2, b_col3 = st.columns([1.2, 1.4, 1.4])
with b_col1:
    if st.button("🔄 Atualizar Tudo", use_container_width=True):
        buscar_cotacoes.clear()
        buscar_ibovespa.clear()
        buscar_feed_editoria.clear()
        buscar_proposicoes_camara.clear()
        buscar_og_image_da_pagina.clear()
        st.rerun()
with b_col2:
    if st.button("🎨 Reabrir Último Card", use_container_width=True):
        st.session_state["abrir_modal_estudio"] = True
        st.rerun()
with b_col3:
    if postados_hoje and st.button("🧹 Limpar Postados Hoje", use_container_width=True):
        limpar_postagens_hoje()
        st.rerun()

# --- LISTAGEM DE CONTEÚDO EM LARGURA TOTAL ---

def renderizar_lista_noticias(itens_news, prefixo_btn, cor_editoria, tag_editoria):
    if not itens_news:
        st.info("Nenhuma matéria carregada neste filtro no momento.")
        return

    for idx, item in enumerate(itens_news):
        chave = gerar_chave_item(prefixo_btn, item["titulo"], item["fonte"])
        badge = f'<span class="posted-badge">Já postado hoje às {postados_hoje[chave]["hora"]}</span>' if chave in postados_hoje else ""

        c_txt, c_act = st.columns([4.4, 1.1])
        with c_txt:
            st.markdown(
                f'<div class="feed-item">'
                f'<div class="feed-meta" style="color:{cor_editoria};">{item["fonte"]} • {item["data_fmt"]}{badge}</div>'
                f'<div class="feed-title">{item["titulo"]}</div>'
                f'<div class="feed-desc">{item["resumo"]}</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with c_act:
            if st.button("🎨 Criar Card", key=f"btn_{prefixo_btn}_{idx}", use_container_width=True):
                acionar_card_no_modal({
                    "tipo": prefixo_btn,
                    "chapeu": f"{tag_editoria} • {item['data_fmt']}",
                    "manchete": item["titulo"],
                    "resumo": item["resumo"] or "Confira os detalhes completos na fonte original.",
                    "destaque": "",
                    "fonte": item["fonte"],
                    "link": item["link"],
                    "img_url": item["img_url"],
                    "cor": cor_editoria
                })

aba_econ, aba_gerais, aba_fofocas, aba_camara, aba_ferramentas = st.tabs([
    "💹 Mercado & Economia",
    "🌍 Notícias Gerais",
    "✨ Fofocas & Curiosidades",
    "🏛️ Câmara",
    "📈 Gráficos & Resumo"
])

with aba_econ:
    k1, k2, k3 = st.columns(3)
    with k1:
        cls_u = "kpi-delta-down" if usd_pct_num > 0 else "kpi-delta-up"
        st.markdown(f'<div class="kpi-box"><div class="kpi-label">💵 Dólar (USD)</div><div class="kpi-val">{usd_formatado}</div><div class="{cls_u}">{usd_var_str} • {fonte_moedas}</div></div>', unsafe_allow_html=True)
        if st.button("🎨 Card Dólar", key="kpi_usd", use_container_width=True):
            acionar_card_no_modal({"tipo": "indicador", "chapeu": "CÂMBIO • MERCADO", "manchete": "Dólar Comercial (USD)", "resumo": f"Variação diária: {usd_var_str}.", "destaque": usd_formatado, "fonte": fonte_moedas, "link": "", "img_url": "", "cor": "#4ADE80"})
    with k2:
        cls_e = "kpi-delta-down" if eur_pct_num > 0 else "kpi-delta-up"
        st.markdown(f'<div class="kpi-box"><div class="kpi-label">💶 Euro (EUR)</div><div class="kpi-val">{eur_formatado}</div><div class="{cls_e}">{eur_var_str} • {fonte_moedas}</div></div>', unsafe_allow_html=True)
        if st.button("🎨 Card Euro", key="kpi_eur", use_container_width=True):
            acionar_card_no_modal({"tipo": "indicador", "chapeu": "CÂMBIO • MERCADO", "manchete": "Euro Comercial (EUR)", "resumo": f"Variação diária: {eur_var_str}.", "destaque": eur_formatado, "fonte": fonte_moedas, "link": "", "img_url": "", "cor": "#60A5FA"})
    with k3:
        cls_b = "kpi-delta-up" if btc_pct_num >= 0 else "kpi-delta-down"
        st.markdown(f'<div class="kpi-box"><div class="kpi-label">₿ Bitcoin (BTC)</div><div class="kpi-val">{btc_formatado}</div><div class="{cls_b}">{btc_var_str} • {fonte_btc}</div></div>', unsafe_allow_html=True)
        if st.button("🎨 Card Bitcoin", key="kpi_btc", use_container_width=True):
            acionar_card_no_modal({"tipo": "indicador", "chapeu": "CRIPTOATIVOS", "manchete": "Bitcoin (BTC)", "resumo": f"Oscilação 24h: {btc_var_str}.", "destaque": btc_formatado, "fonte": fonte_btc, "link": "", "img_url": "", "cor": "#F59E0B"})

    k4, k5, k6 = st.columns(3)
    with k4:
        cls_i = "kpi-delta-up" if ibov_pct_num >= 0 else "kpi-delta-down"
        st.markdown(f'<div class="kpi-box"><div class="kpi-label">📉 Ibovespa</div><div class="kpi-val">{ibov_formatado}</div><div class="{cls_i}">{ibov_var_str or "Ref. mercado"} • {fonte_ibov}</div></div>', unsafe_allow_html=True)
        if st.button("🎨 Card Ibovespa", key="kpi_ibov", use_container_width=True):
            acionar_card_no_modal({"tipo": "indicador", "chapeu": "BOLSA • B3", "manchete": "Ibovespa (^BVSP)", "resumo": f"Desempenho: {ibov_var_str or 'acompanhamento diário'}.", "destaque": ibov_formatado, "fonte": fonte_ibov, "link": "", "img_url": "", "cor": "#38BDF8"})
    with k5:
        st.markdown(f'<div class="kpi-box"><div class="kpi-label">🏦 Taxa Selic</div><div class="kpi-val">{selic_formatada}</div><div class="kpi-delta-neutral">Ref: {selic_data} • BCB</div></div>', unsafe_allow_html=True)
        if st.button("🎨 Card Selic", key="kpi_selic", use_container_width=True):
            acionar_card_no_modal({"tipo": "indicador", "chapeu": "JUROS • COPOM", "manchete": "Taxa Selic (Meta Anual)", "resumo": f"Data de referência oficial: {selic_data}.", "destaque": selic_formatada, "fonte": "Banco Central", "link": "", "img_url": "", "cor": "#38BDF8"})
    with k6:
        st.markdown(f'<div class="kpi-box"><div class="kpi-label">🏷️ IPCA Mensal</div><div class="kpi-val">{ipca_formatada}</div><div class="kpi-delta-neutral">Ref: {ipca_data} • IBGE/BCB</div></div>', unsafe_allow_html=True)
        if st.button("🎨 Card IPCA", key="kpi_ipca", use_container_width=True):
            acionar_card_no_modal({"tipo": "indicador", "chapeu": "INFLAÇÃO • BRASIL", "manchete": "IPCA Mensal Oficial", "resumo": f"Data de referência: {ipca_data}.", "destaque": ipca_formatada, "fonte": "Banco Central", "link": "", "img_url": "", "cor": "#F472B6"})

    st.divider()
    portais_econ = ["Todos os portais"] + [p[0] for p in FEEDS_POR_EDITORIA["economia"]]
    filtro_econ = st.selectbox("Portal de Economia", options=portais_econ, key="filtro_econ")
    news_econ = buscar_feed_editoria("economia", filtro_econ)
    renderizar_lista_noticias(news_econ, "economia", "#38BDF8", "ECONOMIA")

with aba_gerais:
    st.caption("Principais manchetes do Brasil e do mundo (G1, Folha, UOL, Agência Brasil).")
    portais_ger = ["Todos os portais"] + [p[0] for p in FEEDS_POR_EDITORIA["gerais"]]
    filtro_ger = st.selectbox("Filtrar por portal", options=portais_ger, key="filtro_ger")
    news_gerais = buscar_feed_editoria("gerais", filtro_ger)
    renderizar_lista_noticias(news_gerais, "gerais", "#4ADE80", "BRASIL & MUNDO")

with aba_fofocas:
    st.caption("Famosos, TV, cultura pop, ciência e curiosidades (Gshow, UOL Splash, G1 Pop & Arte, Superinteressante, TecMundo).")
    portais_ent = ["Todos os portais"] + [p[0] for p in FEEDS_POR_EDITORIA["entretenimento"]]
    filtro_ent = st.selectbox("Filtrar por portal", options=portais_ent, key="filtro_ent")
    news_ent = buscar_feed_editoria("entretenimento", filtro_ent)
    renderizar_lista_noticias(news_ent, "entretenimento", "#F472B6", "POP & CURIOSIDADES")

with aba_camara:
    st.caption("Proposições apresentadas recentemente na Câmara dos Deputados.")
    props = buscar_proposicoes_camara(10)
    if props:
        for idx, p in enumerate(props):
            chave_p = gerar_chave_item("camara", p["codigo"], p["ementa"])
            badge_p = f'<span class="posted-badge">Já postado hoje às {postados_hoje[chave_p]["hora"]}</span>' if chave_p in postados_hoje else ""
            url_p = f"https://www.camara.leg.br/proposicoesWeb/fichadetailid?idProposicao={p['id']}" if p.get("id") else ""

            c_pt, c_pb = st.columns([4.4, 1.1])
            with c_pt:
                st.markdown(
                    f'<div class="feed-item">'
                    f'<div class="feed-meta" style="color:#FBBF24;">CÂMARA DOS DEPUTADOS{badge_p}</div>'
                    f'<div class="feed-title">{p["codigo"]}</div>'
                    f'<div class="feed-desc">{p["ementa"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
            with c_pb:
                if st.button("🎨 Criar Card", key=f"btn_pl_{idx}", use_container_width=True):
                    acionar_card_no_modal({
                        "tipo": "camara",
                        "chapeu": "CONGRESSO • CÂMARA",
                        "manchete": p["codigo"],
                        "resumo": p["ementa"],
                        "destaque": "",
                        "fonte": "Dados Abertos Câmara",
                        "link": url_p,
                        "img_url": "",
                        "cor": "#FBBF24"
                    })
    else:
        st.info("Consulta à Câmara temporariamente indisponível.")

with aba_ferramentas:
    st.subheader("📈 Histórico de Mercado")
    ca, cd = st.columns([2, 1])
    with ca:
        ativo_esc = st.selectbox("Ativo", ["USD-BRL", "EUR-BRL", "BTC-BRL", "IBOV"])
    with cd:
        dias_esc = st.selectbox("Dias", [7, 30, 90], index=1)
    serie_h = buscar_historico_ativo(ativo_esc, dias_esc)
    if serie_h:
        st.line_chart(serie_h, height=240)

    st.subheader("⏱️ Arrecadação Tributária Estimada")
    renderizar_contador_js(imposto_atual_float)
    if st.button("🎨 Gerar Card da Arrecadação", key="btn_card_imp"):
        acionar_card_no_modal({
            "tipo": "indicador",
            "chapeu": "CONTAS PÚBLICAS • BRASIL",
            "manchete": "Arrecadação Tributária Estimada",
            "resumo": "Projeção contínua acumulada desde 1º de janeiro.",
            "destaque": imposto_atual_fmt,
            "fonte": "Estimativa Fiscal",
            "link": "",
            "img_url": "",
            "cor": "#FBBF24"
        })

    st.divider()
    st.subheader("📊 Card Resumo Geral (Todos os Índices)")
    fmt_resumo = st.radio("Formato Resumo", ["Feed (1080x1080)", "Stories (1080x1920)"], horizontal=True)
    img_res = gerar_card_resumo(
        usd_formatado, usd_var_str, usd_pct_num,
        eur_formatado, eur_var_str, eur_pct_num,
        btc_formatado, btc_var_str, btc_pct_num,
        ibov_formatado, ibov_var_str, ibov_pct_num,
        ipca_formatada, selic_formatada, imposto_atual_fmt,
        data_atual_str, formato=fmt_resumo
    )
    st.image(img_res, width=380)
    renderizar_bloco_publicacao_interativo(
        img_res,
        f"resumo_radar_{datetime.now().strftime('%H%M')}.png",
        f"Resumo Econômico ({data_atual_str}): Dólar {usd_formatado} | Euro {eur_formatado} | Selic {selic_formatada}"
    )

if postados_hoje:
    with st.expander(f"📋 Histórico de postagens de hoje ({len(postados_hoje)})", expanded=False):
        for info in postados_hoje.values():
            st.markdown(f"- `{info['hora']}` — {info['rotulo']}")

if st.session_state.get("abrir_modal_estudio"):
    mostrar_modal_publicacao()