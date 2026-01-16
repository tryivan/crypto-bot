import functools
import logging
from typing import Any, Callable
import ccxt


def handle_ccxt_exceptions(method: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorador que centraliza o tratamento de exceções específicas do CCXT.

    Captura exceções lançadas pela biblioteca CCXT, registra logs detalhados
    e relança como RuntimeError com mensagens descritivas. Usa o logger
    'bot.ccxt_decorator' configurado em logger.py.

    Args:
        method: Método a ser decorado.

    Returns:
        Método decorado com tratamento de exceções CCXT.

    Raises:
        RuntimeError: Quando uma exceção CCXT é capturada.

    Exemplo:
        @handle_ccxt_exceptions
        def _send_order(self, side: str) -> dict:
            return self._exchange.create_order(...)
    """

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger("bot.ccxt_decorator")

        try:
            return method(self, *args, **kwargs)
        except ccxt.NetworkError as exc:
            logger.error(f"Erro de rede ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Erro de rede: {exc}") from exc  # L38
        except ccxt.PermissionDenied as exc:
            logger.error(f"Permissão negada ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Permissão negada: {exc}") from exc  # L41
        except ccxt.AuthenticationError as exc:
            logger.error(f"Erro de autenticação ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Erro de autenticação: {exc}") from exc  # L44
        except ccxt.InvalidOrder as exc:
            logger.error(f"Ordem inválida ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Ordem inválida: {exc}") from exc  # L47
        except ccxt.ExchangeError as exc:
            logger.error(f"Erro da exchange ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Erro da exchange: {exc}") from exc  # L50
        except ccxt.BaseError as exc:
            logger.error(f"Erro CCXT ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Erro CCXT: {exc}") from exc  # L53
        except Exception as exc:
            logger.error(f"Erro inesperado ao executar {method.__name__}: {exc}")
            raise RuntimeError(f"Erro inesperado: {exc}") from exc  # L56

    return wrapper
