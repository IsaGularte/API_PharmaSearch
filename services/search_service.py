# services/search_service.py
import logging
from database import db
from scrapers.maxxi import buscar_maxxi
from scrapers.sao_joao import buscar_sao_joao
from scrapers.panvel import buscar_panvel

cache_resultados = {}

def search_medicamento(medicamento):
    """
    Orquestra a busca por um medicamento, usando cache, banco ou scraping.
    """
    # --- CORREÇÃO AQUI ---
    if db is None: # Em vez de 'if not db:'
        logging.error("Conexão com o banco de dados não está disponível (db is None).")
        return None # Retorna None se não houver conexão com o banco

    medicamentos_collection = db['medicamentos']

    # 1. Tenta buscar do cache ou do banco
    if medicamento in cache_resultados:
        logging.info(f"'{medicamento}' encontrado no cache.")
        return cache_resultados[medicamento]
    
    existente = medicamentos_collection.find_one({'medicamento': medicamento})
    if existente:
        logging.info(f"'{medicamento}' encontrado no banco de dados.")
        dados = existente['dados']
        cache_resultados[medicamento] = dados
        return dados

    # 2. Se não encontrou, faz o scraping
    logging.info(f"'{medicamento}' não encontrado. Iniciando scraping...")
    medicamentos_maxxi = buscar_maxxi(medicamento)
    medicamentos_sao_joao = buscar_sao_joao(medicamento)
    medicamentos_panvel = buscar_panvel(medicamento)
    
    todos = medicamentos_maxxi + medicamentos_sao_joao + medicamentos_panvel
    if not todos:
        return []

    # 3. Ordena por preço e salva
    dados_medicamentos = sorted(todos, key=lambda x: x['preco'])
    dados_para_salvar = dados_medicamentos[:10]

    medicamentos_collection.update_one(
        {'medicamento': medicamento},
        {'$set': {'dados': dados_para_salvar}},
        upsert=True
    )
    cache_resultados[medicamento] = dados_para_salvar
    
    return dados_para_salvar