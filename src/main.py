from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
import yfinance as yf
import logging
import gradio as gr
from langchain_core.tools import tool
from typing import Dict
import json
import os
import time

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
if not OPENAI_API_KEY or not OPENAI_MODEL:
    raise ValueError("OPENAI_API_KEY ou OPENAI_MODEL. As variáveis de ambiente não está definida. Adicione-a ao seu arquivo .env")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
llm_model = ChatOpenAI(
    model=OPENAI_MODEL,
    temperature=0,
)


@tool
def get_stock_price(symbol: str) -> str:
    """Obtém o preço atual da ação e informações básicas."""
    logging.info(f"[TOOL] Buscando preço de ações para: {symbol}")
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        hist = stock.history(period="1d")
        if hist.empty:
            logging.error("Nenhum dado histórico encontrado")
            return json.dumps({"error": f"Could not retrieve data for {symbol}"})

        current_price = hist['Close'].iloc[-1]
        result = {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "company_name": info.get('longName', symbol),
            "market_cap": info.get('marketCap', 0),
            "pe_ratio": info.get('trailingPE', 'N/A'),
            "52_week_high": info.get('fiftyTwoWeekHigh', 0),
            "52_week_low": info.get('fiftyTwoWeekLow', 0)
        }
        logging.info(f"[TOOL RESULTADO] {result}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logging.exception("Exception in get_stock_price")
        return json.dumps({"error": str(e)})


@tool
def get_financial_statements(symbol: str) -> str:
    """Recupera dados principais das demonstrações financeiras."""
    try:
        stock = yf.Ticker(symbol)
        financials = stock.financials
        balance_sheet = stock.balance_sheet

        latest_year = financials.columns[0]

        return json.dumps({
            "symbol": symbol,
            "period": str(latest_year.year),
            "revenue": float(
                financials.loc['Total Revenue', latest_year]) if 'Total Revenue' in financials.index else 'N/A',
            "net_income": float(
                financials.loc['Net Income', latest_year]) if 'Net Income' in financials.index else 'N/A',
            "total_assets": float(
                balance_sheet.loc['Total Assets', latest_year]) if 'Total Assets' in balance_sheet.index else 'N/A',
            "total_debt": float(
                balance_sheet.loc['Total Debt', latest_year]) if 'Total Debt' in balance_sheet.index else 'N/A'
        }, indent=2)
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_technical_indicators(symbol: str, period: str = "3mo") -> str:
    """Calcula indicadores técnicos principais."""
    hist = None
    for i in range(3):
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period=period)
            if not hist.empty:
                break
            else:
                logging.warning(f"Attempt {i + 1} failed for {symbol}. Retrying in 5 seconds.")
                time.sleep(5)
        except Exception as e:
            logging.error(f"Exception on attempt {i + 1} for {symbol}: {e}")
            if i == 2:
                return json.dumps({"error": f"Failed to retrieve data for {symbol} after 3 attempts."})
            time.sleep(5)

    if hist is None or hist.empty:
        return json.dumps({"error": f"No historical data found for {symbol} after retries."})

    try:
        hist['SMA_20'] = hist['Close'].rolling(window=20).mean()
        hist['SMA_50'] = hist['Close'].rolling(window=50).mean()

        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        latest = hist.iloc[-1]
        latest_rsi = rsi.iloc[-1]

        return json.dumps({
            "symbol": symbol,
            "current_price": round(latest['Close'], 2),
            "sma_20": round(latest['SMA_20'], 2),
            "sma_50": round(latest['SMA_50'], 2),
            "rsi": round(latest_rsi, 2),
            "volume": int(latest['Volume']),
            "trend_signal": "bullish" if latest['Close'] > latest['SMA_20'] > latest['SMA_50'] else "bearish"
        }, indent=2)
    except Exception as e:
        logging.exception("Exception in get_technical_indicators after data retrieval")
        return json.dumps({"error": str(e)})


# Configurações dos sub-agentes
analista_fundamentalista = {
    "name": "analista-fundamentalista",
    "description": "Realiza análise fundamentalista profunda de empresas incluindo índices financeiros, métricas de crescimento e valuation",
    "prompt": """Você é um analista fundamentalista especialista com 15+ anos de experiência.
    Foque em:
    - Análise de demonstrações financeiras
    - Análise de índices (P/L, P/VPA, ROE, ROA, Dívida/Patrimônio)
    - Métricas de crescimento e tendências
    - Comparações com o setor
    - Cálculos de valor intrínseco
    Sempre forneça números específicos e cite suas fontes."""
}

analista_tecnico = {
    "name": "analista-tecnico",
    "description": "Analisa padrões de preço, indicadores técnicos e sinais de trading",
    "prompt": """Você é um analista técnico profissional especializado em análise gráfica e sinais de trading.
    Foque em:
    - Ação do preço e análise de tendência
    - Indicadores técnicos (RSI, MACD, Médias Móveis)
    - Níveis de suporte e resistência
    - Análise de volume
    - Recomendações de entrada/saída
    Forneça níveis de preço específicos e prazos para suas recomendações."""
}

analista_risco = {
    "name": "analista-risco",
    "description": "Avalia riscos de investimento e fornece avaliação de risco",
    "prompt": """Você é um especialista em gestão de riscos focado em identificar e quantificar riscos de investimento.
    Foque em:
    - Análise de risco de mercado
    - Riscos específicos da empresa
    - Riscos setoriais e da indústria
    - Riscos de liquidez e crédito
    - Riscos regulatórios e de compliance
    Sempre quantifique os riscos quando possível e sugira estratégias de mitigação."""
}

subagents = [analista_fundamentalista, analista_tecnico, analista_risco]

# Instruções principais de pesquisa
research_instructions = """Você é um analista de pesquisa de ações de elite com acesso a múltiplas ferramentas especializadas e sub-agentes.

Seu processo de pesquisa deve ser sistemático e abrangente:

1. **Coleta Inicial de Dados**: Comece coletando informações básicas da ação, dados de preço e notícias recentes
2. **Análise Fundamentalista**: Mergulhe profundamente nas demonstrações financeiras, índices e fundamentos da empresa
3. **Análise Técnica**: Analise padrões de preço, tendências e indicadores técnicos
4. **Avaliação de Risco**: Identifique e avalie riscos potenciais
5. **Análise Competitiva**: Compare com pares do setor quando relevante
6. **Síntese**: Combine todas as descobertas em uma tese de investimento coerente
7. **Recomendação**: Forneça recomendação clara de compra/venda/manter com preços-alvo

Sempre:
- Use dados específicos e números para apoiar sua análise
- Cite suas fontes e metodologia
- Considere múltiplas perspectivas e cenários potenciais
- Forneça insights acionáveis e recomendações concretas
- Estruture seu relatório final profissionalmente

Ao usar sub-agentes, forneça a eles tarefas específicas e focadas e incorpore seus insights especializados em sua análise geral."""

# Define all tools
tools = [
    get_stock_price,
    get_financial_statements,
    get_technical_indicators
]

# Create the DeepAgent
stock_research_agent = create_deep_agent(
    tools=tools,
    instructions=research_instructions,
    subagents=subagents,
    model=llm_model
)


def run_stock_research(query: str):
    """Executa o agente de pesquisa de ações e retorna o conteúdo da mensagem final com logging de debug."""
    try:
        logging.info(f"[run_stock_research] Query received: {query}")

        result = stock_research_agent.invoke(
            {"messages": [{"role": "user", "content": query}]},
            {"recursion_limit": 100}
        )

        logging.debug(f"[run_stock_research] Full result: {result}")

        messages = result.get("messages", [])
        output_text = ""

        if not messages:
            logging.warning("[run_stock_research] No messages returned in result.")
            output_text = "Error: No response messages received."
        elif isinstance(messages[-1], dict):
            output_text = messages[-1].get("content", "")
            logging.debug(f"[run_stock_research] Output content from dict: {output_text}")
        elif hasattr(messages[-1], "content"):
            output_text = messages[-1].content
            logging.debug(f"[run_stock_research] Output content from object: {output_text}")
        else:
            logging.error("[run_stock_research] Unrecognized message format.")
            output_text = "Error: Invalid response message format."

        file_output = ""
        if "files" in result:
            file_output += "\n\n=== Generated Research Files ===\n"
            for filename, content in result["files"].items():
                preview = content[:500] + "..." if len(content) > 500 else content
                file_output += f"\n**{filename}**\n{preview}\n"
                logging.debug(f"[run_stock_research] File: {filename}, Preview: {preview[:100]}")

        return output_text + file_output

    except Exception as e:
        logging.exception("[run_stock_research] Exception during invocation:")
        return f"Error: {str(e)}"


# Cria interface Gradio UI
with gr.Blocks() as app:
    gr.Markdown("## 📊 Agente de Pesquisa de Ações")
    gr.Markdown("Digite sua solicitação de pesquisa abaixo. Exemplo: *Análise abrangente da Petróleo Brasileiro S.A. (PETR4)*")

    with gr.Row():
        query_input = gr.Textbox(label="Consulta de Pesquisa", lines=3, placeholder="Digite sua consulta de pesquisa aqui...")

    run_button = gr.Button("Executar Análise")
    output_box = gr.Textbox(label="Relatório de Pesquisa", lines=20)

    run_button.click(fn=run_stock_research, inputs=query_input, outputs=output_box)

# Inicia aplicação
app.launch(server_name="0.0.0.0", server_port=7860)
