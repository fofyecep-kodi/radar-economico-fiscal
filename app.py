import streamlit as st
import streamlit.components.v1 as components
import requests
import io
import os
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="Radar Econômico e Fiscal - Tempo Real",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
    <style>
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
    </style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml"
}

TAXA_IMPOSTO_POR_SEGUNDO = 108500.00

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

@st.cache_data(ttl=60)
def buscar_cotacoes():
    resultado = {"usd": None, "eur": None, "btc": None}

    try:
        url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,BTC-BRL"
        response = requests.get(url, headers=HEADERS, timeout=8)
        response.raise_for_status()
        dados = response.json()
        if "USDBRL" in dados:
            resultado["usd"] = dados["USDBRL"]
        if "EURBRL" in dados:
            resultado["eur"] = dados["EURBRL"]
        if "BTCBRL" in dados:
            resultado["btc"] = dados["BTCBRL"]
    except Exception:
        pass

    if not resultado["usd"] or not resultado["eur"]:
        try:
            hoje = datetime.now().date()
            inicio = hoje - timedelta(days=5)
            if not resultado["usd"]:
                r_usd = requests.get(
                    f"https://api.frankfurter.app/{inicio}..{hoje}?from=USD&to=BRL",
                    headers=HEADERS, timeout=8
                ).json()
                rates_usd = sorted(r_usd.get("rates", {}).items())
                if len(rates_usd) >= 1:
                    u = float(rates_usd[-1][1]["BRL"])
                    p = float(rates_usd[-2][1]["BRL"]) if len(rates_usd) >= 2 else u
                    pct = ((u - p) / p * 100) if p else 0.0
                    resultado["usd"] = {"bid": str(u), "pctChange": str(round(pct, 2))}

            if not resultado["eur"]:
                r_eur = requests.get(
                    f"https://api.frankfurter.app/{inicio}..{hoje}?from=EUR&to=BRL",
                    headers=HEADERS, timeout=8
                ).json()
                rates_eur = sorted(r_eur.get("rates", {}).items())
                if len(rates_eur) >= 1:
                    u = float(rates_eur[-1][1]["BRL"])
                    p = float(rates_eur[-2][1]["BRL"]) if len(rates_eur) >= 2 else u
                    pct = ((u - p) / p * 100) if p else 0.0
                    resultado["eur"] = {"bid": str(u), "pctChange": str(round(pct, 2))}
        except Exception:
            pass

    if not resultado["btc"]:
        try:
            url_btc = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl&include_24hr_change=true"
            r_btc = requests.get(url_btc, headers=HEADERS, timeout=8).json()
            if "bitcoin" in r_btc:
                preco_brl = float(r_btc["bitcoin"]["brl"])
                var_24h = float(r_btc["bitcoin"].get("brl_24h_change", 0.0))
                resultado["btc"] = {"bid": str(preco_brl), "pctChange": str(round(var_24h, 2))}
        except Exception:
            pass

    return resultado["usd"], resultado["eur"], resultado["btc"]

@st.cache_data(ttl=120)
def buscar_ibovespa():
    try:
        url = "https://brapi.dev/api/quote/%5EBVSP"
        response = requests.get(url, headers=HEADERS, timeout=8)
        response.raise_for_status()
        dados = response.json()
        results = dados.get("results", [])
        if results:
            item = results[0]
            pontos = float(item.get("regularMarketPrice", 0.0))
            pct = float(item.get("regularMarketChangePercent", 0.0))
            if pontos > 0:
                return pontos, pct, False
    except Exception:
        pass

    try:
        url_yf = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP?interval=1d&range=5d"
        response = requests.get(url_yf, headers=HEADERS, timeout=8)
        response.raise_for_status()
        dados = response.json()
        result = dados.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            pontos = float(meta.get("regularMarketPrice", 0.0))
            fechamento_ant = float(meta.get("chartPreviousClose", 0.0))
            if pontos > 0:
                pct = ((pontos - fechamento_ant) / fechamento_ant * 100) if fechamento_ant else 0.0
                return pontos, pct, False
    except Exception:
        pass

    return None, None, True

@st.cache_data(ttl=3600)
def buscar_selic():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        dados = response.json()
        return float(dados[0]["valor"]), dados[0]["data"], False
    except Exception:
        return 13.75, "Ref. estimada", True

@st.cache_data(ttl=21600)
def buscar_ipca_mensal():
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        dados = response.json()
        return float(dados[0]["valor"]), dados[0]["data"], False
    except Exception:
        return 0.44, "Ref. estimada", True

@st.cache_data(ttl=1800)
def buscar_historico_ativo(ativo="USD-BRL", dias=30):
    if ativo in ("USD-BRL", "EUR-BRL", "BTC-BRL"):
        try:
            url = f"https://economia.awesomeapi.com.br/json/daily/{ativo}/{dias}"
            response = requests.get(url, headers=HEADERS, timeout=8)
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
                response = requests.get(url, headers=HEADERS, timeout=8)
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
            response = requests.get(url_yf, headers=HEADERS, timeout=8)
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

@st.cache_data(ttl=900)
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
            resp = requests.get(url, headers=HEADERS, timeout=8)
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

@st.cache_data(ttl=1800)
def buscar_proposicoes_camara(limite=8):
    """Consulta proposições recentes na API de Dados Abertos da Câmara."""
    try:
        data_inicio = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        url = (
            "https://dadosabertos.camara.leg.br/api/v2/proposicoes"
            f"?dataApresentacaoInicio={data_inicio}&itens={limite}&ordem=DESC&ordenarPor=id"
        )
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=8)
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

# --- FUNÇÃO GERADORA DE CARD (PILLOW) ---

def gerar_card_imagem(
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

    base_dir = os.path.dirname(os.path.abspath(__file__))

    def carregar_fonte(nomes_candidatos, tamanho):
        for nome in nomes_candidatos:
            caminho = os.path.join(base_dir, nome)
            try:
                return ImageFont.truetype(caminho, tamanho)
            except Exception:
                continue
        return ImageFont.load_default()

    bold_candidatos = ["ARIALBD.TTF", "ARIBLK.TTF", "ARIAL.TTF", "arialbd.ttf", "arial.ttf"]
    regular_candidatos = ["ARIAL.TTF", "ARIALBD.TTF", "arial.ttf", "arialbd.ttf"]

    fonte_titulo = carregar_fonte(bold_candidatos, 44 if eh_stories else 42)
    fonte_subtitulo = carregar_fonte(regular_candidatos, 25 if eh_stories else 23)
    fonte_label = carregar_fonte(regular_candidatos, 25 if eh_stories else 24)
    fonte_valor = carregar_fonte(bold_candidatos, 40 if eh_stories else 37)
    fonte_var = carregar_fonte(regular_candidatos, 23 if eh_stories else 21)
    fonte_imposto = carregar_fonte(bold_candidatos, 44 if eh_stories else 41)
    fonte_rodape = carregar_fonte(regular_candidatos, 21 if eh_stories else 19)

    offset_y = 95 if eh_stories else 0
    espaco_linha = 235 if eh_stories else 188

    draw.text((65, 45 + offset_y), "RADAR ECONÔMICO & FISCAL", fill="#FFFFFF", font=fonte_titulo)
    draw.text((65, 98 + offset_y), f"Atualizado em {data_hora}", fill="#A0AAB5", font=fonte_subtitulo)

    y1 = 152 + offset_y
    h_box = 185 if eh_stories else 166

    # Linha 1: Dólar e Euro
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

    # Linha 2: Bitcoin e Ibovespa
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

    # Linha 3: Selic e IPCA
    y3 = y2 + espaco_linha
    h_macro = 158 if eh_stories else 142
    draw.rounded_rectangle([65, y3, 525, y3 + h_macro], radius=18, fill="#1E232F")
    draw.text((90, y3 + 16), "TAXA SELIC (META)", fill="#A0AAB5", font=fonte_label)
    draw.text((90, y3 + 58), selic_str, fill="#38BDF8", font=fonte_valor)

    draw.rounded_rectangle([555, y3, 1015, y3 + h_macro], radius=18, fill="#1E232F")
    draw.text((580, y3 + 16), "IPCA (ÚLTIMO MÊS)", fill="#A0AAB5", font=fonte_label)
    draw.text((580, y3 + 58), ipca_str, fill="#F472B6", font=fonte_valor)

    # Linha 4: Impostômetro
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

# --- INTERFACE DO PAINEL ---

st.title("📊 Radar Econômico e Fiscal")
data_atual_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
st.caption(f"Última sincronização: {data_atual_str}")

col_btn, col_info = st.columns([1, 4])
with col_btn:
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()

dolar, euro, btc = buscar_cotacoes()
selic_valor, selic_data, selic_fallback = buscar_selic()
ipca_valor, ipca_data, ipca_fallback = buscar_ipca_mensal()
ibov_pontos, ibov_pct, ibov_indisponivel = buscar_ibovespa()

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

ipca_formatado = "Indisponível"
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
    else:
        st.error("Erro ao carregar Dólar")

with col2:
    if euro:
        valor_eur_float = float(euro["bid"])
        eur_pct_num = float(euro["pctChange"])
        eur_formatado = formatar_brl(valor_eur_float)
        eur_var_str = formatar_variacao(eur_pct_num)
        st.metric(label="💶 Euro (EUR)", value=eur_formatado, delta=eur_var_str)
    else:
        st.error("Erro ao carregar Euro")

with col3:
    if btc:
        valor_btc_float = float(btc["bid"])
        btc_pct_num = float(btc["pctChange"])
        btc_formatado = formatar_brl(valor_btc_float)
        btc_var_str = formatar_variacao(btc_pct_num)
        st.metric(label="₿ Bitcoin (BTC)", value=btc_formatado, delta=btc_var_str)
    else:
        st.error("Erro ao carregar BTC")

with col4:
    if not ibov_indisponivel and ibov_pontos is not None:
        ibov_pct_num = ibov_pct or 0.0
        ibov_formatado = formatar_pontos(ibov_pontos)
        ibov_var_str = formatar_variacao(ibov_pct_num)
        st.metric(label="📉 Ibovespa", value=ibov_formatado, delta=ibov_var_str)
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
        ipca_formatado = f"{sinal_ipca}{ipca_valor:.2f}".replace(".", ",") + "% a.m."
        legenda_ipca = f"{ipca_data} (contingência)" if ipca_fallback else f"Ref: {ipca_data}"
        st.metric(label="🏷️ Inflação / IPCA Mensal", value=ipca_formatado, delta=legenda_ipca, delta_color="off")
    else:
        st.error("Erro ao carregar IPCA")

st.divider()

aba1, aba2 = st.tabs(["📈 Gráficos, Conversor & Card", "📰 Notícias & Câmara"])

with aba1:
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
    renderizar_contador_js(calcular_impostometro_estimado())

    st.divider()

    st.subheader("📸 Gerador de Card para Redes Sociais")
    formato_card = st.radio(
        "Formato da imagem",
        options=["Feed (1080x1080)", "Stories / Status (1080x1920)"],
        horizontal=True
    )

    imposto_fmt_card = formatar_brl(calcular_impostometro_estimado())
    imagem_card = gerar_card_imagem(
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
        ipca_str=ipca_formatado,
        selic_str=selic_formatada,
        imposto_str=imposto_fmt_card,
        data_hora=data_atual_str,
        formato=formato_card
    )

    sufixo_arq = "stories" if "1080x1920" in formato_card else "feed"
    st.download_button(
        label=f"⬇️ Baixar Card ({formato_card}) em PNG",
        data=imagem_card,
        file_name=f"radar_economico_{sufixo_arq}_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
        mime="image/png"
    )

with aba2:
    st.subheader("📰 Linha de Notícias Econômicas e Políticas")
    categoria_escolhida = st.selectbox(
        "Filtrar manchetes por tema",
        options=["Relevantes", "Votações / Congresso", "Impostos & Fiscal", "Mercado & Juros", "Todas"]
    )
    noticias = buscar_noticias_rss(categoria=categoria_escolhida)

    if noticias:
        for item in noticias:
            link_md = f" — [Ler fonte]({item['link']})" if item["link"] else ""
            data_txt = f" • {item['data_fmt']}" if item["data_fmt"] else ""
            st.markdown(
                f'<div class="news-card"><strong>[{item["fonte"]}]</strong> {item["titulo"]}{link_md}<br><span class="source-text">{data_txt.lstrip(" • ")}</span></div>',
                unsafe_allow_html=True
            )
    else:
        st.info("Nenhuma manchete encontrada para esse filtro no momento.")

    st.divider()

    st.subheader("🏛️ Proposições Recentes na Câmara dos Deputados")
    proposicoes = buscar_proposicoes_camara(limite=8)
    if proposicoes:
        for prop in proposicoes:
            url_camara = f"https://www.camara.leg.br/proposicoesWeb/fichadetailid?idProposicao={prop['id']}" if prop["id"] else ""
            link_prop = f" — [Ficha na Câmara]({url_camara})" if url_camara else ""
            st.markdown(
                f'<div class="pl-card"><strong>{prop["codigo"]}</strong>{link_prop}<br><span>{prop["ementa"]}</span></div>',
                unsafe_allow_html=True
            )
    else:
        st.info("Consulta de proposições da Câmara temporariamente indisponível.")

st.divider()
st.markdown(
    '<p class="source-text">Fontes: Banco Central do Brasil (SGS), AwesomeAPI, Frankfurter, CoinGecko, Brapi/Yahoo Finance, Dados Abertos da Câmara e feeds RSS públicos.</p>',
    unsafe_allow_html=True
)