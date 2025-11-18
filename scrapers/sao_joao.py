from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json

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
                                preco = float(preco.replace('R$', '').replace(',', '.'))
                            resultados.append({'nome': nome, 'preco': preco, 'imagem': imagem, 'farmacia': 'São João'})
            except Exception as e:
                print(f"Erro ao processar script São João: {e}")
        return resultados
    except Exception as e:
        print(f"Erro ao acessar São João: {e}")
        return []
    finally:
        driver.quit()