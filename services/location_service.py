# services/location_service.py
from database import db
from utils.helpers import haversine
import logging
import random

def enrich_with_location_data(medicamentos, user_lat, user_lon):
    """
    Adiciona dados de localização aos medicamentos e os ordena por distância.
    """
    if db is None:
        logging.error("Conexão com o banco de dados não está disponível no location_service.")
        return sorted(medicamentos, key=lambda x: x['preco']) # Fallback

    farmacias_collection = db['models']
    farmacias_db = list(farmacias_collection.find({}))
    farmacias_map = {f['nome'].lower(): f for f in farmacias_db}

    resultados_completos = []
    for med in medicamentos:
        farmacia_nome = med.get('farmacia', '').lower()
        if farmacia_nome in farmacias_map:
            farmacia_info = farmacias_map[farmacia_nome]
            localizacao = farmacia_info.get('localizacao', {})
            coords = localizacao.get('coordinates')
            
            if coords and len(coords) == 2:
                med['endereco'] = farmacia_info.get('endereco')
                med['latitude'] = float(coords[1])
                med['longitude'] = float(coords[0])
                
                dist = haversine(user_lon, user_lat, med['longitude'], med['latitude'])
                med['distancia_km'] = round(dist, 2)
                
                resultados_completos.append(med)

    if not resultados_completos:
        logging.warning("Nenhum medicamento pôde ser combinado com uma farmácia com coordenadas.")
        return medicamentos

    return sorted(resultados_completos, key=lambda x: x.get('distancia_km', float('inf')))

def get_nearby_offers(user_lat, user_lon):
    """
    Encontra as 3 farmácias mais próximas e busca até 2 ofertas em cada uma.
    """
    if db is None:
        logging.error("Conexão com o banco de dados indisponível para buscar ofertas.")
        return None

    farmacias_collection = db['models']
    medicamentos_collection = db['medicamentos']
    
    farmacias_db = list(farmacias_collection.find({}))
    
    # 1. Calcula a distância para todas as farmácias
    for f in farmacias_db:
        localizacao = f.get('localizacao', {})
        coords = localizacao.get('coordinates')
        if coords and len(coords) == 2:
            lon, lat = float(coords[0]), float(coords[1])
            f['distancia_km'] = haversine(user_lon, user_lat, lon, lat)

    # 2. Filtra e ordena para pegar as 3 mais próximas
    farmacias_proximas = sorted(
        [f for f in farmacias_db if 'distancia_km' in f], 
        key=lambda x: x['distancia_km']
    )[:3] # Pega apenas as 3 primeiras

    ofertas_finais = []
    
    # 3. Itera sobre cada uma das farmácias mais próximas
    for farmacia in farmacias_proximas:
        farmacia_nome = farmacia['nome']
        
        # 4. Busca no banco por documentos de medicamentos que contenham ofertas desta farmácia
        # O 'limit(2)' otimiza a busca, pedindo no máximo 2 documentos para o MongoDB
        cursor = medicamentos_collection.find(
            {"dados.farmacia": farmacia_nome}
        ).limit(2)
        
        ofertas_encontradas_para_farmacia = 0
        for doc_medicamento in cursor:
            # Dentro de cada documento, encontra a oferta específica
            for oferta_item in doc_medicamento['dados']:
                if oferta_item['farmacia'] == farmacia_nome:
                    # Cria uma cópia para não modificar o objeto original
                    oferta_final = oferta_item.copy()
                    
                    # Adiciona os dados de distância e endereço
                    oferta_final['distancia_km'] = round(farmacia['distancia_km'], 2)
                    oferta_final['endereco'] = farmacia.get('endereco')
                    
                    ofertas_finais.append(oferta_final)
                    ofertas_encontradas_para_farmacia += 1
                    
                    # Garante que pegamos no máximo 2 ofertas por farmácia
                    if ofertas_encontradas_para_farmacia >= 2:
                        break # Sai do loop de ofertas dentro do documento
            
            if ofertas_encontradas_para_farmacia >= 2:
                break # Sai do loop de documentos (cursor)

    # 5. Reordena a lista final pela distância para garantir a ordem de exibição
    if ofertas_finais:
        ofertas_finais.sort(key=lambda x: x['distancia_km'])

    return ofertas_finais

def get_closest_pharmacy(user_lat, user_lon):
    """
    Encontra e retorna a farmácia mais próxima do usuário.
    """
    if db is None:
        logging.error("Conexão com o banco de dados indisponível.")
        return None

    farmacias_collection = db['models']
    farmacias_db = list(farmacias_collection.find({}))
    
    if not farmacias_db:
        return None

    farmacia_proxima = None
    menor_distancia = float('inf')

    for f in farmacias_db:
        localizacao = f.get('localizacao', {})
        coords = localizacao.get('coordinates')
        if coords and len(coords) == 2:
            lon, lat = float(coords[0]), float(coords[1])
            dist = haversine(user_lon, user_lat, lon, lat)
            
            if dist < menor_distancia:
                menor_distancia = dist
                farmacia_proxima = {
                    'nome': f.get('nome'),
                    'endereco': f.get('endereco'),
                    'latitude': lat,
                    'longitude': lon,
                    'distancia_km': round(dist, 2)
                }
    
    return farmacia_proxima