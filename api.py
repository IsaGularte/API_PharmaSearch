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
    # 🎯 MUITO IMPORTANTE: Especificar explicitamente o caminho do executável do Chromium.
    chrome_options.binary_location = "/usr/bin/chromium" # Caminho do Chromium no Railway

    # Argumentos essenciais e adicionais para ambientes headless/server
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu") # Sempre bom em headless
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--single-process")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    chrome_options.add_argument('--disable-setuid-sandbox')

    # Adicionar o argumento Xvfb se o XVFB for usado
    # (Embora o Nixpacks deva lidar com isso, explicitamente não custa)
    # chrome_options.add_argument('--display=:99') # Não necessário se XVFB for configurado para iniciar automaticamente ou se já for headless

    # --- Configuração do Service para ChromeDriver ---
    # Manter log verbose para depuração.
    # log_output='stderr' faz com que os logs do chromedriver apareçam nos logs do Railway.
    service_args = ["--verbose"]
    # service = Service(driver_path, service_args=service_args, log_output='stderr') # Para Selenium 4.6+
    # Para Selenium 4.10.0 (sua versão), 'log_output' pode não estar disponível diretamente no Service
    # mas o '--verbose' em service_args já joga para o stderr.

    try:
        driver_path = ChromeDriverManager().install()
        # Ao criar o Service, você pode definir a variável de ambiente PATH
        # para garantir que o Chromium seja encontrado.
        service_env = os.environ.copy()
        # Garante que /usr/bin está no PATH para o ChromeDriver encontrar o 'chromium'
        if '/usr/bin' not in service_env.get('PATH', ''):
            service_env['PATH'] = f"{service_env.get('PATH', '')}:/usr/bin" if service_env.get('PATH') else "/usr/bin"

        service = Service(driver_path, service_args=service_args, env=service_env)
        print(f"ChromeDriver Service iniciado com log verbose. Caminho do driver: {driver_path}")
        print(f"PATH usado pelo ChromeDriver Service: {service_env.get('PATH')}")

    except Exception as e:
        print(f"Erro ao instalar ou localizar ChromeDriver: {e}")
        # Captura as mensagens de erro do Service, que agora devem ser mais detalhadas.
        if "session not created" in str(e).lower() and "chrome failed to start" in str(e).lower():
            print("Provável causa: Chromium não está iniciando corretamente no container.")
            print("Verifique dependências APT e argumentos do ChromeOptions.")
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

    # As funções de busca permanecem as mesmas, pois o problema não é nelas, mas na inicialização do driver.
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