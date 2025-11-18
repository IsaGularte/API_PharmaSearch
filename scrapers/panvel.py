from seleniumwire import webdriver as seleniumwire_webdriver
from selenium.webdriver.chrome.options import Options
import json
import gzip
import brotli
import logging

def buscar_panvel(medicamento):
    search_url = f"https://www.panvel.com/panvel/buscarProduto.do?termoPesquisa={medicamento}"
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = seleniumwire_webdriver.Chrome(options=chrome_options)
    try:
        driver.get(search_url)
        request = driver.wait_for_request('/api/v3/search', timeout=30)
        if not (request.response and request.response.body):
            return []
        body = request.response.body
        if request.response.headers.get('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)
        elif request.response.headers.get('Content-Encoding') == 'br':
            body = brotli.decompress(body)
        data = json.loads(body.decode('utf-8'))
        items = data.get("items", [])
        products_list = []
        for item in items:
            price_info = item.get("price", {})
            if not price_info: continue
            price = price_info.get("dealPrice") or price_info.get("originalPrice")
            if price is None: continue
            products_list.append({"nome": item.get("name", "").strip(), "preco": float(price), "imagem": item.get("image"), "farmacia": "Panvel"})
        return products_list
    except Exception as e:
        logging.error(f"Erro ao acessar Panvel: {e}")
        return []
    finally:
        if driver:
            driver.quit()