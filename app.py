import streamlit as st
import requests
import time
import io
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
    </style>
""", unsafe_allow_html=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# --- FUNÇÕES DE BUSCA DE DADOS ---

@st.cache_data(ttl=60)
def buscar_moedas():
    # 1ª tentativa: AwesomeAPI
    try:
        url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL"
        response = requests.get(url, headers=HEADERS, timeout=8)
        response.raise_for_status()
        dados = response.json()
        if "USDBRL" in dados and "EURBRL" in dados:
            return dados["USDBRL"], dados["EURBRL"]
    except Exception:
        pass

    # 2ª tentativa (fallback para servidores em nuvem): Frankfurter API
    try:
        hoje = datetime.now().date()
        ontem = hoje - timedelta(days=5)
        url = f"https://api.frankfurter.app/{ontem}..{hoje}?from=USD&to=BRL"
        r_usd = requests.get(url, headers=HEADERS, timeout=8).json()

        url_eur = f"https://api.frankfurter.app/{ontem}..{hoje}?from=EUR&to=BRL"
        r_eur = requests.get(url_eur, headers=HEADERS, timeout=8).json()

        rates_usd = sorted(r_usd.get("rates", {}).items())
        rates_eur = sorted(r_eur.get("rates", {}).items())

        usd_dict = None
        eur_dict = None

        if len(rates_usd) >= 1:
            ultimo_val = float(rates_usd[-1][1]["BRL"])
            penultimo_val = float(rates_usd[-2][1]["BRL"]) if len(rates_usd) >= 2 else ultimo_val
            pct = ((ultimo_val - penultimo_val) / penultimo_val * 100) if penultimo_val else 0.0
            usd_dict = {"bid": str(ultimo_val), "pctChange": str(round(pct, 2))}

        if len(rates_eur) >= 1:
            ultimo_val = float(rates_eur[-1][1]["BRL"])
            penultimo_val = float(rates_eur[-2][1]["BRL"]) if len(rates_eur) >= 2 else ultimo_val
            pct = ((ultimo_val - penultimo_val) / penultimo_val * 100) if penultimo_val else 0.0
            eur_dict = {"bid": str(ultimo_val), "pctChange": str(round(pct, 2))}

        return usd_dict, eur_dict
    except Exception:
        return None, None

@st.cache_data(ttl=1800)
def buscar_historico_dolar(dias=30):
    # 1ª tentativa: AwesomeAPI histórico
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

    # 2ª tentativa (fallback): Frankfurter série temporal
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

def gerar_card_imagem(usd_str, usd_var_str, usd_pct_val, selic_str, imposto_str, data_hora):
    largura, altura = 1080, 1080
    img = Image.new("RGB", (largura, altura), color="#0E1117")
    draw = ImageDraw.Draw(img)

    caminhos_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arialbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    caminhos_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]

    def carregar_fonte(caminhos, tamanho):
        for caminho in caminhos:
            try:
                return ImageFont.truetype(caminho, tamanho)
            except IOError:
                continue
        return ImageFont.load_default()

    fonte_titulo = carregar_fonte(caminhos_bold, 48)
    fonte_subtitulo = carregar_fonte(caminhos_regular, 28)
    fonte_label = carregar_fonte(caminhos_regular, 32)
    fonte_valor = carregar_fonte(caminhos_bold, 54)
    fonte_imposto = carregar_fonte(caminhos_bold, 48)
    fonte_rodape = carregar_fonte(caminhos_regular, 22)

    draw.text((70, 70), "RADAR ECONÔMICO & FISCAL", fill="#FFFFFF", font=fonte_titulo)
    draw.text((70, 140), f"Atualizado em {data_hora}", fill="#A0AAB5", font=fonte_subtitulo)

    cor_usd = "#F87171" if usd_pct_val > 0 else "#4ADE80"
    draw.rounded_rectangle([70, 230, 1010, 430], radius=20, fill="#1E232F")
    draw.text((110, 260), "DÓLAR COMERCIAL (USD)", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 325), f"{usd_str} ({usd_var_str})", fill=cor_usd, font=fonte_valor)

    draw.rounded_rectangle([70, 470, 1010, 670], radius=20, fill="#1E232F")
    draw.text((110, 500), "TAXA SELIC (META COPOM)", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 565), selic_str, fill="#60A5FA", font=fonte_valor)

    draw.rounded_rectangle([70, 710, 1010, 930], radius=20, fill="#1E232F")
    draw.text((110, 740), "ARRECADAÇÃO ESTIMADA NO ANO", fill="#A0AAB5", font=fonte_label)
    draw.text((110, 810), imposto_str, fill="#FBBF24", font=fonte_imposto)

    draw.text((70, 990), "Fontes: Banco Central do Brasil, AwesomeAPI & Frankfurter", fill="#6B7280", font=fonte_rodape)

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

dolar, euro = buscar_moedas()
selic_valor, selic_data, selic_fallback = buscar_selic()
historico_dolar = buscar_historico_dolar(30)

col1, col2, col3 = st.columns(3)

usd_formatado = "Indisponível"
usd_var_str = "0,00% hoje"
usd_pct_num = 0.0
selic_formatada = "Indisponível"

with col1:
    if dolar:
        valor_usd = float(dolar["bid"])
        usd_pct_num = float(dolar["pctChange"])
        usd_formatado = f"R$ {valor_usd:.2f}".replace(".", ",")
        usd_var_str = formatar_variacao(usd_pct_num)
        st.metric(label="💵 Dólar Comercial (USD)", value=usd_formatado, delta=usd_var_str)
    else:
        st.error("Erro ao carregar Dólar")

with col2:
    if euro:
        valor_eur = float(euro["bid"])
        var_eur_num = float(euro["pctChange"])
        st.metric(
            label="💶 Euro (EUR)",
            value=f"R$ {valor_eur:.2f}".replace(".", ","),
            delta=formatar_variacao(var_eur_num)
        )
    else:
        st.error("Erro ao carregar Euro")

with col3:
    if selic_valor is not None:
        selic_formatada = f"{selic_valor:.2f}".replace(".", ",") + "% a.a."
        legenda_selic = f"{selic_data} (contingência)" if selic_fallback else f"Ref: {selic_data}"
        st.metric(label="🏦 Taxa Selic (Meta Copom)", value=selic_formatada, delta=legenda_selic, delta_color="off")
    else:
        st.error("Erro ao carregar Selic")

st.divider()

st.subheader("📈 Evolução do Dólar Comercial (Últimos 30 Dias)")
if historico_dolar:
    st.line_chart(historico_dolar, height=280)
else:
    st.info("Histórico temporariamente indisponível.")

st.divider()

st.subheader("⏱️ Estimativa de Arrecadação Tributária Acumulada no Ano")
placeholder_imposto = st.empty()

imposto_inicial = calcular_impostometro_estimado()
imposto_inicial_fmt = f"R$ {imposto_inicial:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

imagem_card = gerar_card_imagem(
    usd_str=usd_formatado,
    usd_var_str=usd_var_str,
    usd_pct_val=usd_pct_num,
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
    '<p class="source-text">Fontes: Banco Central do Brasil (SGS), AwesomeAPI, Frankfurter e projeção estatística baseada na carga tributária nacional.</p>',
    unsafe_allow_html=True
)

for _ in range(60):
    valor_imposto = calcular_impostometro_estimado()
    valor_formatado = f"R$ {valor_imposto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    with placeholder_imposto.container():
        st.markdown(f'<p class="big-font">{valor_formatado}</p>', unsafe_allow_html=True)
        st.caption("Projeção contínua acumulada desde 1º de janeiro (Federal, Estadual e Municipal).")
    
    time.sleep(1)
