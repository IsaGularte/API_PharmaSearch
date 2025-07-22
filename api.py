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
# Certifique-se de que a variável de ambiente MONGO_URI está configurada no Railway
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
    # O Railway instala o Chromium em /usr/bin/chromium.
    chrome_options.binary_location = "/usr/bin/chromium"
    chrome_options.add_argument("--headless") # Não abre uma janela gráfica do navegador
    chrome_options.add_argument("--no-sandbox") # Essencial para ambientes Linux como o do Railway
    chrome_options.add_argument("--disable-dev-shm-usage") # Reduz o uso de /dev/shm, comum em containers
    # Argumentos adicionais que ajudam a estabilizar o Chromium em ambientes headless/server
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080") # Define um tamanho de janela para renderização
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--no-first-run") # Evita a primeira execução do navegador
    chrome_options.add_argument("--single-process") # Pode ajudar a reduzir uso de recursos e estabilidade
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") # Tenta evitar detecção como bot
    chrome_options.add_argument("--disable-extensions") # Desabilita extensões
    chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process") # Otimizações de processo

    try:
        # Pega o caminho do ChromeDriver gerenciado pelo webdriver-manager.
        # Ele baixará o ChromeDriver compatível com a versão do Chromium instalada.
        driver_path = ChromeDriverManager().install()
        # Passa o caminho do ChromeDriver explicitamente para o Service.
        # Isso garante que o Selenium use o driver correto, e não procure em PATHs genéricos.
        service = Service(driver_path)
    except Exception as e:
        print(f"Erro ao instalar ou localizar ChromeDriver: {e}")
        # É crucial levantar uma exceção aqui para que o Flask capture o erro
        # e não tente usar um driver não inicializado, evitando mais erros.
        raise RuntimeError(f"Falha ao inicializar ChromeDriver: {e}")

    return webdriver.Chrome(service=service, options=chrome_options)

@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    medicamento = request.args.get('medicamento')
    if not medicamento:
        return jsonify({'erro': 'Informe o nome do medicamento'}), 400

    medicamento = medicamento.lower()

    # Verifica se o resultado já está em cache para evitar scraping repetitivo
    if medicamento in cache_resultados:
        return jsonify({'medicamentos': cache_resultados[medicamento]})

    def buscar_maxxi(med):
        driver = None # Inicializa driver como None para o finally
        try:
            driver = criar_driver() # A chamada pode levantar RuntimeError
            url = f"https://www.maxxieconomica.com/busca-produtos?busca={med}"
            driver.get(url)
            # Espera até que elementos específicos do produto estejam presentes
            WebDriverWait(driver, 15).until( # Aumentei o timeout para 15s
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
                except ValueError: # Lida com preços que não podem ser convertidos
                    print(f"Aviso: Preço '{preco}' não pôde ser convertido para float para o produto '{nome}' na Maxxi.")
            return resultados
        except Exception as e: # Captura exceções gerais durante o scraping
            print(f"Erro ao acessar Maxxi: {e}")
            return []
        finally:
            if driver: # Garante que o driver seja fechado apenas se foi criado com sucesso
                driver.quit()

    def buscar_sao_joao(med):
        driver = None # Inicializa driver como None para o finally
        try:
            driver = criar_driver() # A chamada pode levantar RuntimeError
            url = f"https://www.saojoaofarmacias.com.br/{med.replace(' ', '%20')}?_q={med.replace(' ', '%20')}&map=ft"
            driver.get(url)
            # Espera por scripts JSON-LD que contêm dados dos produtos
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
                            # Preço pode estar em 'price' ou 'lowPrice' dentro de 'offers'
                            preco_obj = produto.get('offers', {})
                            preco = preco_obj.get('price', preco_obj.get('lowPrice', 'Preço não encontrado'))

                            if isinstance(preco, str):
                                preco = preco.replace('R$', '').replace(',', '.')
                                try:
                                    preco = float(preco)
                                except ValueError:
                                    print(f"Aviso: Preço '{preco}' não pôde ser convertido para float para o produto '{nome}' na São João.")
                                    continue # Pula para o próximo item se o preço for inválido

                            resultados.append({'nome': nome, 'preco': preco, 'farmacia': 'São João'})
                except json.JSONDecodeError as je:
                    print(f"Erro ao decodificar JSON na São João: {je}")
                except Exception as e:
                    print(f"Erro ao processar script São João: {e}")
            return resultados
        except Exception as e: # Captura exceções gerais durante o scraping
            print(f"Erro ao acessar São João: {e}")
            return []
        finally:
            if driver: # Garante que o driver seja fechado apenas se foi criado com sucesso
                driver.quit()

    try:
        # Tenta buscar os resultados de ambas as farmácias
        resultados = buscar_maxxi(medicamento) + buscar_sao_joao(medicamento)
    except RuntimeError as e:
        # Se a criação do driver (ou alguma falha crítica inicial do Selenium) ocorrer,
        # retorna um erro amigável para o usuário.
        return jsonify({'erro': str(e)}), 500

    # Ordena os resultados pelo preço se houver algum
    ordenados = sorted(resultados, key=lambda x: x['preco']) if resultados else []

    if ordenados:
        cache_resultados[medicamento] = ordenados
        db = client['pharmasearch']
        collection = db['medicamentos']
        # Insere apenas se o medicamento ainda não estiver no banco de dados
        if not collection.find_one({'medicamento': medicamento}):
            # Armazena apenas os 5 primeiros resultados (os mais baratos)
            collection.insert_one({
                'medicamento': medicamento,
                'dados': ordenados[:5]
            })
        # Retorna apenas os 5 primeiros resultados da busca atual
        return jsonify({'medicamentos': ordenados[:5]})
    else:
        # Se nenhum resultado for encontrado em ambas as farmácias
        return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404

if __name__ == '__main__':
    # Define a porta para 8080, que é a porta padrão que o Railway expõe
    port = int(os.environ.get("PORT", 8080)) # Alterei de 5000 para 8080 (padrão do Railway)
    app.run(host="0.0.0.0", port=port)