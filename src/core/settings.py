"""
Configurações centralizadas do Crypto Bot.

Usa Pydantic Settings para:
- Carregar variáveis de ambiente
- Validar tipos automaticamente
- Fornecer valores padrão
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações do bot carregadas do ambiente."""

    model_config = SettingsConfigDict(
        env_file=".env",  # Carrega variáveis do arquivo .env
        env_file_encoding="utf-8",
        case_sensitive=False,  # SYMBOL = symbol = Symbol
    )

    # =========================================================================
    # IDENTIFICAÇÃO DO BOT (obrigatórios - sem default)
    # =========================================================================
    symbol: str  # Par de moedas:  BTCUSDT, SOLUSDT, etc.
    timeframe: str  # Timeframe:  1m, 5m, 15m, 1h, 4h, 1d

    # =========================================================================
    # EXCHANGE (obrigatórios)
    # =========================================================================
    exchange: str  # Nome da exchange:  binance, bybit, etc.
    api_key: str  # Chave da API
    api_secret: str  # Segredo da API

    # =========================================================================
    # TRADING (com defaults seguros)
    # =========================================================================
    leverage: int = 1  # Alavancagem (1 = sem alavancagem)
    amount: float = 0.0  # Quantidade a operar (0 = não opera)
    sandbox: bool = True  # Modo teste (SEMPRE começa em True!)

    # =========================================================================
    # RISK MANAGEMENT (com defaults seguros)
    # =========================================================================
    stop_loss_percent: float = 2.0  # Stop Loss em %
    take_profit_percent: float = 4.0  # Take Profit em %

    # =========================================================================
    # TIMING (com defaults razoáveis)
    # =========================================================================
    wait_sleep: int = 60  # Segundos entre análises
    monitoring_sleep: int = 300  # Segundos entre checks de posição
    max_retries: int = 3  # Tentativas em caso de erro

    # =========================================================================
    # SISTEMA (com defaults)
    # =========================================================================
    timezone: str = "America/Sao_Paulo"
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

    # =========================================================================
    # VALIDAÇÕES CUSTOMIZADAS
    # =========================================================================
    @field_validator("symbol", "timeframe", "exchange", "api_key", "api_secret")
    @classmethod
    def not_empty(cls, v: str, info) -> str:
        """Garante que campos críticos não sejam strings vazias."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} não pode ser vazio")
        return v.strip()


# =========================================================================
# INSTÂNCIA GLOBAL (Singleton)
# =========================================================================
settings = Settings()
