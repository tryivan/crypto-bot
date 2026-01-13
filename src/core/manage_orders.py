import ccxt
import logging
from typing import Any, Dict, Literal, Optional, Tuple, cast

from src.core.settings import settings
from src.utils.logger import get_logger
from src.utils.ccxt_decorators import handle_ccxt_exceptions


class ManageOrders:
    """
    Orquestra a execução de ordens de trading, ordens de proteção e estado de posição.

    Responsabilidades:
    1. Cálculos de preços (entrada, SL, TP)
    2. Gerenciamento de posições
    3. Gerenciamento de ordens
    4. Execução de ordens
    """

    LONG_SIDE: Literal["buy"] = "buy"
    SHORT_SIDE: Literal["sell"] = "sell"
    VALID_SIDES: Tuple[Literal["buy"], Literal["sell"]] = ("buy", "sell")

    def __init__(self, exchange: ccxt.Exchange) -> None:
        """
        Inicializa o gerenciador de ordens.

        Args:
            exchange:  Instância CCXT autenticada.

        Raises:
            ValueError:  Se campos obrigatórios estiverem ausentes ou inválidos.
            @handle_ccxt_exceptions: Lança exceções específicas CCXT.
        """
        # Atributos de objeto
        self._log_order: logging.Logger = get_logger("bot.manage_orders")
        self._exchange = exchange
        self._symbol = settings.symbol
        self._leverage = settings.leverage
        self._amount = settings.amount
        self._percent_sl = settings.stop_loss_percent
        self._percent_tp = settings.take_profit_percent

        # Configura a alavancagem ao iniciar a classe.
        self._set_leverage()

    # -------------------------------------------------------------------------
    # Definindo a alavancagem
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _set_leverage(self) -> None:
        """Configura a alavancagem na exchange."""
        try:
            self._exchange.set_leverage(self._leverage, self._symbol)
            self._log_order.info(f"Alavancagem configurada:  {self._leverage}x")
        except Exception as exc:
            self._log_order.error(f"Falha ao configurar alavancagem: {exc}")
            raise ValueError

    # -------------------------------------------------------------------------
    # Cálculos de Preço
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _calculate_protection_price(
        self, side: str, entry_price: float, percent: float, is_stop_loss: bool
    ) -> float:
        """Calcula o preço de SL ou TP baseado na entrada."""
        is_long = side == self.LONG_SIDE
        should_subtract = (is_long and is_stop_loss) or (
            not is_long and not is_stop_loss
        )

        if should_subtract:
            price = entry_price * (1 - percent / 100)
        else:
            price = entry_price * (1 + percent / 100)

        precision_price = self._exchange.price_to_precision(self._symbol, price)

        return float(precision_price) if precision_price is not None else float(price)

    @handle_ccxt_exceptions
    def _format_amount(self, amount: float) -> float:
        """Formata a quantidade para a precisão da exchange."""
        try:
            precision_amount = self._exchange.amount_to_precision(self._symbol, amount)
            return (
                float(precision_amount)
                if precision_amount is not None
                else float(amount)
            )
        except Exception:
            self._log_order.error("Erro ao formatar quantidade.")
            return float(amount)

    @handle_ccxt_exceptions
    def _create_protection_order(
        self,
        side: Literal["buy", "sell"],
        entry_price: float,
        order_type: str,
        percent: float,
        is_stop_loss: bool,
        amount: float,
    ) -> Optional[Dict]:
        """Cria uma ordem de proteção (SL ou TP)."""
        try:
            protection_price = self._calculate_protection_price(
                side, entry_price, percent, is_stop_loss
            )
            order_name = "Stop Loss" if is_stop_loss else "Take Profit"
            opposite_side = (
                self.SHORT_SIDE if side == self.LONG_SIDE else self.LONG_SIDE
            )

            order = self._exchange.create_order(
                symbol=self._symbol,
                type=cast(Any, order_type),
                side=opposite_side,
                amount=self._format_amount(amount),
                params={"stopPrice": protection_price, "reduceOnly": True},
            )
            self._log.info(f"{order_name} criado: {protection_price}")
            return order

        except Exception as e:
            order_name = "Stop Loss" if is_stop_loss else "Take Profit"
            self._log_order.warning(f"Erro ao criar {order_name}: {e}")
            return None

    # -------------------------------------------------------------------------
    # Interface Pública
    # -------------------------------------------------------------------------
    def send_protection_orders(
        self, side: Literal["buy", "sell"], entry_price: float
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Cria ordens de SL e TP para uma posição."""
        sl_order = self._create_protection_order(
            side,
            entry_price,
            "stop_market",
            self._percent_sl,
            is_stop_loss=True,
            amount=self._amount,
        )
        tp_order = self._create_protection_order(
            side,
            entry_price,
            "take_profit_market",
            self._percent_tp,
            is_stop_loss=False,
            amount=self._amount,
        )
        return sl_order, tp_order
