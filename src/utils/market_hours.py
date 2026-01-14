"""
Módulo para verificar horários de funcionamento do mercado.

Verifica se o mercado está aberto ou em standby baseado nas
configurações de horário definidas no . env
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from enum import Enum


class MarketStatus(str, Enum):
    """Status possíveis do mercado."""

    OPEN = "open"
    STANDBY = "standby"


class MarketHoursChecker:
    """
    Verifica se o mercado está aberto ou em standby.

    Uso:
        from settings import settings

        checker = MarketHoursChecker(
            timezone=settings.market_timezone,
            open_day=settings.market_open_day,
            open_hour=settings.market_open_hour,
            open_minute=settings.market_open_minute,
            close_day=settings.market_close_day,
            close_hour=settings.market_close_hour,
            close_minute=settings.market_close_minute,
        )

        if checker.is_market_open():
            # executar lógica de trading
        else:
            # entrar em standby
    """

    def __init__(self, timezone: str, open_day: int, open_hour: int, open_minute: int, close_day: int, close_hour: int, close_minute: int):
        self.tz = ZoneInfo(timezone)
        self.open_day = open_day
        self.open_hour = open_hour
        self.open_minute = open_minute
        self.close_day = close_day
        self.close_hour = close_hour
        self.close_minute = close_minute

    def get_status(self) -> MarketStatus:
        """
        Verifica se o mercado está aberto ou em standby.

        Retorna:
            MarketStatus. OPEN - Mercado aberto, pode operar
            MarketStatus. STANDBY - Mercado fechado, aguardar
        """
        now = datetime.now(self.tz)
        weekday = now.weekday()
        current_time = now.time()

        # Sábado = sempre standby
        if weekday == 5:
            return MarketStatus.STANDBY

        # Domingo = standby até o horário de abertura
        if weekday == self.open_day:
            open_time = time(self.open_hour, self.open_minute)
            if current_time < open_time:
                return MarketStatus.STANDBY
            return MarketStatus.OPEN

        # Dia de fechamento (sexta) = aberto até o horário de fechamento
        if weekday == self.close_day:
            close_time = time(self.close_hour, self.close_minute)
            if current_time >= close_time:
                return MarketStatus.STANDBY
            return MarketStatus.OPEN

        # Segunda a Quinta = sempre aberto
        return MarketStatus.OPEN

    def is_market_open(self) -> bool:
        """Retorna True se o mercado está aberto."""
        return self.get_status() == MarketStatus.OPEN

    def seconds_until_next_open(self) -> int:
        """
        Calcula quantos segundos faltam até a próxima abertura.

        Útil para fazer sleep inteligente no modo standby.

        Retorna:
            0 se o mercado já está aberto
            Número de segundos até a próxima abertura
        """
        if self.is_market_open():
            return 0

        now = datetime.now(self.tz)
        weekday = now.weekday()

        # Calcula dias até o dia de abertura (domingo)
        days_until_open = (self.open_day - weekday) % 7

        # Se já é domingo mas ainda não abriu, dias_until_open = 0
        # Se é domingo e já passou do horário de abertura, espera próximo domingo
        if days_until_open == 0:
            open_time = time(self.open_hour, self.open_minute)
            if now.time() >= open_time:
                days_until_open = 7

        # Calcula o datetime da próxima abertura
        next_open = now.replace(hour=self.open_hour, minute=self.open_minute, second=0, microsecond=0)
        next_open += timedelta(days=days_until_open)

        return int((next_open - now).total_seconds())
