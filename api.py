from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://admin:ilovepharmasearch@pharmasearch-cluster.facv1dr.mongodb.net/?retryWrites=true&w=majority&appName=pharmasearch-cluster"

client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

app = Flask(__name__)
cache_resultados = {}  # Cache simples em memória

@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    medicamento = request.args.get('medicamento')
    if not medicamento:
        return jsonify({'erro': 'Informe o nome do medicamento'}), 400

    medicamento = medicamento.lower()

    # Verifica se já temos em cache
    if medicamento in cache_resultados:
        return jsonify({'medicamentos': cache_resultados[medicamento]})

    def buscar_maxxi(medicamento):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        driver = webdriver.Chrome(options=chrome_options)
        try:
            url = f"https://www.maxxieconomica.com/busca-produtos?busca={medicamento}"
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
            driver.quit()

    medicamentos_maxxi = buscar_maxxi(medicamento)
    medicamentos_sao_joao = buscar_sao_joao(medicamento)
    todos = medicamentos_maxxi + medicamentos_sao_joao
    todos_ordenados = sorted(todos, key=lambda x: x['preco']) if todos else []

    if todos_ordenados:
        cache_resultados[medicamento] = todos_ordenados

        db = client['pharmasearch']
        collection = db['medicamentos']
        existente = collection.find_one({'medicamento': medicamento})

        if not existente:
            collection.insert_one({
                'medicamento': medicamento,
                'dados': todos_ordenados[:5]
            })

        return jsonify({'medicamentos': todos_ordenados[:5]})
    else:
        return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404


if __name__ == '__main__':
    app.run(debug=True)

#http://127.0.0.1:5000/comparar_precos?medicamento=dipirona