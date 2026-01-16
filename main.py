"""Crypto Bot - Entry Point"""

from src.core.exchange_conn import ExchangeConn
from src.core.manage_orders import ManageOrders


def main():
    """Inicializa e executa o robô de trading."""

    # 1. Cria objeto de conexão binance
    binance = ExchangeConn().exchange

    # 2. Cria ManageOrders
    manage_orders = ManageOrders(exchange=binance)


if __name__ == "__main__":
    main()
