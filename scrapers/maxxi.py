from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def buscar_maxxi(medicamento):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=chrome_options)
    try:
        url = f"https://www.maxxieconomica.com/busca-produtos?busca={medicamento}"
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".prodMaxxi__text")))
        nomes = driver.find_elements(By.CSS_SELECTOR, ".prodMaxxi__text")
        precos = driver.find_elements(By.CSS_SELECTOR, ".priceByMaxxi")
        resultados = []
        for i in range(min(len(nomes), len(precos))):
            nome = nomes[i].text.strip()
            preco = precos[i].text.strip().replace('R$', '').replace(',', '.')
            imagem = None
            try:
                bloco_produto = nomes[i].find_element(By.XPATH, "ancestor::div[contains(@class, 'prodMaxxi__item')]")
                img_tag = bloco_produto.find_element(By.CSS_SELECTOR, "img")
                imagem = img_tag.get_attribute("src")
            except Exception:
                imagem = None
            resultados.append({"nome": nome, "preco": float(preco), "imagem": imagem, "farmacia": "Maxxi"})
        return resultados
    except Exception as e:
        print(f"Erro ao acessar Maxxi: {e}")
        return []
    finally:
        driver.quit()
