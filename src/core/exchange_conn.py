"""
exchange_conn.py

Este módulo gerencia a conexão com exchanges de criptomoedas usando a biblioteca CCXT.

Explicação linha a linha:
- import ccxt: Importa a biblioteca CCXT, que fornece uma interface unificada para múltiplas exchanges.
- from src.core.settings import settings: Importa as configurações globais do bot, como nome da exchange, chaves de API, tipo de mercado e modo sandbox.
- from src.utils.logger import get_logger: Importa a função auxiliar para criar loggers configurados, permitindo rastreamento detalhado de eventos.
- _log_exchange = get_logger("bot.exchange_conn"): Cria um logger específico para este módulo, com nome identificador para os logs.
- class Exchange: Define a classe responsável por gerenciar a conexão com a exchange.
- def __init__(self): Construtor da classe, inicializa a conexão usando as configurações globais.
    - _log_exchange.info(...): Registra no log o início da conexão e o modo (testnet ou real).
    - exchange_class = getattr(ccxt, settings.exchange): Obtém dinamicamente a classe da exchange a partir do nome configurado.
    - self.client = exchange_class({...}): Cria uma instância autenticada da exchange, passando chaves, tipo de mercado e opções.
    - if settings.sandbox: Ativa o modo sandbox/testnet se configurado.
    - _log_exchange.info(...): Registra sucesso na conexão.
- def test_connection(self): Método para testar se a conexão está funcionando.
    - try: Tenta buscar o saldo da conta na exchange.
    - _log_exchange.info(...): Registra sucesso no teste.
    - _log_exchange.debug(...): Registra o saldo disponível de USDT.
    - except Exception as e: Em caso de erro, registra o erro no log.
- exchange = Exchange(): Cria uma instância global (singleton) da classe Exchange, pronta para uso em outros módulos.

Este design garante:
- Conexão única e consistente com a exchange.
- Suporte a múltiplos tipos de mercado e ambiente de testes.
- Logging detalhado para rastreabilidade e depuração.
- Facilidade de uso em todo o projeto via importação da instância global.
"""

import ccxt

from src.core.settings import settings
from src.utils.logger import get_logger

log_exchange = get_logger("bot.exchange_conn")


class Exchange:
    """Gerencia conexão com a exchange."""

    def __init__(self) -> None:
        """Inicializa conexão com a exchange."""
        log_exchange.info(f"Conectando à {settings.exchange.upper()}...")
        log_exchange.info(f"Modo: {'TESTNET' if settings.sandbox else 'REAL'}")

        try:
            self.exchange_class = getattr(ccxt, settings.exchange)  # ← retorna a CLASSE
        except AttributeError as e:
            log_exchange.error(
                f"Exchange '{settings.exchange}' não encontrada no CCXT: {e}"
            )
            raise

        self.client = self._get_exchange()

    def _create_ccxt_instance(self) -> ccxt.Exchange:
        try:
            exchange: ccxt.Exchange = (
                self.exchange_class(  # ← cria um OBJETO a partir da classe
                    {
                        "apiKey": settings.api_key,
                        "secret": settings.api_secret,
                        "enableRateLimit": True,
                        "options": {
                            "defaultType": settings.market_type,
                            "adjustForTimeDifference": True,
                        },
                    }
                )
            )
            # Ativa sandbox se necessário
            if settings.sandbox:
                exchange.enable_demo_trading(True)

            return exchange

        except Exception as e:
            log_exchange.error(f"Erro ao criar instância da exchange: {e}")
            raise

    def _test_connection(self, exchange: ccxt.Exchange) -> bool:
        """Testa se a conexão está funcionando."""
        try:
            balance = exchange.fetch_balance()
            mode = "TESTNET" if settings.sandbox else "REAL"
            log_exchange.info(
                f"Conexão testada com sucesso! [{settings.exchange.upper()}, {settings.market_type} | {mode}]"
            )
            log_exchange.debug(f"USDT disponível: {balance['USDT']['free']}")
            return True
        except ccxt.PermissionDenied as e:
            log_exchange.error(
                f"Permissão negada: verifique as permissões da API - {e}"
            )
            return False
        except ccxt.AuthenticationError as e:
            log_exchange.error(
                f"Erro de autenticação: verifique suas chaves de API - {e}"
            )
            return False
        except ccxt.DDoSProtection as e:
            log_exchange.error(f"Proteção DDoS ativada: aguarde alguns minutos - {e}")
            return False
        except ccxt.RateLimitExceeded as e:
            log_exchange.error(f"Limite de requisições excedido: aguarde - {e}")
            return False
        except ccxt.RequestTimeout as e:
            log_exchange.error(f"Timeout na requisição: verifique sua conexão - {e}")
            return False
        except ccxt.ExchangeNotAvailable as e:
            log_exchange.error(f"Exchange indisponível ou em manutenção - {e}")
            return False
        except ccxt.NetworkError as e:
            log_exchange.error(f"Erro de rede: verifique sua conexão - {e}")
            return False
        except ccxt.ExchangeError as e:
            log_exchange.error(f"Erro da exchange: {e}")
            return False
        except Exception as e:
            log_exchange.error(f"Erro inesperado na conexão: {e}")
            return False

    def _get_exchange(self) -> ccxt.Exchange:
        exchange = self._create_ccxt_instance()
        if not self._test_connection(exchange):
            raise ConnectionError(
                "Falha ao conectar com a exchange - verifique os logs."
            )
        return exchange
