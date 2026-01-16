import time
from enum import Enum
from typing import Literal, Optional
from src.core.settings import settings
from src.core.manage_orders import ManageOrders
from src.utils.market_hours import MarketHoursChecker

import ccxt

from src.utils.logger import get_logger


class StateChief:
    """
    Máquina de estados principal do robô.

    Gerencia o ciclo completo: inicialização, análise, abertura e monitoramento.
    """

    class BotState(Enum):
        INITIALIZING = "initializing"
        ANALYZING = "analyzing"
        OPENING_POSITION = "opening_position"
        MONITORING = "monitoring"
        STANDBY = "standby"
        ERROR = "error"

    def __init__(self, exchange: ccxt.Exchange, manage_orders: ManageOrders, hours_checker: MarketHoursChecker) -> None:
        """
        Inicializa o controlador de estados.

        Args:
            exchange: Instância CCXT autenticada.
            manage_orders: Intância ManageOrders
            hours_checker: Intância MarketHoursChecker

        """
        self._log_state_chief = get_logger("bot.state_chief")

        # Dependências principais
        self._symbol = settings.symbol
        self._timeframe = settings.timeframe
        self._exchange = exchange
        self._manage_orders = manage_orders
        self._hours_checker = hours_checker

        # Estado
        self._state = StateChief.BotState.INITIALIZING
        self._side: Optional[Literal["buy", "sell"]] = None
        self._retry_count: int = 0
        self._max_retries: int = settings.max_retries

        self._wait_sleep: int = 60  # Intervalo padrão (segundos)
        self._next_window: int = 0
        self._monitoring_sleep: int = 300  # MONITORING: 5 minutos

        self._log_state_chief.info("StateChief inicializado. Estado: INITIALIZING")

    # =========================================================================
    # LOOP PRINCIPAL
    # =========================================================================
    def run(self) -> None:
        """Loop principal da máquina de estados."""
        while self._state is not None:
            try:
                self._log_state_chief.info(f"[Estado: {self._state.value}]")

                if self._state == StateChief.BotState.INITIALIZING:
                    self._handle_initializing()

                elif self._state == StateChief.BotState.ANALYZING:
                    self._handle_analyzing()

                elif self._state == StateChief.BotState.OPENING_POSITION:
                    self._handle_opening_position()

                elif self._state == StateChief.BotState.MONITORING:
                    self._handle_monitoring()

                elif self._state == StateChief.BotState.ERROR:
                    self._handle_error()

                elif self._state == StateChief.BotState.STANDBY:
                    self._log_state_chief.info("Estado IDLE — aguardando próxima janela operacional...")
                    time.sleep(self._next_window)

            except KeyboardInterrupt:
                self._log_state_chief.info("Bot interrompido manualmente. Encerrando...")
                break

            except Exception as e:
                self._log_state_chief.critical(f"Erro inesperado no loop principal: {e}", exc_info=True)
                self._state = StateChief.BotState.ERROR

    # =========================================================================
    # HANDLERS DE ESTADO
    # =========================================================================
    def _handle_initializing(self) -> None:
        """Inicializa ManageOrders e normaliza posição."""
        try:
            # Verifica janela operacional
            is_market_open = self._hours_checker.is_market_open()
            if not is_market_open:
                self._log_state_chief.info("Horário fora da janela operacional.")
                self._next_window = self._hours_checker.seconds_until_next_open()
                self._state = StateChief.BotState.STANDBY

            # Normaliza posição existente
            is_trading = self._manage_orders.normalize_position_state()

            # None = erro ao verificar, vai pro ERROR
            if is_trading is None:
                self._log_state_chief.error("Não foi possível verificar posição. Indo para ERROR.")
                self._retry_count += 1
                self._state = StateChief.BotState.ERROR
                return

            if is_trading:
                self._log_state_chief.info("Posição ativa detectada. Indo para MONITORING.")
                self._state = StateChief.BotState.MONITORING
            else:
                self._log_state_chief.info("Nenhuma posição aberta. Indo para ANALYZING.")
                self._state = StateChief.BotState.ANALYZING

            self._retry_count = 0

        except Exception as e:
            self._log_state_chief.critical(f"Erro ao inicializar: {e}", exc_info=True)
            self._retry_count += 1
            self._state = StateChief.BotState.ERROR

    def _handle_analyzing(self) -> None:
        """Executa análise de mercado e identifica sinais."""
        try:
            self._log_state_chief.info(f"Analisando {self._symbol} ({self._timeframe})...")

            # 1. Atualiza dados
            df = self._dataset_manager.update()

            if df.empty:
                self._log_state_chief.warning("DataFrame vazio. Aguardando próximo ciclo.")
                time.sleep(self._wait_sleep)
                return

            # 2. Aplica indicadores
            df = self._indicator_pipeline.apply(df, self._strategy_config)

            # 3. Gera sinais
            df = self._strategy.generate_signals(df)

            # 4. Salva dados
            self._dataset_manager.save(df)

            if "signal" not in df.columns:
                self._log_state_chief.warning("Coluna 'signal' ausente. Aguardando próximo ciclo.")
                time.sleep(self._wait_sleep)
                return

            # 5. Lê sinal mais recente
            latest_signal = int(df["signal"].iloc[-1])

            if latest_signal == 1:
                self._side = "buy"
                self._log_state_chief.info("Sinal detectado: LONG (BUY). Indo para OPENING_POSITION.")
                self._state = StateChief.BotState.OPENING_POSITION

            elif latest_signal == -1:
                self._side = "sell"
                self._log_state_chief.info("Sinal detectado: SHORT (SELL). Indo para OPENING_POSITION.")
                self._state = StateChief.BotState.OPENING_POSITION

            else:
                self._log_state_chief.info("Nenhum sinal detectado. Aguardando próximo candle.")
                time.sleep(self._wait_sleep)

            self._retry_count = 0

        except Exception as e:
            self._log_state_chief.error(f"Erro durante análise: {e}", exc_info=True)
            self._retry_count += 1
            self._state = StateChief.BotState.ERROR

    def _handle_opening_position(self) -> None:
        """Abre uma nova posição com base no sinal."""
        try:
            if not self._side:
                self._log_state_chief.warning("Nenhum 'side' definido. Voltando para ANALYZING.")
                self._state = StateChief.BotState.ANALYZING
                return

            if self._manage_orders is None:
                self._log_state_chief.error("ManageOrders não inicializado.")
                self._state = StateChief.BotState.ERROR
                return

            self._log_state_chief.info(f"Tentando abrir posição: {self._side.upper()} para {self._symbol}")

            # Abre ordem
            result = self._manage_orders.open_order(self._side)

            if result and result.get("success"):
                entry_price = result.get("entry_price")
                self._log_state_chief.info(f"Posição aberta! Preço: {entry_price}")
                self._state = StateChief.BotState.MONITORING
            else:
                self._log_state_chief.warning("Falha ao abrir posição. Voltando para ANALYZING.")
                self._state = StateChief.BotState.ANALYZING

            self._side = None
            self._retry_count = 0

        except Exception as e:
            self._log_state_chief.critical(f"Erro ao abrir posição: {e}", exc_info=True)
            self._retry_count += 1
            self._state = StateChief.BotState.ERROR

    def _handle_monitoring(self) -> None:
        """Monitora posição ativa."""
        try:
            self._log_state_chief.info(f"Monitorando posição em {self._symbol}...")

            if self._manage_orders is None:
                self._log_state_chief.error("ManageOrders não inicializado.")
                self._state = StateChief.BotState.ERROR
                return

            is_trading = self._manage_orders.normalize_position_state()

            # None = erro ao verificar, mantém MONITORING e tenta novamente
            if is_trading is None:
                self._log_state_chief.warning("Erro ao verificar posição. Mantendo MONITORING por segurança.")
                time.sleep(self._monitoring_sleep)
                return

            if not is_trading:
                self._log_state_chief.info("Posição encerrada. Voltando para ANALYZING.")
                self._state = StateChief.BotState.ANALYZING
            else:
                self._log_state_chief.info("Ordens de proteção confirmadas.")
                time.sleep(self._monitoring_sleep)

        except Exception as e:
            self._log_state_chief.critical(f"Erro no monitoramento: {e}", exc_info=True)
            self._retry_count += 1
            self._state = StateChief.BotState.ERROR

    def _handle_error(self) -> None:
        """Tenta recuperar após falhas."""
        self._log_state_chief.warning(f"Estado ERROR. Tentativa {self._retry_count}/{self._max_retries}")

        try:
            time.sleep(20)

            if self._retry_count >= self._max_retries:
                self._log_state_chief.critical("Limite de tentativas atingido. Encerrando robô.")
                self._state = None  # Encerra o loop
                return

            self._log_state_chief.info("Tentando reinicialização...")
            self._state = StateChief.BotState.INITIALIZING

        except Exception as e:
            self._log_state_chief.critical(f"Erro na recuperação: {e}", exc_info=True)
            self._retry_count += 1
