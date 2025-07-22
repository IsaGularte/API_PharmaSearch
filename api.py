from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import json
import os

# 🔐 Conexão com MongoDB Atlas
uri = os.getenv("MONGO_URI") # Certifique-se de que MONGO_URI está configurado nas variáveis de ambiente do Railway
client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Conectado ao MongoDB com sucesso!")
except Exception as e:
    print(f"Erro ao conectar no MongoDB: {e}")

app = Flask(__name__)
cache_resultados = {}

# 🚗 Driver configurado para Chromium
def criar_driver():
    chrome_options = Options()
    # Adicionando a localização do binário do Chromium, se necessário.
    # Em muitos ambientes Nixpacks que instalam 'chromium', o binário estará em /usr/bin/chromium.
    # Mas o ChromeDriverManager geralmente configura isso implicitamente.
    # Se o erro persistir mesmo com o nixpacks.toml, você pode tentar descomentar e ajustar esta linha:
    # chrome_options.binary_location = "/usr/bin/chromium"

    # Argumentos essenciais e adicionais para ambientes headless/server
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    chrome_options.add_argument('--disable-setuid-sandbox')

    try:
        # ChromeDriverManager.install() irá baixar o chromedriver adequado
        # e o Service() irá usá-lo. O problema é o navegador (Chromium), não o driver.
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path) # Não precisamos de service_args=["--verbose"] em produção
        print(f"ChromeDriver Service iniciado. Caminho do driver: {driver_path}")
    except Exception as e:
        print(f"Erro ao instalar ou localizar ChromeDriver: {e}")
        raise RuntimeError(f"Falha ao inicializar ChromeDriver: {e}")

    return webdriver.Chrome(service=service, options=chrome_options)

@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    medicamento = request.args.get('medicamento')
    if not medicamento:
        return jsonify({'erro': 'Informe o nome do medicamento'}), 400

    medicamento = medicamento.lower()

    if medicamento in cache_resultados:
        return jsonify({'medicamentos': cache_resultados[medicamento]})

    def buscar_maxxi(med):
        driver = None
        try:
            driver = criar_driver()
            print(f"Acessando Maxxi Econômica para: {med}")
            url = f"https://www.maxxieconomica.com/busca-produtos?busca={med}"
            driver.get(url)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".prodMaxxi__text"))
            )
            nomes = driver.find_elements(By.CSS_SELECTOR, ".prodMaxxi__text")
            precos = driver.find_elements(By.CSS_SELECTOR, ".priceByMaxxi")
            resultados = []
            for i in range(min(len(nomes), len(precos))):
                nome = nomes[i].text.strip()
                preco = precos[i].text.strip().replace('R$', '').replace(',', '.')
                try:
                    resultados.append({"nome": nome, "preco": float(preco), "farmacia": "Maxxi"})
                except ValueError:
                    print(f"Aviso Maxxi: Preço '{preco}' para '{nome}' não pôde ser convertido.")
            print(f"Resultados Maxxi Econômica: {len(resultados)} encontrados.")
            return resultados
        except Exception as e:
            print(f"Erro ao acessar Maxxi: {e}")
            return []
        finally:
            if driver:
                driver.quit()

    def buscar_sao_joao(med):
        driver = None
        try:
            driver = criar_driver()
            print(f"Acessando São João Farmácias para: {med}")
            url = f"https://www.saojoaofarmacias.com.br/{med.replace(' ', '%20')}?_q={med.replace(' ', '%20')}&map=ft"
            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//script[@type='application/ld+json']"))
            )
            scripts = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
            resultados = []
            for script in scripts:
                try:
                    json_data = json.loads(script.get_attribute('innerHTML'))
                    if isinstance(json_data, dict) and json_data.get('@type') == 'ItemList':
                        for item in json_data.get('itemListElement', []):
                            produto = item.get('item', {})
                            nome = produto.get('name', 'Nome não encontrado')
                            preco_obj = produto.get('offers', {})
                            preco = preco_obj.get('price', preco_obj.get('lowPrice', 'Preço não encontrado'))

                            if isinstance(preco, str):
                                preco = preco.replace('R$', '').replace(',', '.')
                                try:
                                    preco = float(preco)
                                except ValueError:
                                    print(f"Aviso São João: Preço '{preco}' para '{nome}' não pôde ser convertido.")
                                    continue

                            resultados.append({'nome': nome, 'preco': preco, 'farmacia': 'São João'})
                except json.JSONDecodeError as je:
                    print(f"Erro ao decodificar JSON na São João: {je}")
                except Exception as e:
                    print(f"Erro ao processar script São João: {e}")
            print(f"Resultados São João: {len(resultados)} encontrados.")
            return resultados
        except Exception as e:
            print(f"Erro ao acessar São João: {e}")
            return []
        finally:
            if driver:
                driver.quit()

    try:
        resultados = buscar_maxxi(medicamento) + buscar_sao_joao(medicamento)
        print(f"Total de resultados combinados: {len(resultados)}")
    except RuntimeError as e:
        return jsonify({'erro': str(e)}), 500

    ordenados = sorted(resultados, key=lambda x: x['preco']) if resultados else []

    if ordenados:
        cache_resultados[medicamento] = ordenados
        db = client['pharmasearch']
        collection = db['medicamentos']
        # Verifica se o medicamento existe antes de tentar inserir
        if not collection.find_one({'medicamento': medicamento}):
            collection.insert_one({
                'medicamento': medicamento,
                'dados': ordenados[:5]
            })
        return jsonify({'medicamentos': ordenados[:5]})
    else:
        return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)