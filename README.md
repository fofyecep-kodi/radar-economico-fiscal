# Radar Econômico e Fiscal

Painel web gratuito desenvolvido com **Streamlit**, **Requests** e **Pillow** para acompanhar indicadores econômicos, estimativa de arrecadação anual, notícias/proposições legislativas e exportação de cards prontos para redes sociais.

## Indicadores e Fontes
- **Dólar (USD), Euro (EUR) e Bitcoin (BTC):** AwesomeAPI, Frankfurter API e CoinGecko.
- **Ibovespa (^BVSP):** Brapi / Yahoo Finance.
- **Taxa Selic (Série 432) e IPCA Mensal (Série 433):** Banco Central do Brasil (SGS).
- **Notícias e Proposições:** Feeds RSS públicos e API de Dados Abertos da Câmara dos Deputados.

## Execução Local
```bash
pip install -r requirements.txt
streamlit run app.py