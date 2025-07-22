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
import sys

# --- Conexão com MongoDB Atlas ---
uri = os.getenv("MONGO_URI")
client = None

if not uri:
    print("ERRO: A variável de ambiente MONGO_URI não está configurada.", file=sys.stderr)
else:
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        client.admin.command('ping')
        print("CONECTADO ao MongoDB com sucesso!")
    except Exception as e:
        print(f"ERRO ao conectar no MongoDB: {e}", file=sys.stderr)
        client = None

app = Flask(__name__)
cache_resultados = {}

# --- Configuração do WebDriver para Ambientes Headless ---
def criar_driver():
    chrome_options = Options()

    # --- PONTO CRÍTICO: Tentar diferentes binary_locations e verificar a existência ---
    chrome_binary_paths = [
        "/usr/bin/chromium",              # Prioridade para Chromium
        "/usr/bin/chromium-browser",     # Comum para Chromium no Debian/Ubuntu
        "/usr/bin/google-chrome"         # Comum para Google Chrome
    ]
    found_binary = False
    for path in chrome_binary_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            print(f"Usando binary_location: {path}")
            found_binary = True
            break
    
    if not found_binary:
        print("AVISO: Nenhum Chromium/Chrome binary encontrado nos caminhos esperados.", file=sys.stderr)
        print("Verifique seu nixpacks.toml e os logs de build do Railway.", file=sys.stderr)
        # Se não encontrou, o erro fatal virá do webdriver.Chrome() de qualquer forma.

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
    chrome_options.add_argument("--remote-debugging-port=9222")  # Corrige erro DevToolsActivePort
    # Adicionar User-Agent para evitar detecção de bot e melhorar compatibilidade
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")


    try:
       
        driver_path = ChromeDriverManager().install() 

        service = Service(driver_path)
        print(f"ChromeDriver Service iniciado. Caminho do driver: {driver_path}")
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"ERRO FATAL ao inicializar ChromeDriver/Navegador: {e}", file=sys.stderr)
        print("Certifique-se de que o Chromium/Google Chrome está instalado e acessível no contêiner.", file=sys.stderr)
        raise RuntimeError(f"Falha ao inicializar Selenium WebDriver: {e}")

# --- Rotas da API e Lógica de Busca (Sem Alterações Significativas Aqui) ---
@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    medicamento = request.args.get('medicamento')
    if not medicamento:
        return jsonify({'erro': 'Informe o nome do medicamento'}), 400

    medicamento = medicamento.lower()

    if medicamento in cache_resultados:
        print(f"Retornando resultados para '{medicamento}' do cache.")
        return jsonify({'medicamentos': cache_resultados[medicamento]})

    def buscar_maxxi(med):
        driver = None
        resultados = []
        try:
            driver = criar_driver()
            print(f"Acessando Maxxi Econômica para: {med}")
            url = f"https://www.maxxieconomica.com/busca-produtos?busca={med}"
            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".prodMaxxi__text"))
            )
            nomes = driver.find_elements(By.CSS_SELECTOR, ".prodMaxxi__text")
            precos = driver.find_elements(By.CSS_SELECTOR, ".priceByMaxxi")
            for i in range(min(len(nomes), len(precos))):
                nome = nomes[i].text.strip()
                preco = precos[i].text.strip().replace('R$', '').replace(',', '.')
                try:
                    resultados.append({"nome": nome, "preco": float(preco), "farmacia": "Maxxi"})
                except ValueError:
                    print(f"AVISO Maxxi: Preço '{preco}' para '{nome}' não pôde ser convertido.", file=sys.stderr)
            print(f"Maxxi Econômica: {len(resultados)} resultados encontrados para '{med}'.")
            return resultados
        except Exception as e:
            print(f"ERRO ao acessar Maxxi Econômica: {e}", file=sys.stderr)
            return []
        finally:
            if driver:
                driver.quit()
                print("Driver da Maxxi encerrado.")

    def buscar_sao_joao(med):
        driver = None
        resultados = []
        try:
            driver = criar_driver()
            print(f"Acessando São João Farmácias para: {med}")
            url = f"https://www.saojoaofarmacias.com.br/{med.replace(' ', '%20')}?_q={med.replace(' ', '%20')}&map=ft"
            driver.get(url)
            WebDriverWait(driver, 25).until(
                EC.presence_of_element_located((By.XPATH, "//script[@type='application/ld+json']"))
            )
            scripts = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
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
                                    print(f"AVISO São João: Preço '{preco}' para '{nome}' não pôde ser convertido.", file=sys.stderr)
                                    continue

                            resultados.append({'nome': nome, 'preco': preco, 'farmacia': 'São João'})
                except json.JSONDecodeError as je:
                    print(f"AVISO São João: Erro ao decodificar JSON de script: {je}", file=sys.stderr)
                except Exception as e:
                    print(f"ERRO ao processar script São João: {e}", file=sys.stderr)
            print(f"São João Farmácias: {len(resultados)} resultados encontrados para '{med}'.")
            return resultados
        except Exception as e:
            print(f"ERRO ao acessar São João Farmácias: {e}", file=sys.stderr)
            return []
        finally:
            if driver:
                driver.quit()
                print("Driver da São João encerrado.")

    try:
        medicamentos_maxxi = buscar_maxxi(medicamento)
        medicamentos_sao_joao = buscar_sao_joao(medicamento)

        todos = medicamentos_maxxi + medicamentos_sao_joao
        print(f"Total de resultados combinados após ambas as buscas: {len(todos)}")

    except RuntimeError as e:
        print(f"ERRO FATAL: Falha na inicialização do Selenium WebDriver para '{medicamento}'. Detalhes: {e}", file=sys.stderr)
        return jsonify({'erro': f'Não foi possível iniciar o navegador para buscar preços. Detalhes: {e}'}), 500
    except Exception as e:
        print(f"ERRO INESPERADO durante a busca de medicamentos: {e}", file=sys.stderr)
        return jsonify({'erro': f'Um erro inesperado ocorreu durante a busca. Detalhes: {e}'}), 500

    ordenados = sorted(todos, key=lambda x: x['preco']) if todos else []

    if ordenados:
        cache_resultados[medicamento] = ordenados
        
        if client:
            db = client['pharmasearch']
            collection = db['medicamentos']
            
            try:
                collection.update_one(
                    {'medicamento': medicamento},
                    {'$set': {'dados': ordenados[:5]}},
                    upsert=True
                )
                print(f"Resultados para '{medicamento}' salvos/atualizados no MongoDB.")
            except Exception as e:
                print(f"ERRO ao salvar/atualizar no MongoDB: {e}", file=sys.stderr)
        else:
            print("AVISO: Conexão com MongoDB não estabelecida. Resultados não serão persistidos.", file=sys.stderr)

        return jsonify({'medicamentos': ordenados[:5]})
    else:
        print(f"Nenhum medicamento encontrado para '{medicamento}' após todas as buscas.", file=sys.stderr)
        return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404

# --- Ponto de Entrada da Aplicação ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    print(f"Iniciando a aplicação Flask na porta {port}...")
    app.run(host="0.0.0.0", port=port)