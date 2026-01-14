"""
Teste rápido do MarketHoursChecker.
Execute:  python test_market_hours.py
"""

from src.core.settings import settings
from src.utils.market_hours import MarketHoursChecker, MarketStatus

# Cria o checker com as configurações do . env
checker = MarketHoursChecker(
    timezone=settings.market_timezone,
    open_day=settings.market_open_day,
    open_hour=settings.market_open_hour,
    open_minute=settings.market_open_minute,
    close_day=settings.market_close_day,
    close_hour=settings.market_close_hour,
    close_minute=settings.market_close_minute,
)

# Testa
print("=" * 50)
print("🔍 TESTE DO MARKET HOURS CHECKER")
print("=" * 50)

print(f"\n📍 Timezone: {settings.market_timezone}")
print(f"📅 Abertura:  Dia {settings.market_open_day} às {settings.market_open_hour}:{settings.market_open_minute:02d}")
print(f"📅 Fechamento: Dia {settings.market_close_day} às {settings.market_close_hour}:{settings.market_close_minute:02d}")

status = checker.get_status()
print(f"\n🚦 Status atual: {status.value.upper()}")

if checker.is_market_open():
    print("✅ Mercado ABERTO - Pode operar!")
else:
    seconds = checker.seconds_until_next_open()
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    print(f"🔴 Mercado FECHADO - Standby por {hours}h {minutes}min")

print("\n" + "=" * 50)
