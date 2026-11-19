import streamlit as st
import requests
import time
import io
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title="Painel Econômico e Fiscal - Tempo Real",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
    <style>
    .big-font {
        font-size: 28px !important;
        font-weight: bold;
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
    </style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, text/xml"
}

# --- FUNÇÕES DE BUSCA DE DADOS ---

@st.cache_data(ttl=60)
def buscar_cotacoes():
    """Retorna dicionários com USD, EUR e BTC em BRL."""
    resultado = {"usd": None, "eur": None, "btc": None}

    # 1ª tentativa: AwesomeAPI
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

    # Fallback USD / EUR via Frankfurter
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

    # Fallback BTC via CoinGecko
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

@st.cache_data(ttl=1800)
def buscar_historico_dolar(dias=30):
    try:
        url = f"https://economia.awesomeapi.com.br/json/daily/USD-BRL/{dias}"
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

    try:
        fim = datetime.now().date()
        inicio = fim - timedelta(days=dias)
        url = f"https://api.frankfurter.app/{inicio}..{fim}?from=USD&to=BRL"
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

@st.cache_data(ttl=900)  # Atualiza a cada 15 minutos
def buscar_noticias_rss(apenas_relevantes=True):
    """Lê feeds RSS públicos para montar a linha de notícias e votações."""
    feeds = [
        ("InfoMoney", "https://www.infomoney.com.br/feed/"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"),
    ]
    palavras_chave = [
        "aprova", "aprovado", "votação", "vota", "câmara", "senado",
        "congresso", "projeto", "pl ", "pec ", "imposto", "tributo",
        "fiscal", "selic", "dólar", "inflação", "governo", "ministro"
    ]

    itens = []
    for fonte, url in feeds:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            for item in root.findall(".//item")[:15]:
                titulo = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()

                if not titulo:
                    continue

                texto_lower = titulo.lower()
                if apenas_relevantes and not any(p in texto_lower for p in palavras_chave):
                    continue

                itens.append({
                    "fonte": fonte,
                    "titulo": titulo,
                    "link": link,
                    "data": pub_date[:16] if pub_date else ""
                })
        except Exception:
            continue

    return itens[:12]

def formatar_brl(valor_float):
    return "R$ " + f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_variacao(pct_float):
    sinal = "+" if pct_float > 0 else ""
    pct_br = f"{pct_float:.2f}".replace(".", ",")
    return f"{sinal}{pct_br}% hoje"

def calcular_impostometro_estimado():
    agora = datetime.now()
    inicio_ano = datetime(agora.year, 1, 1)
    segundos_passados = (agora - inicio_ano).total_seconds()
    taxa_por_segundo = 108500.00
    return segundos_passados * taxa_por_segundo

# --- FUNÇÃO GERADORA DE CARD (PILLOW) ---

def gerar_card_imagem(usd_str, usd_var_str, usd_pct_val, btc_str, selic_str, imposto_str, data_hora):
    largura, altura = 1080, 1080
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

    fonte_titulo = carregar_fonte(bold_candidatos, 46)
    fonte_subtitulo = carregar_fonte(regular_candidatos, 26)
    fonte_label = carregar_fonte(regular_candidatos, 30)
    fonte_valor = carregar_fonte(bold_candidatos, 50)
    fonte_imposto = carregar_fonte(bold_candidatos, 44)
    fonte_rodape = carregar_fonte(regular_candidatos, 22)

    draw.text((70, 60), "RADAR ECONÔMICO & FISCAL", fill="#FFFFFF", font=fonte_titulo)
    draw.text((70, 125), f"Atualizado em {data_hora}", fill="#A0AAB5", font=fonte_subtitulo)

    # Bloco 1: Dólar
    cor_usd = "#F87171" if usd_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([70, 195, 1010, 375], radius=20, fill="#1E232F")
    draw.text((110, 220), "DÓLAR COMERCIAL (USD)", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 278), f"{usd_str} ({usd_var_str})", fill=cor_usd, font=fonte_valor)

    # Bloco 2: Bitcoin + Selic
    draw.rounded_rectangle([70, 400, 1010, 640], radius=20, fill="#1E232F")
    draw.text((110, 422), "BITCOIN (BTC)", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 465), btc_str, fill="#F59E0B", font=fonte_valor)
    draw.text((110, 535), "TAXA SELIC (META COPOM)", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 576), selic_str, fill="#60A5FA", font=fonte_valor)

    # Bloco 3: Impostômetro
    draw.rounded_rectangle([70, 665, 1010, 915], radius=20, fill="#1E232F")
    draw.text((110, 695), "ARRECADAÇÃO ESTIMADA NO ANO", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 775), imposto_str, fill="#FBBF24", font=fonte_imposto)

    draw.text((70, 985), "Fontes: BCB, AwesomeAPI, Frankfurter & CoinGecko", fill="#6B7280", font=fonte_rodape)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# --- INTERFACE DO PAINEL ---

st.title("📊 Indicadores Econômicos e Fiscais")
data_atual_str = datetime.now().strftime('%d/%m/%Y às %H:%M:%S')
st.caption(f"Última sincronização: {data_atual_str}")

if st.button("🔄 Atualizar Dados Agora"):
    st.cache_data.clear()
    st.rerun()

st.divider()

dolar, euro, btc = buscar_cotacoes()
selic_valor, selic_data, selic_fallback = buscar_selic()
historico_dolar = buscar_historico_dolar(30)

col1, col2, col3, col4 = st.columns(4)

usd_formatado = "Indisponível"
usd_var_str = "0,00% hoje"
usd_pct_num = 0.0
btc_formatado = "Indisponível"
selic_formatada = "Indisponível"

with col1:
    if dolar:
        valor_usd = float(dolar["bid"])
        usd_pct_num = float(dolar["pctChange"])
        usd_formatado = formatar_brl(valor_usd)
        usd_var_str = formatar_variacao(usd_pct_num)
        st.metric(label="💵 Dólar (USD)", value=usd_formatado, delta=usd_var_str)
    else:
        st.error("Erro ao carregar Dólar")

with col2:
    if euro:
        valor_eur = float(euro["bid"])
        var_eur_num = float(euro["pctChange"])
        st.metric(
            label="💶 Euro (EUR)",
            value=formatar_brl(valor_eur),
            delta=formatar_variacao(var_eur_num)
        )
    else:
        st.error("Erro ao carregar Euro")

with col3:
    if btc:
        valor_btc = float(btc["bid"])
        var_btc_num = float(btc["pctChange"])
        btc_formatado = formatar_brl(valor_btc)
        st.metric(
            label="₿ Bitcoin (BTC)",
            value=btc_formatado,
            delta=formatar_variacao(var_btc_num)
        )
    else:
        st.error("Erro ao carregar BTC")

with col4:
    if selic_valor is not None:
        selic_formatada = f"{selic_valor:.2f}".replace(".", ",") + "% a.a."
        legenda_selic = f"{selic_data} (contingência)" if selic_fallback else f"Ref: {selic_data}"
        st.metric(label="🏦 Taxa Selic", value=selic_formatada, delta=legenda_selic, delta_color="off")
    else:
        st.error("Erro ao carregar Selic")

st.divider()

# Linha de Notícias e Acompanhamento Legislativo/Econômico
st.subheader("📰 Linha de Notícias e Acompanhamento")
filtrar_relevantes = st.toggle("Filtrar temas de economia, impostos e votações", value=True)
noticias = buscar_noticias_rss(apenas_relevantes=filtrar_relevantes)

if noticias:
    for item in noticias:
        link_md = f" — [Ler fonte]({item['link']})" if item["link"] else ""
        st.markdown(
            f'<div class="news-card"><strong>[{item["fonte"]}]</strong> {item["titulo"]}{link_md}<br><span class="source-text">{item["data"]}</span></div>',
            unsafe_allow_html=True
        )
else:
    st.info("Nenhuma notícia encontrada com o filtro atual no momento. Tente desativar o filtro acima.")

st.divider()

# Gráfico Histórico do Dólar
st.subheader("📈 Evolução do Dólar Comercial (Últimos 30 Dias)")
if historico_dolar:
    st.line_chart(historico_dolar, height=280)
else:
    st.info("Histórico temporariamente indisponível.")

st.divider()

# Seção do Contador Fiscal
st.subheader("⏱️ Estimativa de Arrecadação Tributária Acumulada no Ano")
placeholder_imposto = st.empty()

imposto_inicial = calcular_impostometro_estimado()
imposto_inicial_fmt = formatar_brl(imposto_inicial)

imagem_card = gerar_card_imagem(
    usd_str=usd_formatado,
    usd_var_str=usd_var_str,
    usd_pct_val=usd_pct_num,
    btc_str=btc_formatado,
    selic_str=selic_formatada,
    imposto_str=imposto_inicial_fmt,
    data_hora=data_atual_str
)

st.download_button(
    label="📸 Baixar Card Pronto para Redes Sociais (PNG)",
    data=imagem_card,
    file_name=f"radar_economico_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
    mime="image/png"
)

st.divider()
st.markdown(
    '<p class="source-text">Fontes: Banco Central do Brasil, AwesomeAPI, Frankfurter, CoinGecko e feeds RSS públicos.</p>',
    unsafe_allow_html=True
)

for _ in range(60):
    valor_imposto = calcular_impostometro_estimado()
    valor_formatado = formatar_brl(valor_imposto)
    
    with placeholder_imposto.container():
        st.markdown(f'<p class="big-font">{valor_formatado}</p>', unsafe_allow_html=True)
        st.caption("Projeção contínua acumulada desde 1º de janeiro (Federal, Estadual e Municipal).")
    
    time.sleep(1)