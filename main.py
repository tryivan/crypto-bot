from src.core.exchange_conn import ExchangeConn
from src.core.manage_orders import ManageOrders
from src.core.state_chief import StateChief
from src.utils.market_hours import MarketHoursChecker


def main():
    """Inicializa e executa o robô de trading."""
    binance = ExchangeConn().exchange
    manage_orders = ManageOrders(exchange=binance)
    hours_checker = MarketHoursChecker()

    state_chief = StateChief(exchange=binance, manage_orders=manage_orders, hours_checker=hours_checker)
    state_chief.run()


if __name__ == "__main__":
    main()
