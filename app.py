import os
import json
import gzip
import brotli
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request, jsonify
from pymongo import MongoClient
from pymongo.server_api import ServerApi

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from seleniumwire import webdriver as seleniumwire_webdriver
from webdriver_manager.chrome import ChromeDriverManager

# --- Configuração de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Conexão Segura com MongoDB via Variável de Ambiente ---
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    logger.critical("A variável de ambiente MONGO_URI não foi definida. A aplicação não pode iniciar.")
    raise ValueError("A variável de ambiente MONGO_URI não foi definida.")

try:
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    client.admin.command('ping')
    logger.info("Conexão com MongoDB estabelecida com sucesso!")
except Exception as e:
    logger.critical(f"Falha ao conectar com o MongoDB: {e}")
    raise

app = Flask(__name__)
db = client['pharmasearch']
medicamentos_collection = db['medicamentos']
cache_memoria = {}

# --- Função Otimizada para Criar Driver do Chrome (COM DIAGNÓSTICO) ---
def criar_driver_chrome(use_selenium_wire=False):
    logger.info("Iniciando a criação do driver do Chrome.")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")

    # Lógica para funcionar tanto no Render quanto localmente
    if os.environ.get("RENDER"):
        logger.info("Ambiente Render detectado.")
        
        # LOGS DE DIAGNÓSTICO CRUCIAIS
        chrome_bin = os.environ.get("GOOGLE_CHROME_BIN")
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        
        logger.info(f"Valor lido de GOOGLE_CHROME_BIN: {chrome_bin}")
        logger.info(f"Valor lido de CHROMEDRIVER_PATH: {chromedriver_path}")

        if not chrome_bin or not chromedriver_path:
            logger.critical("ERRO: Variáveis de ambiente para o Chrome não encontradas no Render!")
            raise RuntimeError("Variáveis de ambiente do Chrome (GOOGLE_CHROME_BIN, CHROMEDRIVER_PATH) não configuradas no ambiente Render.")

        chrome_options.binary_location = chrome_bin
        service = Service(executable_path=chromedriver_path)
        logger.info("Configurando Service e Options para o ambiente Render.")
        
    else:
        logger.info("Ambiente local detectado. Usando webdriver-manager.")
        service = Service(ChromeDriverManager().install())

    logger.info("Instanciando o driver...")
    try:
        if use_selenium_wire:
            driver = seleniumwire_webdriver.Chrome(service=service, options=chrome_options)
        else:
            driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Driver criado com sucesso.")
        return driver
    except Exception as e:
        logger.critical(f"Falha final ao instanciar o webdriver do Chrome: {e}", exc_info=True)
        raise

# --- Funções de Scraping (sem alterações, já estavam robustas) ---
def buscar_maxxi(medicamento):
    driver = criar_driver_chrome()
    # ... (código da função buscar_maxxi como na resposta anterior)
    resultados = []
    url = f"https://www.maxxieconomica.com/busca-produtos?busca={medicamento}"
    logger.info(f"Buscando na Maxxi: {url}")
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        product_containers = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".prodMaxxi__item"))
        )

        for container in product_containers:
            try:
                nome = container.find_element(By.CSS_SELECTOR, ".prodMaxxi__text").text.strip()
                preco_str = container.find_element(By.CSS_SELECTOR, ".priceByMaxxi").text.strip()
                
                if not preco_str: continue

                preco = float(preco_str.replace('R$', '').replace('.', '').replace(',', '.').strip())
                imagem = container.find_element(By.TAG_NAME, "img").get_attribute("src")
                link = container.find_element(By.TAG_NAME, "a").get_attribute("href")

                resultados.append({
                    "nome": nome, "preco": preco, "imagem": imagem,
                    "link": link, "farmacia": "Maxxi"
                })
            except Exception:
                logger.warning(f"Falha ao processar um item da Maxxi.", exc_info=False)
                continue
        return resultados
    except Exception as e:
        logger.error(f"Erro geral ao buscar na Maxxi: {e}", exc_info=True)
        return []
    finally:
        driver.quit()

def buscar_sao_joao(medicamento):
    driver = criar_driver_chrome()
    # ... (código da função buscar_sao_joao como na resposta anterior)
    resultados = []
    url = f"https://www.saojoaofarmacias.com.br/{medicamento.replace(' ', '%20')}?_q={medicamento.replace(' ', '%20')}&map=ft"
    logger.info(f"Buscando na São João: {url}")
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        scripts = wait.until(
            EC.presence_of_all_elements_located((By.XPATH, "//script[@type='application/ld+json']"))
        )
        
        for script in scripts:
            json_data = json.loads(script.get_attribute('innerHTML'))
            if isinstance(json_data, dict) and json_data.get('@type') == 'ItemList':
                for item in json_data.get('itemListElement', []):
                    produto = item.get('item', {})
                    offers = produto.get('offers', {})
                    
                    nome = produto.get('name')
                    preco = offers.get('lowPrice')
                    imagem = produto.get('image')
                    link = produto.get('url')

                    if not all([nome, preco, link]): continue

                    resultados.append({
                        "nome": nome, "preco": float(preco), "imagem": imagem,
                        "link": link, "farmacia": "São João"
                    })
        return resultados
    except Exception as e:
        logger.error(f"Erro geral ao buscar na São João: {e}", exc_info=True)
        return []
    finally:
        driver.quit()

def buscar_panvel(medicamento):
    driver = criar_driver_chrome(use_selenium_wire=True)
    # ... (código da função buscar_panvel como na resposta anterior)
    url = f"https://www.panvel.com/panvel/buscarProduto.do?termoPesquisa={medicamento}"
    logger.info(f"Buscando na Panvel: {url}")
    try:
        driver.get(url)
        request = driver.wait_for_request('/api/v3/search', timeout=30)
        
        if not (request.response and request.response.body):
            logger.error("API de busca da Panvel não retornou corpo de resposta.")
            return []

        encoding = request.response.headers.get('Content-Encoding', 'identity')
        body = request.response.body
        decompressed_body = brotli.decompress(body) if encoding == 'br' else gzip.decompress(body) if encoding == 'gzip' else body
        data = json.loads(decompressed_body.decode('utf-8'))
        
        resultados = []
        for item in data.get("items", []):
            price_info = item.get("price", {})
            price = price_info.get("pack", {}).get("dealPrice") or price_info.get("dealPrice") or price_info.get("originalPrice")
            if price is None: continue

            resultados.append({
                "nome": item.get("name", "N/A").strip(), "preco": float(price),
                "imagem": item.get("image"), "link": f"https://www.panvel.com{item.get('uri')}",
                "farmacia": "Panvel"
            })
        return resultados
    except Exception as e:
        logger.error(f"Erro geral ao buscar na Panvel: {e}", exc_info=True)
        return []
    finally:
        driver.quit()

# --- Rota Principal da API (sem alterações) ---
@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    # ... (código da rota como na resposta anterior)
    medicamento = request.args.get('medicamento')
    if not medicamento:
        return jsonify({'erro': 'O parâmetro "medicamento" é obrigatório.'}), 400

    medicamento_key = medicamento.lower().strip()

    if medicamento_key in cache_memoria:
        if (datetime.utcnow() - cache_memoria[medicamento_key]['timestamp']) < timedelta(hours=1):
            logger.info(f"Retornando dados do CACHE DE MEMÓRIA para '{medicamento_key}'")
            return jsonify(cache_memoria[medicamento_key]['dados'])

    cache_ttl = timedelta(hours=4)
    documento_cache = medicamentos_collection.find_one({'_id': medicamento_key})
    if documento_cache and (datetime.utcnow() - documento_cache['timestamp']) < cache_ttl:
        logger.info(f"Retornando dados do CACHE DO BANCO DE DADOS para '{medicamento_key}'")
        response_data = {'medicamentos': documento_cache['dados'], 'fonte': 'cache_db'}
        cache_memoria[medicamento_key] = {'dados': response_data, 'timestamp': datetime.utcnow()}
        return jsonify(response_data)

    logger.info(f"Nenhum cache válido encontrado. Iniciando scraping para '{medicamento_key}'...")
    
    todos_os_resultados = []
    farmacias_a_buscar = {
        "Maxxi": buscar_maxxi,
        "São João": buscar_sao_joao,
        "Panvel": buscar_panvel
    }

    with ThreadPoolExecutor(max_workers=len(farmacias_a_buscar)) as executor:
        future_to_farmacia = {executor.submit(func, medicamento_key): nome for nome, func in farmacias_a_buscar.items()}
        for future in as_completed(future_to_farmacia):
            farmacia_nome = future_to_farmacia[future]
            try:
                resultados_farmacia = future.result()
                if resultados_farmacia:
                    todos_os_resultados.extend(resultados_farmacia)
                    logger.info(f"Busca na {farmacia_nome} concluída com {len(resultados_farmacia)} resultados.")
            except Exception as exc:
                logger.error(f"Busca na {farmacia_nome} gerou uma exceção: {exc}", exc_info=True)

    if not todos_os_resultados:
        return jsonify({'erro': 'Nenhum medicamento encontrado com este nome.'}), 404

    todos_ordenados = sorted(todos_os_resultados, key=lambda x: x['preco'])
    response_data = {
        'medicamentos': todos_ordenados[:15],
        'total_encontrado': len(todos_ordenados),
        'farmacias_consultadas': list(farmacias_a_buscar.keys()),
        'fonte': 'live_scrape'
    }

    medicamentos_collection.update_one(
        {'_id': medicamento_key},
        {'$set': {'dados': todos_ordenados[:15], 'timestamp': datetime.utcnow()}},
        upsert=True
    )
    cache_memoria[medicamento_key] = {'dados': response_data, 'timestamp': datetime.utcnow()}
    logger.info(f"Resultados para '{medicamento_key}' salvos no cache.")

    return jsonify(response_data)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)