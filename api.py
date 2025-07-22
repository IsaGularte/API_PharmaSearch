from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager # Mantemos esta importação
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import json
import os

# 🔐 Conexão com MongoDB Atlas
uri = os.getenv("MONGO_URI")
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
    # Mantém a localização explícita para o Chromium
    chrome_options.binary_location = "/usr/bin/chromium"
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # Adicionando argumentos adicionais que podem ajudar em ambientes sem display
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--single-process") # Pode ajudar a reduzir uso de recursos

    try:
        # Pega o caminho do ChromeDriver gerenciado pelo webdriver-manager
        driver_path = ChromeDriverManager().install()
        # Passa o caminho explicitamente para o Service
        service = Service(driver_path)
    except Exception as e:
        print(f"Erro ao instalar ou localizar ChromeDriver: {e}")
        # É importante levantar a exceção para que o Flask não continue
        # com um driver não inicializado.
        raise RuntimeError("Falha ao inicializar ChromeDriver")

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
        driver = None # Inicializa driver como None
        try:
            driver = criar_driver() # Agora criar_driver pode levantar um erro
            url = f"https://www.maxxieconomica.com/busca-produtos?busca={med}"
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".prodMaxxi__text"))
            )
            nomes = driver.find_elements(By.CSS_SELECTOR, ".prodMaxxi__text")
            precos = driver.find_elements(By.CSS_SELECTOR, ".priceByMaxxi")
            resultados = []
            for i in range(min(len(nomes), len(precos))):
                nome = nomes[i].text.strip()
                preco = precos[i].text.strip().replace('R$', '').replace(',', '.')
                resultados.append({"nome": nome, "preco": float(preco), "farmacia": "Maxxi"})
            return resultados
        except Exception as e:
            print(f"Erro ao acessar Maxxi: {e}")
            return []
        finally:
            if driver: # Garante que o driver seja fechado apenas se foi criado
                driver.quit()

    def buscar_sao_joao(med):
        driver = None # Inicializa driver como None
        try:
            driver = criar_driver() # Agora criar_driver pode levantar um erro
            url = f"https://www.saojoaofarmacias.com.br/{med.replace(' ', '%20')}?_q={med.replace(' ', '%20')}&map=ft"
            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, 'script'))
            )
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
                                if isinstance(preco, str):
                                    preco = preco.replace('R$', '').replace(',', '.')
                                    preco = float(preco)
                                resultados.append({'nome': nome, 'preco': preco, 'farmacia': 'São João'})
                except Exception as e:
                    print(f"Erro ao processar script São João: {e}")
            return resultados
        except Exception as e:
            print(f"Erro ao acessar São João: {e}")
            return []
        finally:
            if driver: # Garante que o driver seja fechado apenas se foi criado
                driver.quit()

    try:
        resultados = buscar_maxxi(medicamento) + buscar_sao_joao(medicamento)
    except RuntimeError as e:
        # Se a criação do driver falhar, retorne um erro amigável ao usuário
        return jsonify({'erro': str(e)}), 500

    ordenados = sorted(resultados, key=lambda x: x['preco']) if resultados else []

    if ordenados:
        cache_resultados[medicamento] = ordenados
        db = client['pharmasearch']
        collection = db['medicamentos']
        if not collection.find_one({'medicamento': medicamento}):
            collection.insert_one({
                'medicamento': medicamento,
                'dados': ordenados[:5]
            })
        return jsonify({'medicamentos': ordenados[:5]})
    else:
        return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)