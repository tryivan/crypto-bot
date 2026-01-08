"""
Configurações centralizadas do Crypto Bot.

Usa Pydantic Settings para:
- Carregar variáveis de ambiente
- Validar tipos automaticamente
- Fornecer valores padrão
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from src.utils.logger import get_logger

log_settings = get_logger("bot.settings")


class Settings(BaseSettings):
    """Configurações do bot carregadas do ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",  # Carrega variáveis do arquivo .env
        env_file_encoding="utf-8",
        case_sensitive=False,  # SYMBOL = symbol = Symbol
    )

    # =========================================================================
    # EXCHANGE (carregados do .env)
    # =========================================================================
    exchange: str = ""  # Nome da exchange:  binance, bybit, etc.
    market_type: str = "future"  # "future' ou "spot"
    """. env tem SANDBOX?  
    ├── SIM → usa o valor do .env
    └── NÃO → usa o default do settings.py (True)
    """
    sandbox: bool = True  # Modo teste (SEMPRE começa em True!)

    # Chaves Testnet
    binance_api_key_test: str = ""
    binance_api_secret_test: str = ""

    # Chaves Reais
    binance_api_key: str = ""
    binance_api_secret: str = ""

    @property
    def api_key(self) -> str:
        """
        Retorna a API key correta baseado no sandbox
        @property possibilita acesso como atributo:
        settings = Settings()
        settings.api_key
        """
        return self.binance_api_key_test if self.sandbox else self.binance_api_key

    @property
    def api_secret(self) -> str:
        """
        Retorna o API secret correto baseado no sandbox
        @property possibilita acesso como atributo:
        settings = Settings()
        settings.api_secret
        """
        return self.binance_api_secret_test if self.sandbox else self.binance_api_secret

    # =========================================================================
    # PAIR TRADING
    # =========================================================================
    symbol: str = ""  # Par de moedas:  BTCUSDT, SOLUSDT, etc.
    timeframe: str = ""  # Timeframe:  1m, 5m, 15m, 1h, 4h, 1d
    leverage: int  # Alavancagem
    amount: float  # Quantidade a operar
    stop_loss_percent: float  # Stop Loss em %
    take_profit_percent: float  # Take Profit em %
    max_chase_percent: float
    entry_offset_percent: float
    entry_fill_timeout: int = 30
    max_retries: int = 3  # Tentativas em caso de erro

    # =========================================================================
    # SISTEMA (com defaults)
    # =========================================================================
    timezone: str = "America/Sao_Paulo"
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # =========================================================================
    # VALIDAÇÕES: Int, Float
    # =========================================================================
    @field_validator(
        "leverage",
        "amount",
        "stop_loss_percent",
        "take_profit_percent",
        "max_chase_percent",
        "entry_offset_percent",
        "entry_fill_timeout",
        "max_retries",
    )
    @classmethod
    def validate_positive(cls, v: int | float, info) -> int | float:
        """Garante que valores numéricos críticos sejam positivos."""
        if v <= 0:
            log_settings.error(f"{info.field_name} deve ser maior que 0")
            raise ValueError
        return v

    # =========================================================================
    # VALIDAÇÕES: Strings
    # =========================================================================
    @field_validator(
        "exchange",
        "market_type",
        "binance_api_key_test",
        "binance_api_secret_test",
        "binance_api_key",
        "binance_api_secret",
        "symbol",
        "timeframe",
    )
    @classmethod
    def not_empty(cls, v: str, info) -> str:
        """Garante que campos críticos não sejam strings vazias."""
        if not v or not v.strip():
            log_settings.error(f"{info.field_name} não pode ser vazio")
            raise ValueError
        return v.strip()


# =========================================================================
# INSTÂNCIA GLOBAL (Singleton)
# =========================================================================
settings = Settings()


"""
        
settings = Settings()
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. Lê o arquivo .env                    │
│    (definido em model_config)           │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 2. Para CADA campo da classe:           │
│    ├── Existe no .env?                  │
│    │   ├── SIM → usa valor do . env     │
│    │   └── NÃO → usa fallback           │
│    │             (ou erro se não tiver) │
└─────────────────────────────────────────┘
         │
         ▼
┌───────────��─────────────────────────────┐
│ 3. Converte tipos                        │
│    "true" → True (bool)                  │
│    "10" → 10 (int)                       │
└──────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 4. Executa @field_validator             │
│    ├── Passou?  → continua              │
│    └── Falhou? → EXCEÇÃO!               │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 5. Retorna objeto settings pronto       │
└─────────────────────────────────────────┘
"""
