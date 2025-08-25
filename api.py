from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from seleniumwire import webdriver as seleniumwire_webdriver
import json
import gzip
import brotli
import logging

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Conexão com MongoDB
uri = "mongodb+srv://admin:ilovepharmasearch@pharmasearch-cluster.facv1dr.mongodb.net/?retryWrites=true&w=majority&appName=pharmasearch-cluster"
client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

app = Flask(__name__)
cache_resultados = {}  # Cache simples em memória

def buscar_maxxi(medicamento):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=chrome_options)
    try:
        url = f"https://www.maxxieconomica.com/busca-produtos?busca={medicamento}"
        print(f"[DEBUG] Acessando URL Maxxi: {url}")
        driver.get(url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".prodMaxxi__text"))
            )
        except Exception as e:
            print(f"[DEBUG] Elemento .prodMaxxi__text não encontrado: {e}")
        nomes = driver.find_elements(By.CSS_SELECTOR, ".prodMaxxi__text")
        precos = driver.find_elements(By.CSS_SELECTOR, ".priceByMaxxi")
        print(f"[DEBUG] Nomes encontrados: {len(nomes)}, Preços: {len(precos)}")
        resultados = []
        for i in range(min(len(nomes), len(precos))):
            nome = nomes[i].text.strip()
            preco = precos[i].text.strip().replace('R$', '').replace(',', '.')
            imagem = None
            try:
                bloco_produto = nomes[i].find_element(By.XPATH, "ancestor::div[contains(@class, 'prodMaxxi__item')]")
                img_tag = bloco_produto.find_element(By.CSS_SELECTOR, "img")
                imagem = img_tag.get_attribute("src")
            except Exception as e:
                print(f"[DEBUG] Caminho principal falhou ao buscar imagem do produto {i}: {e}")
                try:
                    bloco_div = nomes[i].find_element(By.XPATH, "ancestor::div[1]")
                    img_tag = bloco_div.find_element(By.CSS_SELECTOR, "img")
                    imagem = img_tag.get_attribute("src")
                except Exception as e2:
                    print(f"[DEBUG] Fallback 1 falhou ao buscar imagem do produto {i}: {e2}")
                    try:
                        img_tag = nomes[i].find_element(By.XPATH, "preceding::img[1]")
                        imagem = img_tag.get_attribute("src")
                    except Exception as e3:
                        print(f"[DEBUG] Fallback 2 falhou ao buscar imagem do produto {i}: {e3}")
                        imagem = None
            resultados.append({
                "nome": nome,
                "preco": float(preco),
                "imagem": imagem,
                "farmacia": "Maxxi"
            })
        return resultados
    except Exception as e:
        print(f"Erro ao acessar Maxxi: {e}")
        return []
    finally:
        driver.quit()

def buscar_sao_joao(medicamento):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    try:
        url = f"https://www.saojoaofarmacias.com.br/{medicamento.replace(' ', '%20')}?_q={medicamento.replace(' ', '%20')}&map=ft"
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, 'script')))
        scripts = driver.find_elements(By.TAG_NAME, 'script')
        resultados = []
        for script in scripts:
            try:
                if 'application/ld+json' in script.get_attribute('type'):
                    json_data = json.loads(script.get_attribute('innerHTML'))
                    if isinstance(json_data, dict) and json_data.get('@type') == 'ItemList':
                        for item in json_data.get('itemListElement', []):
                            produto = item.get('item', {})
                            nome = produto.get('name', 'Nome não encontrado')
                            preco = produto.get('offers', {}).get('lowPrice', 'Preço não encontrado')
                            imagem = produto.get('image') or produto.get('MainImage') or None
                            if isinstance(preco, str):
                                preco = preco.replace('R$', '').replace(',', '.')
                                preco = float(preco)
                            resultados.append({'nome': nome, 'preco': preco, 'imagem': imagem, 'farmacia': 'São João'})
            except Exception as e:
                print(f"Erro ao processar script São João: {e}")
        return resultados
    except Exception as e:
        print(f"Erro ao acessar São João: {e}")
        return []
    finally:
        driver.quit()

def buscar_panvel(medicamento):
    search_url = f"https://www.panvel.com/panvel/buscarProduto.do?termoPesquisa={medicamento}"
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")

    driver = None
    try:
        logging.info("Iniciando o driver do Chrome com Selenium-Wire para Panvel...")
        driver = seleniumwire_webdriver.Chrome(options=chrome_options)

        logging.info(f"Acessando a URL de busca: {search_url}")
        driver.get(search_url)

        logging.info("Aguardando a interceptação da requisição da API de busca...")
        request = driver.wait_for_request('/api/v3/search', timeout=30)
        
        if not (request.response and request.response.body):
            logging.error("API de busca foi chamada, mas não retornou um corpo de resposta.")
            return []

        logging.info("Requisição da API interceptada com sucesso! Processando JSON...")
        
        encoding = request.response.headers.get('Content-Encoding', 'identity')
        body = request.response.body

        if encoding == 'gzip':
            logging.info("Resposta compactada com GZIP. Descompactando...")
            decompressed_body = gzip.decompress(body)
        elif encoding == 'br':
            logging.info("Resposta compactada com Brotli. Descompactando...")
            decompressed_body = brotli.decompress(body)
        else:
            decompressed_body = body
        
        response_text = decompressed_body.decode('utf-8')
        data = json.loads(response_text)

        items = data.get("items", [])
        if not items:
            logging.warning(f"JSON da API recebido, mas sem produtos na chave 'items' para '{medicamento}'.")
            return []

        products_list = []
        for item in items:
            price_info = item.get("price", {})
            if not price_info: continue

            price = None
            if price_info.get("pack") and price_info["pack"].get("dealPrice"):
                price = price_info["pack"]["dealPrice"]
            elif price_info.get("dealPrice"):
                price = price_info["dealPrice"]
            elif price_info.get("originalPrice"):
                price = price_info["originalPrice"]
            
            if price is None: continue

            products_list.append({
                "nome": item.get("name", "Nome não disponível").strip(),
                "preco": float(price),
                "imagem": item.get("image"),
                "farmacia": "Panvel"
            })
        
        logging.info(f"Extração da Panvel concluída. {len(products_list)} produtos encontrados.")
        return products_list

    except Exception as e:
        logging.error(f"Erro ao acessar Panvel: {e}")
        return []
    finally:
        if driver:
            driver.quit()

@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    medicamento = request.args.get('medicamento')
    if not medicamento:
        return jsonify({'erro': 'Informe o nome do medicamento'}), 400

    medicamento = medicamento.lower()

    # 1️⃣ Verifica cache
    if medicamento in cache_resultados:
        return jsonify({'medicamentos': cache_resultados[medicamento]})

    # 2️⃣ Verifica banco
    db = client['pharmasearch']
    collection = db['medicamentos']
    existente = collection.find_one({'medicamento': medicamento})

    if existente:
        cache_resultados[medicamento] = existente['dados']
        return jsonify({'medicamentos': existente['dados']})

    # 3️⃣ Se não existe em cache ou banco, faz scraping
    medicamentos_maxxi = buscar_maxxi(medicamento)
    medicamentos_sao_joao = buscar_sao_joao(medicamento)
    medicamentos_panvel = buscar_panvel(medicamento)

    todos = medicamentos_maxxi + medicamentos_sao_joao + medicamentos_panvel
    todos_ordenados = sorted(todos, key=lambda x: x['preco']) if todos else []

    if todos_ordenados:
        cache_resultados[medicamento] = todos_ordenados

        # Salva no banco
        collection.insert_one({
            'medicamento': medicamento,
            'dados': todos_ordenados[:10]
        })

        return jsonify({
            'medicamentos': todos_ordenados[:10],
            'total_encontrado': len(todos_ordenados),
            'farmácias_consultadas': ['Maxxi', 'São João', 'Panvel']
        })
    else:
        return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

#http://127.0.0.1:5000/comparar_precos?medicamento=dipirona