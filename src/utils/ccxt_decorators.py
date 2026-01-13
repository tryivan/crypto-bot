import functools
import ccxt
import logging


def handle_ccxt_exceptions(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        # Tenta usar um logger do objeto, senão usa o logger do módulo
        logger = logging.getLogger("ccxt_decorator")

        try:
            return method(self, *args, **kwargs)
        except ccxt.NetworkError as exc:
            logger.error(f"Erro de rede: {exc}")
            raise ValueError(f"Erro de rede: {exc}")
        except ccxt.PermissionDenied as exc:
            logger.error(f"Permissão negada: {exc}")
            raise ValueError(f"Permissão negada: {exc}")
        except ccxt.AuthenticationError as exc:
            logger.error(f"Erro de autenticação: {exc}")
            raise ValueError(f"Erro de autenticação: {exc}")
        except ccxt.InvalidOrder as exc:
            logger.error(f"Ordem inválida: {exc}")
            raise ValueError(f"Ordem inválida: {exc}")
        except ccxt.ExchangeError as exc:
            logger.error(f"Erro da exchange: {exc}")
            raise ValueError(f"Erro da exchange: {exc}")
        except ccxt.BaseError as exc:
            logger.error(f"Erro CCXT: {exc}")
            raise ValueError(f"Erro CCXT: {exc}")
        except Exception as exc:
            logger.error(f"Erro inesperado: {exc}")
            raise ValueError(f"Erro inesperado: {exc}")

    return wrapper
