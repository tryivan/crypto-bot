"""Crypto Bot - Entry Point"""

from src.core.exchange_conn import ExchangeConn


def main():
    """Inicializa e executa o robô de trading."""

    # -------------------------------------------------------------------------
    # 1. Conecta a exchange
    # -------------------------------------------------------------------------
    binance = ExchangeConn().exchange


if __name__ == "__main__":
    main()
