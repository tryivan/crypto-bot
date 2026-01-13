import ccxt
import logging
from typing import Optional

from src.core.settings import settings
from src.utils.logger import get_logger
from src.utils.ccxt_decorators import handle_ccxt_exceptions


class ExchangeConn:
    """Gerencia conexão com a exchange usando a biblioteca CCXT.

    Responsabilidades:
    - Criar e autenticar conexão com a exchange configurada.
    - Suportar modo sandbox (testnet) e produção.
    - Testar a conexão automaticamente na inicialização.
    - Tratar exceções específicas do CCXT para diagnóstico preciso.

    Attributes:
        exchange (ccxt.Exchange): Instância autenticada da exchange CCXT.
    """

    def __init__(self) -> None:
        """Inicializa conexão com a exchange."""
        self._log_exchange: logging.Logger = get_logger("bot.exchange_conn")
        self._exchange: Optional[ccxt.Exchange] = None

        try:
            """Factory dinâmica para multiplas corretoras"""
            self._exchange_class = getattr(
                ccxt, settings.exchange
            )  # ← retorna a CLASSE
        except AttributeError as e:
            self._log_exchange.error(
                f"Exchange '{settings.exchange}' não encontrada no CCXT: {e}"
            )
            raise

    @handle_ccxt_exceptions
    def _create_ccxt_instance(self) -> ccxt.Exchange:
        """
        Cria e retorna uma instância autenticada da exchange CCXT, usando as configurações globais.
        Ativa o modo sandbox se configurado.
        Returns:
            ccxt.Exchange: Instância autenticada da exchange.
        Raises:
            Exception: Se houver erro na criação da instância.
        """
        try:
            _exchange: ccxt.Exchange = (
                self._exchange_class(  # ← cria um OBJETO a partir da classe
                    {
                        "apiKey": settings.api_key,
                        "secret": settings.api_secret,
                        "enableRateLimit": True,
                        "options": {
                            "defaultType": settings.market_type,
                            "adjustForTimeDifference": True,
                        },
                        "recvWindow": 60000,
                    }
                )
            )
            # Ativa sandbox se necessário
            if settings.sandbox:
                _exchange.enable_demo_trading(True)

            return _exchange

        except Exception as e:
            self._log_exchange.error(f"Erro ao criar instância da exchange: {e}")
            raise

    @handle_ccxt_exceptions
    def _test_connection(self, _exchange: ccxt.Exchange) -> bool:
        """Testa se a conexão com a exchange está funcionando.

        Realiza uma requisição real (fetch_balance) para validar autenticação
        e conectividade. Trata exceções específicas do CCXT para fornecer
        mensagens de erro detalhadas.

        Args:
            exchange (ccxt.Exchange): Instância da exchange a ser testada.

        Returns:
            bool: True se a conexão foi bem-sucedida, False caso contrário.
        """

        _balance = _exchange.fetch_balance()
        _mode = "TESTNET" if settings.sandbox else "REAL"
        self._log_exchange.info(
            f"Conexão testada com sucesso! [ {settings.exchange.upper()}, {settings.market_type} | {_mode} ]"
        )
        self._log_exchange.debug(f"USDT disponível: {_balance['USDT']['free']}")
        return True

    @property
    def exchange(self) -> ccxt.Exchange:
        """Retorna a instância da exchange, criando-a se necessário.

        Implementa padrão de cache: a conexão é criada apenas uma vez
        e reutilizada em chamadas subsequentes.

        Returns:
            ccxt.Exchange: Instância autenticada e testada da exchange.
        Raises:
            ConnectionError: Se a conexão não puder ser estabelecida.
        """
        if self._exchange is None:
            self._exchange = self._create_ccxt_instance()
            if not self._test_connection(self._exchange):
                self._exchange = None
                raise ConnectionError(
                    "Falha ao conectar com a exchange - verifique os logs."
                )
        else:
            self._log_exchange.info(f"CACHE OBJECT: {type(self._exchange)}")
        return self._exchange
