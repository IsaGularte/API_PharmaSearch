# app.py
from flask import Flask, request, jsonify
import logging
import traceback
from services.search_service import search_medicamento
from services.location_service import enrich_with_location_data, get_nearby_offers , get_closest_pharmacy

app = Flask(__name__)

# Configuração de logging   
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@app.route('/comparar_precos', methods=['GET'])
def comparar_precos():
    try:
        medicamento = request.args.get('medicamento')
        user_lat = request.args.get('latitude', type=float)
        user_lon = request.args.get('longitude', type=float)
        pesquisar_localizacao = user_lat is not None and user_lon is not None

        if not medicamento:
            return jsonify({'erro': 'Informe o nome do medicamento'}), 400

        medicamento = medicamento.lower()
        
        logging.info(f"Iniciando busca por: {medicamento}")
        dados_base = search_medicamento(medicamento)

        if dados_base is None:
            return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
        
        if not dados_base:
            return jsonify({'erro': 'Nenhum medicamento encontrado'}), 404

        resultados_finais = [med.copy() for med in dados_base]

        if pesquisar_localizacao:
            logging.info("Enriquecendo com dados de localização...")
            resultados_finais = enrich_with_location_data(resultados_finais, user_lat, user_lon)

        return jsonify({
            'medicamentos': resultados_finais,
            'total_encontrado': len(resultados_finais)
        })

    except Exception as e:
        logging.error("ERRO CRÍTICO NA API /comparar_precos:")
        traceback.print_exc()
        return jsonify({
            'erro': 'Erro interno no servidor',
            'detalhes': str(e),
            'tipo_erro': type(e).__name__
        }), 500

@app.route('/ofertas_proximas', methods=['GET'])
def ofertas_proximas():
    try:
        user_lat = request.args.get('latitude', type=float)
        user_lon = request.args.get('longitude', type=float)

        if user_lat is None or user_lon is None:
            return jsonify({'erro': 'Latitude e longitude são obrigatórios'}), 400

        ofertas = get_nearby_offers(user_lat, user_lon)

        if ofertas is None:
             return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
        
        if not ofertas:
            return jsonify({'erro': 'Nenhuma oferta encontrada nas proximidades'}), 404

        return jsonify({'ofertas': ofertas})

    except Exception as e:
        logging.error("ERRO CRÍTICO NA API /ofertas_proximas:")
        traceback.print_exc()
        return jsonify({
            'erro': 'Erro interno ao buscar ofertas',
            'detalhes': str(e)
        }), 500

@app.route('/farmacia_mais_proxima', methods=['GET'])
def farmacia_mais_proxima():
    try:
        user_lat = request.args.get('latitude', type=float)
        user_lon = request.args.get('longitude', type=float)

        if user_lat is None or user_lon is None:
            return jsonify({'erro': 'Latitude e longitude são obrigatórios'}), 400

        farmacia = get_closest_pharmacy(user_lat, user_lon)

        if farmacia:
            return jsonify({'farmacia_mais_proxima': farmacia})
        else:
            return jsonify({'erro': 'Nenhuma farmácia encontrada'}), 404

    except Exception as e:
        logging.error(f"ERRO CRÍTICO NA API /farmacia_mais_proxima: {e}")
        traceback.print_exc()
        return jsonify({'erro': 'Erro interno ao buscar farmácia'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)