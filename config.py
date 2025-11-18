# config.py
import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env para o ambiente
load_dotenv()

# Pega a MONGO_URI do ambiente. Se não encontrar, usa um valor padrão (pode ser None ou uma URI de dev)
MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    raise ValueError("A variável de ambiente MONGO_URI não foi definida!")