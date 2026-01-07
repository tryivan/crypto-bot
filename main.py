"""Crypto Bot - Entry Point"""

from src.core.settings import settings


def main() -> None:
    print("=== Configurações Carregadas ===")
    print(f"Symbol: {settings.symbol}")
    print(f"Timeframe: {settings.timeframe}")
    print(f"Exchange:  {settings.exchange}")
    print(f"Leverage: {settings.leverage} (tipo: {type(settings.leverage).__name__})")
    print(f"Sandbox: {settings.sandbox} (tipo: {type(settings.sandbox).__name__})")
    print(f"Stop Loss: {settings.stop_loss_percent}%")
    print(f"Timezone: {settings.timezone}")


if __name__ == "__main__":
    main()
