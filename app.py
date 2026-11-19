import streamlit as st
import streamlit.components.v1 as components
import requests
import io
import os
import json
import hashlib
import textwrap
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="Radar Económico e Fiscal - Estúdio de Informação",
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
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
    }
    .source-text {
        font-size: 12px;
        color: #888888;
    }
    .news-card {
        padding: 12px 16px;
        border-radius: 10px;
        background-color: #161B22;
        border-left: 4px solid #60A5FA;
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
    </style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml",
    "Cache-Control": "no-cache"
}

TAXA_IMPOSTO_POR_SEGUNDO = 108500.00
ARQUIVO_POSTAGENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "postagens_hoje.json")

# --- CONTROLO DE POSTAGENS DO DIA ---

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

# --- FUNÇÕES DE FORMATAÇÃO ---

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

def calcular_impostometro_estimado():
    agora = datetime.now()
    inicio_ano = datetime(agora.year, 1, 1)
    segundos_passados = max(0.0, (agora - inicio_ano).total_seconds())
    return segundos_passados * TAXA_IMPOSTO_POR_SEGUNDO

# --- FUNÇÕES DE BUSCA DE DADOS ---

@st.cache_data(ttl=30, show_spinner=False)
def buscar_cotacoes():
    resultado = {"usd": None, "eur": None, "btc": None, "fonte_moedas": "N/D", "fonte_btc": "N/D"}

    try:
        url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,BTC-BRL"
        response = requests.get(url, headers=HEADERS, timeout=7)
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
    except Exception:
        pass

    if not resultado["usd"] or not resultado["eur"]:
        try:
            hoje = datetime.now().date()
            inicio = hoje - timedelta(days=5)
            if not resultado["usd"]:
                r_usd = requests.get(
                    f"https://api.frankfurter.app/{inicio}..{hoje}?from=USD&to=BRL",
                    headers=HEADERS, timeout=7
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
                    headers=HEADERS, timeout=7
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
            r_btc = requests.get(url_btc, headers=HEADERS, timeout=7).json()
            if "bitcoin" in r_btc:
                preco_brl = float(r_btc["bitcoin"]["brl"])
                var_24h = float(r_btc["bitcoin"].get("brl_24h_change", 0.0))
                resultado["btc"] = {"bid": str(preco_brl), "pctChange": str(round(var_24h, 2))}
                resultado["fonte_btc"] = "CoinGecko"
        except Exception:
            pass

    return resultado

@st.cache_data(ttl=60, show_spinner=False)
def buscar_ibovespa():
    try:
        url = "https://brapi.dev/api/quote/%5EBVSP"
        response = requests.get(url, headers=HEADERS, timeout=7)
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
        response = requests.get(url_yf, headers=HEADERS, timeout=7)
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

        if ativo in ("USD-BRL", "EUR-BRL"):
            moeda = ativo.split("-")[0]
            try:
                fim = datetime.now().date()
                inicio = fim - timedelta(days=dias)
                url = f"https://api.frankfurter.app/{inicio}..{fim}?from={moeda}&to=BRL"
                response = requests.get(url, headers=HEADERS, timeout=7)
                response.raise_for_status()
                dados = response.json().get("rates", {})
                serie = {}
                for data_iso in sorted(dados.keys()):
                    dt_obj = datetime.strptime(data_iso, "%Y-%m-%d")
                    serie[dt_obj.strftime("%d/%m")] = float(dados[data_iso]["BRL"])
                return serie
            except Exception:
                return {}

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

@st.cache_data(ttl=300, show_spinner=False)
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
                titulo = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()

                if not titulo:
                    continue

                texto_lower = titulo.lower()
                if categoria != "Todas" and not any(p in texto_lower for p in palavras):
                    continue

                itens.append({
                    "fonte": fonte,
                    "titulo": titulo,
                    "link": link,
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

# --- COMPONENTE CONTADOR NO NAVEGADOR ---

def renderizar_contador_js(valor_inicial_float):
    html_code = f"""
    <div style="font-family: sans-serif; padding: 8px 0;">
        <div id="contador-imposto" style="font-size: 32px; font-weight: 700; color: #FBBF24;">
            A carregar...
        </div>
        <div style="font-size: 13px; color: #9CA3AF; margin-top: 4px;">
            Projeção contínua acumulada desde 1 de janeiro (atualização local no navegador).
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

# --- FUNÇÕES GERADORAS DE CARD (PILLOW) ---

def carregar_fonte_segura(nomes_candidatos, tamanho):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for nome in nomes_candidatos:
        caminho = os.path.join(base_dir, nome)
        try:
            return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue
    return ImageFont.load_default()

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
    img = Image.new("RGB", (largura, altura), color="#0E1117")
    draw = ImageDraw.Draw(img)

    bold_candidatos = ["ARIALBD.TTF", "ARIBLK.TTF", "ARIAL.TTF", "arialbd.ttf", "arial.ttf"]
    regular_candidatos = ["ARIAL.TTF", "ARIALBD.TTF", "arial.ttf", "arialbd.ttf"]

    fonte_titulo = carregar_fonte_segura(bold_candidatos, 44 if eh_stories else 42)
    fonte_subtitulo = carregar_fonte_segura(regular_candidatos, 25 if eh_stories else 23)
    fonte_label = carregar_fonte_segura(regular_candidatos, 25 if eh_stories else 24)
    fonte_valor = carregar_fonte_segura(bold_candidatos, 40 if eh_stories else 37)
    fonte_var = carregar_fonte_segura(regular_candidatos, 23 if eh_stories else 21)
    fonte_imposto = carregar_fonte_segura(bold_candidatos, 44 if eh_stories else 41)
    fonte_rodape = carregar_fonte_segura(regular_candidatos, 21 if eh_stories else 19)

    offset_y = 95 if eh_stories else 0
    espaco_linha = 235 if eh_stories else 188

    draw.text((65, 45 + offset_y), "RADAR ECONÓMICO & FISCAL", fill="#FFFFFF", font=fonte_titulo)
    draw.text((65, 98 + offset_y), f"Atualizado em {data_hora}", fill="#A0AAB5", font=fonte_subtitulo)

    y1 = 152 + offset_y
    h_box = 185 if eh_stories else 166

    cor_usd = "#F87171" if usd_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([65, y1, 525, y1 + h_box], radius=18, fill="#1E232F")
    draw.text((90, y1 + 16), "DÓLAR (USD)", fill="#A0AAB5", font=fonte_label)
    draw.text((90, y1 + 54), usd_str, fill=cor_usd, font=fonte_valor)
    draw.text((90, y1 + 114), usd_var_str, fill=cor_usd, font=fonte_var)

    cor_eur = "#F87171" if eur_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([555, y1, 1015, y1 + h_box], radius=18, fill="#1E232F")
    draw.text((580, y1 + 16), "EURO (EUR)", fill="#A0AAB5", font=fonte_label)
    draw.text((580, y1 + 54), eur_str, fill=cor_eur, font=fonte_valor)
    draw.text((580, y1 + 114), eur_var_str, fill=cor_eur, font=fonte_var)

    y2 = y1 + espaco_linha
    cor_btc = "#4ADE80" if btc_pct_val >= 0 else "#F87171"
    draw.rounded_rectangle([65, y2, 525, y2 + h_box], radius=18, fill="#1E232F")
    draw.text((90, y2 + 16), "BITCOIN (BTC)", fill="#A0AAB5", font=fonte_label)
    draw.text((90, y2 + 54), btc_str, fill="#F59E0B", font=fonte_valor)
    if btc_var_str:
        draw.text((90, y2 + 114), btc_var_str, fill=cor_btc, font=fonte_var)

    cor_ibov = "#4ADE80" if ibov_pct_val >= 0 else "#F87171"
    draw.rounded_rectangle([555, y2, 1015, y2 + h_box], radius=18, fill="#1E232F")
    draw.text((580, y2 + 16), "IBOVESPA", fill="#A0AAB5", font=fonte_label)
    draw.text((580, y2 + 54), ibov_str, fill="#60A5FA", font=fonte_valor)
    if ibov_var_str:
        draw.text((580, y2 + 114), ibov_var_str, fill=cor_ibov, font=fonte_var)

    y3 = y2 + espaco_linha
    h_macro = 158 if eh_stories else 142
    draw.rounded_rectangle([65, y3, 525, y3 + h_macro], radius=18, fill="#1E232F")
    draw.text((90, y3 + 16), "TAXA SELIC (META)", fill="#A0AAB5", font=fonte_label)
    draw.text((90, y3 + 58), selic_str, fill="#38BDF8", font=fonte_valor)

    draw.rounded_rectangle([555, y3, 1015, y3 + h_macro], radius=18, fill="#1E232F")
    draw.text((580, y3 + 16), "IPCA (ÚLTIMO MÊS)", fill="#A0AAB5", font=fonte_label)
    draw.text((580, y3 + 58), ipca_str, fill="#F472B6", font=fonte_valor)

    y4 = y3 + (182 if eh_stories else 164)
    h_imp = 220 if eh_stories else 195
    draw.rounded_rectangle([65, y4, 1015, y4 + h_imp], radius=18, fill="#1E232F")
    draw.text((90, y4 + 24), "ARRECADAÇÃO ESTIMADA NO ANO", fill="#A0AAB5", font=fonte_label)
    draw.text((90, y4 + 82), imposto_str, fill="#FBBF24", font=fonte_imposto)

    y_rodape = (y4 + h_imp + 75) if eh_stories else 975
    draw.text((65, y_rodape), "Fontes: BCB, AwesomeAPI, Frankfurter, CoinGecko & Yahoo Finance", fill="#6B7280", font=fonte_rodape)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

def gerar_card_item(categoria_tag, titulo_principal, subtitulo_extra, destaque_valor, rodape_fonte, data_hora, formato="Feed (1080x1080)"):
    eh_stories = "1080x1920" in formato
    largura, altura = (1080, 1920) if eh_stories else (1080, 1080)
    img = Image.new("RGB", (largura, altura), color="#0E1117")
    draw = ImageDraw.Draw(img)

    bold_candidatos = ["ARIALBD.TTF", "ARIBLK.TTF", "ARIAL.TTF", "arialbd.ttf", "arial.ttf"]
    regular_candidatos = ["ARIAL.TTF", "ARIALBD.TTF", "arial.ttf", "arialbd.ttf"]

    fonte_marca = carregar_fonte_segura(bold_candidatos, 30)
    fonte_tag = carregar_fonte_segura(bold_candidatos, 26)
    fonte_destaque = carregar_fonte_segura(bold_candidatos, 66)
    fonte_titulo = carregar_fonte_segura(bold_candidatos, 42)
    fonte_corpo = carregar_fonte_segura(regular_candidatos, 30)
    fonte_rodape = carregar_fonte_segura(regular_candidatos, 22)

    topo_y = 140 if eh_stories else 65
    draw.text((70, topo_y), "RADAR ECONÓMICO & FISCAL", fill="#60A5FA", font=fonte_marca)
    draw.text((70, topo_y + 44), f"{data_hora}  •  {rodape_fonte}", fill="#9CA3AF", font=fonte_rodape)

    card_top = topo_y + 100
    card_bot = altura - (200 if eh_stories else 120)
    draw.rounded_rectangle([70, card_top, 1010, card_bot], radius=24, fill="#161B22")

    draw.text((110, card_top + 35), categoria_tag.upper(), fill="#FBBF24", font=fonte_tag)

    y_cursor = card_top + 90
    if destaque_valor:
        draw.text((110, y_cursor), destaque_valor, fill="#FFFFFF", font=fonte_destaque)
        y_cursor += 105

    linhas_titulo = textwrap.wrap(titulo_principal, width=34 if eh_stories else 36)
    for linha in linhas_titulo[:6]:
        draw.text((110, y_cursor), linha, fill="#F3F4F6", font=fonte_titulo)
        y_cursor += 54

    if subtitulo_extra:
        y_cursor += 20
        linhas_sub = textwrap.wrap(subtitulo_extra, width=48)
        for linha in linhas_sub[:7]:
            if y_cursor > card_bot - 55:
                break
            draw.text((110, y_cursor), linha, fill="#A0AAB5", font=fonte_corpo)
            y_cursor += 40

    draw.text((70, altura - 65), "Gerado no Radar Económico & Fiscal", fill="#6B7280", font=fonte_rodape)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --- INTERFACE DO PAINEL ---

st.title("📊 Radar Económico & Fiscal — Estúdio de Informação")
data_atual_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
st.caption(f"Última sincronização: {data_atual_str}")

postados_hoje = carregar_postagens_hoje()

col_btn, col_info_post, col_limpar = st.columns([1.4, 2.6, 1.2])
with col_btn:
    if st.button("🔄 Atualizar Dados Agora"):
        buscar_cotacoes.clear()
        buscar_ibovespa.clear()
        buscar_noticias_rss.clear()
        buscar_proposicoes_camara.clear()
        st.rerun()

with col_info_post:
    st.info(f"📌 Postagens registadas hoje: **{len(postados_hoje)}** (avisos automáticos para evitar repetição sem bloquear)")

with col_limpar:
    if postados_hoje and st.button("🧹 Limpar histórico de hoje"):
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

st.divider()

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
    "🎨 Estúdio de Cards por Item",
    "📰 Notícias & Câmara",
    "📈 Gráficos, Conversor & Resumo"
])

imposto_atual_float = calcular_impostometro_estimado()
imposto_atual_fmt = formatar_brl(imposto_atual_float)

noticias_cache = buscar_noticias_rss("Relevantes")
proposicoes_cache = buscar_proposicoes_camara(8)

with aba1:
    st.subheader("🎨 Criar Card Específico para Publicação")
    st.caption("Escolha um indicador ou uma notícia/proposição para gerar o card e marcar o que já foi publicado hoje.")

    formato_estudio = st.radio(
        "Formato do card",
        options=["Feed (1080x1080)", "Histórias / Estado (1080x1920)"],
        horizontal=True,
        key="formato_estudio"
    )
    sufixo_estudio = "stories" if "1080x1920" in formato_estudio else "feed"

    tipo_postagem = st.selectbox(
        "O que queres publicar agora?",
        options=["Indicador", "Notícia (RSS)", "Proposição da Câmara"]
    )

    if tipo_postagem == "Indicador":
        catalogo_indicadores = {
            "Dólar (USD)": ("INDICADOR • CÂMBIO", "Dólar Comercial (USD)", usd_var_str, usd_formatado, fonte_moedas),
            "Euro (EUR)": ("INDICADOR • CÂMBIO", "Euro (EUR)", eur_var_str, eur_formatado, fonte_moedas),
            "Bitcoin (BTC)": ("INDICADOR • CRIPTO", "Bitcoin (BTC)", btc_var_str, btc_formatado, fonte_btc),
            "Ibovespa": ("INDICADOR • BOLSA", "Ibovespa (^BVSP)", ibov_var_str, ibov_formatado, fonte_ibov),
            "Taxa Selic": ("INDICADOR • JUROS", "Taxa Selic (Meta Copom)", f"Ref: {selic_data}", selic_formatada, "Banco Central"),
            "IPCA Mensal": ("INDICADOR • INFLAÇÃO", "IPCA Mensal", f"Ref: {ipca_data}", ipca_formatada, "Banco Central"),
            "Arrecadação Estimada": ("INDICADOR • FISCAL", "Arrecadação Estimada no Ano", "Acumulado desde 1 de janeiro", imposto_atual_fmt, "Estimativa Fiscal"),
        }
        ind_sel = st.selectbox("Escolhe o indicador", options=list(catalogo_indicadores.keys()))
        tag_i, tit_i, sub_i, dest_i, font_i = catalogo_indicadores[ind_sel]

        chave_ind = gerar_chave_item("indicador", ind_sel, dest_i)
        if chave_ind in postados_hoje:
            st.warning(f"⚠️ Já registaste publicação de **{ind_sel}** hoje às **{postados_hoje[chave_ind]['hora']}**. Podes gerar e publicar novamente se quiseres.")

        img_ind = gerar_card_item(tag_i, tit_i, sub_i, dest_i, font_i, data_atual_str, formato=formato_estudio)
        c_dl, c_mk = st.columns([2, 1])
        with c_dl:
            st.download_button(
                label=f"⬇️ Baixar Card de {ind_sel} ({formato_estudio})",
                data=img_ind,
                file_name=f"card_{ind_sel.lower().replace(' ', '_')}_{sufixo_estudio}_{datetime.now().strftime('%H%M')}.png",
                mime="image/png",
                key="dl_card_ind"
            )
        with c_mk:
            if st.button("✅ Marcar como publicado hoje", key="mk_card_ind"):
                registrar_postagem_hoje(chave_ind, f"Indicador: {ind_sel}")
                st.rerun()

    elif tipo_postagem == "Notícia (RSS)":
        if noticias_cache:
            opcoes_news = {f"[{n['fonte']}] {n['titulo']}": n for n in noticias_cache}
            escolha_news = st.selectbox("Escolhe a notícia", options=list(opcoes_news.keys()))
            item_n = opcoes_news[escolha_news]

            chave_n = gerar_chave_item("noticia", item_n["titulo"], item_n["fonte"])
            if chave_n in postados_hoje:
                st.warning(f"⚠️ Esta notícia já foi marcada como publicada hoje às **{postados_hoje[chave_n]['hora']}**. Podes gerar de novo se quiseres repetir.")

            img_n = gerar_card_item(
                categoria_tag="NOTÍCIA • ECONOMIA & POLÍTICA",
                titulo_principal=item_n["titulo"],
                subtitulo_extra=item_n["data_fmt"] or "Atualização do dia",
                destaque_valor="",
                rodape_fonte=item_n["fonte"],
                data_hora=data_atual_str,
                formato=formato_estudio
            )
            c_dl, c_mk = st.columns([2, 1])
            with c_dl:
                st.download_button(
                    label=f"⬇️ Baixar Card da Notícia ({formato_estudio})",
                    data=img_n,
                    file_name=f"card_noticia_{sufixo_estudio}_{datetime.now().strftime('%H%M')}.png",
                    mime="image/png",
                    key="dl_card_news"
                )
            with c_mk:
                if st.button("✅ Marcar notícia como publicada hoje", key="mk_card_news"):
                    registrar_postagem_hoje(chave_n, item_n["titulo"][:80])
                    st.rerun()
        else:
            st.info("Nenhuma notícia disponível de momento.")

    else:
        if proposicoes_cache:
            opcoes_pl = {f"{p['codigo']} — {p['ementa'][:70]}": p for p in proposicoes_cache}
            escolha_pl = st.selectbox("Escolhe a proposição", options=list(opcoes_pl.keys()))
            item_p = opcoes_pl[escolha_pl]

            chave_p = gerar_chave_item("camara", item_p["codigo"], item_p["ementa"])
            if chave_p in postados_hoje:
                st.warning(f"⚠️ A proposição **{item_p['codigo']}** já foi marcada como publicada hoje às **{postados_hoje[chave_p]['hora']}**. Podes gerar novamente se quiseres.")

            img_p = gerar_card_item(
                categoria_tag="CÂMARA DOS DEPUTADOS • PROPOSIÇÃO",
                titulo_principal=item_p["codigo"],
                subtitulo_extra=item_p["ementa"],
                destaque_valor="",
                rodape_fonte="Dados Abertos Câmara",
                data_hora=data_atual_str,
                formato=formato_estudio
            )
            c_dl, c_mk = st.columns([2, 1])
            with c_dl:
                st.download_button(
                    label=f"⬇️ Baixar Card da Proposição ({formato_estudio})",
                    data=img_p,
                    file_name=f"card_camara_{sufixo_estudio}_{datetime.now().strftime('%H%M')}.png",
                    mime="image/png",
                    key="dl_card_pl"
                )
            with c_mk:
                if st.button("✅ Marcar proposição como publicada hoje", key="mk_card_pl"):
                    registrar_postagem_hoje(chave_p, f"{item_p['codigo']} - {item_p['ementa'][:60]}")
                    st.rerun()
        else:
            st.info("Nenhuma proposição da Câmara disponível de momento.")

    if postados_hoje:
        st.divider()
        st.markdown("**Histórico de hoje:**")
        for info in postados_hoje.values():
            st.markdown(f"- `{info['hora']}` — {info['rotulo']}")

with aba2:
    st.subheader("📰 Linha de Notícias Económicas e Políticas")
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
                badge_html = f'<span class="posted-badge">Já publicado hoje às {postados_hoje[chave_item]["hora"]}</span>'

            link_md = f" — [Ler fonte]({item['link']})" if item["link"] else ""
            data_txt = f" • {item['data_fmt']}" if item["data_fmt"] else ""
            st.markdown(
                f'<div class="news-card"><strong>[{item["fonte"]}]</strong> {item["titulo"]}{badge_html}{link_md}<br><span class="source-text">{data_txt.lstrip(" • ")}</span></div>',
                unsafe_allow_html=True
            )
    else:
        st.info("Nenhuma manchete encontrada para esse filtro de momento.")

    st.divider()

    st.subheader("🏛️ Proposições Recentes na Câmara dos Deputados")
    if proposicoes_cache:
        for prop in proposicoes_cache:
            chave_prop = gerar_chave_item("camara", prop["codigo"], prop["ementa"])
            badge_pl = ""
            if chave_prop in postados_hoje:
                badge_pl = f'<span class="posted-badge">Já publicado hoje às {postados_hoje[chave_prop]["hora"]}</span>'

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

    st.subheader("📸 Card Resumo Geral (Todos os Indicadores)")
    formato_resumo = st.radio(
        "Formato do card resumo",
        options=["Feed (1080x1080)", "Histórias / Estado (1080x1920)"],
        horizontal=True,
        key="formato_resumo"
    )
    chave_resumo = gerar_chave_item("resumo", "Card Resumo Geral", data_atual_str[:10])
    if chave_resumo in postados_hoje:
        st.warning(f"⚠️ Já marcaste o **Card Resumo Geral** como publicado hoje às **{postados_hoje[chave_resumo]['hora']}**.")

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
    r_dl, r_mk = st.columns([2, 1])
    with r_dl:
        st.download_button(
            label=f"⬇️ Baixar Card Resumo ({formato_resumo})",
            data=imagem_resumo,
            file_name=f"radar_resumo_{sufixo_resumo}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
            mime="image/png",
            key="dl_resumo"
        )
    with r_mk:
        if st.button("✅ Marcar resumo como publicado hoje", key="mk_resumo"):
            registrar_postagem_hoje(chave_resumo, "Card Resumo Geral")
            st.rerun()

st.divider()
st.markdown(
    '<p class="source-text">Fontes: Banco Central do Brasil (SGS), AwesomeAPI, Frankfurter, CoinGecko, Brapi/Yahoo Finance, Dados Abertos da Câmara e feeds RSS públicos.</p>',
    unsafe_allow_html=True
)