import ccxt
import time
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
            exchange: Instância CCXT autenticada.

        Raises:
            ValueError: Se a configuração da alavancagem falhar.
        """
        # Atributos de instância
        self._log_order: logging.Logger = get_logger("bot.manage_orders")
        self._exchange = exchange
        self._symbol = settings.symbol
        self._leverage = settings.leverage
        self._amount = settings.amount
        self._percent_sl = settings.stop_loss_percent
        self._percent_tp = settings.take_profit_percent
        self._max_retries = settings.max_retries
        self._max_chase_percent = settings.chase_percent
        self._entry_offset_percent = settings.offset_percent
        self._entry_fill_timeout = settings.fill_timeout

        # Configura a alavancagem ao inicializar a classe
        self._set_leverage()

    # -------------------------------------------------------------------------
    # Configuração da alavancagem
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _set_leverage(self) -> None:
        """
        Configura a alavancagem na exchange.

        Raises:
            ValueError: Se a configuração da alavancagem falhar.
        """
        self._exchange.set_leverage(self._leverage, self._symbol)
        self._log_order.info(f"Alavancagem configurada: {self._leverage}x")

    # -------------------------------------------------------------------------
    # Cálculos de preço
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _calculate_protection_price(self, side: str, entry_price: float, percent: float, is_stop_loss: bool) -> float:
        """
        Calcula o preço de Stop Loss ou Take Profit baseado no preço de entrada.

        Args:
            side: Lado da operação ('buy' ou 'sell').
            entry_price: Preço de entrada da posição.
            percent: Percentual de distância do preço de entrada.
            is_stop_loss: True para Stop Loss, False para Take Profit.

        Returns:
            Preço calculado com precisão da exchange.
        """
        is_long = side == self.LONG_SIDE
        should_subtract = (is_long and is_stop_loss) or (not is_long and not is_stop_loss)

        if should_subtract:
            price = entry_price * (1 - percent / 100)
        else:
            price = entry_price * (1 + percent / 100)

        precision_price = self._exchange.price_to_precision(self._symbol, price)

        return float(precision_price) if precision_price is not None else float(price)

    @handle_ccxt_exceptions
    def _format_amount(self, amount: float) -> float:
        """
        Formata a quantidade para a precisão da exchange.

        Args:
            amount: Quantidade a ser formatada.

        Returns:
            Quantidade formatada com precisão da exchange.
        """
        precision_amount = self._exchange.amount_to_precision(self._symbol, amount)
        return float(precision_amount) if precision_amount is not None else float(amount)

    @handle_ccxt_exceptions
    def _create_protection_order(
        self, side: Literal["buy", "sell"], entry_price: float, order_type: str, percent: float, is_stop_loss: bool, amount: float
    ) -> Optional[Dict]:
        """
        Cria uma ordem de proteção (Stop Loss ou Take Profit).

        Args:
            side: Lado da operação original ('buy' ou 'sell').
            entry_price: Preço de entrada da posição.
            order_type: Tipo da ordem ('stop_market' ou 'take_profit_market').
            percent: Percentual de distância do preço de entrada.
            is_stop_loss: True para Stop Loss, False para Take Profit.
            amount: Quantidade a ser protegida.

        Returns:
            Dicionário com informações da ordem criada ou None se falhar.
        """
        protection_price = self._calculate_protection_price(side, entry_price, percent, is_stop_loss)
        order_name = "Stop Loss" if is_stop_loss else "Take Profit"
        opposite_side = self.SHORT_SIDE if side == self.LONG_SIDE else self.LONG_SIDE

        order = self._exchange.create_order(
            symbol=self._symbol,
            type=cast(Any, order_type),
            side=opposite_side,
            amount=self._format_amount(amount),
            params={"stopPrice": protection_price, "reduceOnly": True},
        )
        self._log_order.info(f"{order_name} criado: {protection_price}")
        return order

    @handle_ccxt_exceptions
    def _calculate_entry_price(self, side: str, current_price: float, offset_percent: float) -> float:
        """
        Calcula o preço de entrada com offset aplicado.

        Args:
            side: Lado da operação ('buy' ou 'sell').
            current_price: Preço atual de mercado.
            offset_percent: Percentual de offset a aplicar.

        Returns:
            Preço de entrada calculado com precisão da exchange.
        """
        offset = offset_percent / 100

        if side == self.LONG_SIDE:
            price = current_price * (1 - offset)
        else:
            price = current_price * (1 + offset)

        precision_price = self._exchange.price_to_precision(self._symbol, price)
        return float(precision_price) if precision_price is not None else float(price)

    @handle_ccxt_exceptions
    def _get_current_price(self) -> Optional[float]:
        """
        Recupera o preço de mercado atual.

        Returns:
            Preço atual do símbolo ou None se falhar.
        """
        ticker = self._exchange.fetch_ticker(self._symbol)
        return ticker["last"]

    # -------------------------------------------------------------------------
    # Execução de ordens
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _send_order(self, side: Literal["buy", "sell"], amount: float) -> Optional[Dict]:
        """
        Envia ordem de entrada com retry e limite de perseguição de preço.

        Tenta criar e executar uma ordem limit, com retry caso não seja preenchida.
        Cancela ordens não executadas e tenta novamente, até o limite de tentativas
        ou até que o preço se desvie demais do preço inicial.

        Args:
            side: Lado da operação ('buy' ou 'sell').
            amount: Quantidade a ser negociada.

        Returns:
            Dicionário com informações da ordem executada ou melhor tentativa,
            ou None se não conseguir obter o preço inicial.
        """
        max_retries = self._max_retries if self._max_retries > 0 else 1

        initial_price = self._get_current_price()
        if not initial_price:
            return None

        best_attempt: Optional[Dict] = None
        attempt = 0

        while attempt < max_retries:
            attempt += 1
            current_price = self._get_current_price()
            if not current_price:
                break

            price_deviation = abs((current_price - initial_price) / initial_price) * 100
            if price_deviation > self._max_chase_percent:
                self._log_order.warning(f"Preço se moveu {price_deviation:.3f}% desde o início. Abortando.")
                break

            entry_price = self._calculate_entry_price(side, current_price, self._entry_offset_percent)

            order = self._exchange.create_order(symbol=self._symbol, type="limit", side=side, amount=self._format_amount(amount), price=entry_price)

            if not order or "id" not in order:
                continue

            best_attempt = order

            time.sleep(self._entry_fill_timeout)
            refreshed = self._exchange.fetch_order(order["id"], self._symbol)
            filled_qty = float(refreshed.get("filled") or 0)

            if filled_qty > 0:
                return refreshed

            self._log_order.info(f"Ordem {order['id']} não executada. Cancelando e tentando novamente...")

            self._exchange.cancel_order(order["id"], self._symbol)

        return best_attempt

    # -------------------------------------------------------------------------
    # Interface pública
    # -------------------------------------------------------------------------
    def send_protection_orders(self, side: Literal["buy", "sell"], entry_price: float) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Cria ordens de Stop Loss e Take Profit para uma posição.

        Args:
            side: Lado da operação original ('buy' ou 'sell').
            entry_price: Preço de entrada da posição.

        Returns:
            Tupla com (ordem_sl, ordem_tp), onde cada elemento pode ser None se falhar.
        """
        sl_order = self._create_protection_order(side, entry_price, "stop_market", self._percent_sl, is_stop_loss=True, amount=self._amount)
        tp_order = self._create_protection_order(side, entry_price, "take_profit_market", self._percent_tp, is_stop_loss=False, amount=self._amount)
        return sl_order, tp_order

    def open_order(self, side: Literal["buy", "sell"]) -> Dict:
        """
        Abre uma posição com ordem de entrada e ordens de proteção.

        Args:
            side: Lado da ordem ('buy' ou 'sell').

        Returns:
            Dicionário com as seguintes chaves:
                - success (bool): Se a operação foi bem-sucedida.
                - order (Dict | None): Informações da ordem de entrada.
                - entry_price (float | None): Preço de entrada executado.
                - sl_order (Dict | None): Informações da ordem de Stop Loss.
                - tp_order (Dict | None): Informações da ordem de Take Profit.

        Raises:
            ValueError: Se o parâmetro side for inválido.
        """

        if side not in self.VALID_SIDES:
            self._log_order.error(f"Side deve ser '{self.LONG_SIDE}' ou '{self.SHORT_SIDE}': {side}")
            raise ValueError

        order_result = self._send_order(side, self._amount)

        if not order_result or not order_result.get("id"):
            self._log_order.warning("Falha ao criar a ordem principal.")
            return {"success": False, "order": None, "entry_price": None, "sl_order": None, "tp_order": None}

        entry_price = order_result.get("price") or order_result.get("average")
        filled_qty = float(order_result.get("filled") or 0)
        status = str(order_result.get("status") or "").lower()

        is_filled = filled_qty > 0 or status in {"closed", "filled"}

        if not is_filled:
            self._log_order.warning(f"Ordem criada mas não preenchida. [Id: {order_result.get('id')}] [Status: {status}]")
            return {"success": False, "order": order_result, "entry_price": entry_price, "sl_order": None, "tp_order": None}

        self._log_order.info(f"Ordem preenchida! [Lado: {side}] [Preço: {entry_price}] [Id: {order_result['id']}]")

        if filled_qty > 0:
            self._amount = filled_qty

        if entry_price is None:
            entry_price = self._get_current_price()

        if entry_price is None:
            self._log_order.warning("Preço de entrada indisponível. Não é possível criar SL/TP.")
            return {"success": False, "order": order_result, "entry_price": None, "sl_order": None, "tp_order": None}

        sl_order, tp_order = self.send_protection_orders(side, float(entry_price))

        return {"success": True, "order": order_result, "entry_price": float(entry_price), "sl_order": sl_order, "tp_order": tp_order}
