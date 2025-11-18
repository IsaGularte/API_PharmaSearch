# PharmaSearch API

Esta é a API backend para o aplicativo PharmaSearch. Ela realiza scraping de preços de medicamentos em diferentes farmácias, armazena os dados em um banco de dados MongoDB e fornece endpoints para consulta de preços e geolocalização.

## Funcionalidades

-   Busca de preços de medicamentos em múltiplas farmácias.
-   Cache de resultados em memória e no banco de dados para performance.
-   Endpoint para ordenar resultados por distância com base na localização do usuário.
-   Endpoint para encontrar ofertas dinâmicas próximas ao usuário.

## Como Rodar Localmente

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/IsaGularte/API_PharmaSearch.git
    cd API
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure as variáveis de ambiente:**
    -   Crie um arquivo chamado `.env` na pasta `API`.
    -   Adicione sua string de conexão do MongoDB a ele:
        ```

5.  **Execute o servidor:**
    ```bash
    python app.py
    ```
    O servidor estará disponível em `http://127.0.0.1:5000`.

## Endpoints da API

-   `GET /comparar_precos?medicamento=<nome>`
-   `GET /comparar_precos?medicamento=<nome>&latitude=<lat>&longitude=<lon>`
-   `GET /ofertas_proximas?latitude=<lat>&longitude=<lon>`
-   `GET /farmacia_mais_proxima?latitude=<lat>&longitude=<lon>`