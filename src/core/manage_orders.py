import ccxt
import time
import logging
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, cast

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

    # -------------------------------------------------------------------------
    # Constantes de classe
    # -------------------------------------------------------------------------
    LONG_SIDE: Literal["buy"] = "buy"
    SHORT_SIDE: Literal["sell"] = "sell"
    VALID_SIDES: Tuple[Literal["buy"], Literal["sell"]] = ("buy", "sell")

    # -------------------------------------------------------------------------
    # Inicialização
    # -------------------------------------------------------------------------
    def __init__(self, exchange: ccxt.Exchange) -> None:
        """
        Inicializa o gerenciador de ordens.

        Args:
            exchange: Instância CCXT autenticada.

        Raises:
            ValueError: Se a configuração da alavancagem falhar.
        """
        self._log_order: logging.Logger = get_logger("bot.manage_orders")
        self._exchange = exchange

        # Configurações do par
        self._symbol = settings.symbol
        self._leverage = settings.leverage
        self._amount = settings.amount

        # Configurações de proteção
        self._percent_sl = settings.stop_loss_percent
        self._percent_tp = settings.take_profit_percent

        # Configurações de execução
        self._max_retries = settings.max_retries
        self._max_chase_percent = settings.chase_percent
        self._entry_offset_percent = settings.offset_percent
        self._entry_fill_timeout = settings.fill_timeout

        self._set_leverage()

    @handle_ccxt_exceptions
    def _set_leverage(self) -> None:
        """Configura a alavancagem na exchange."""
        self._exchange.set_leverage(self._leverage, self._symbol)
        self._log_order.info(f"Alavancagem configurada: {self._leverage}x")

    # -------------------------------------------------------------------------
    # Métodos de preço e formatação (privados)
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _get_current_price(self) -> Optional[float]:
        """Recupera o preço de mercado atual."""
        ticker = self._exchange.fetch_ticker(self._symbol)
        return ticker["last"]

    @handle_ccxt_exceptions
    def _format_amount(self, amount: float) -> float:
        """Formata a quantidade para a precisão da exchange."""
        precision_amount = self._exchange.amount_to_precision(self._symbol, amount)
        return float(precision_amount) if precision_amount is not None else float(amount)

    def _calculate_entry_price(self, side: str, current_price: float, offset_percent: float) -> float:
        """Calcula o preço de entrada com offset aplicado."""
        if current_price <= 0:
            raise ValueError(f"current_price deve ser positivo, recebido: {current_price}")

        offset = offset_percent / 100

        if side == self.LONG_SIDE:
            price = current_price * (1 - offset)
        else:
            price = current_price * (1 + offset)

        precision_price = self._exchange.price_to_precision(self._symbol, price)
        return float(precision_price) if precision_price is not None else float(price)

    def _calculate_protection_price(self, side: str, entry_price: float, percent: float, is_stop_loss: bool) -> float:
        """Calcula o preço de Stop Loss ou Take Profit."""
        if entry_price <= 0:
            raise ValueError(f"entry_price deve ser positivo, recebido: {entry_price}")

        is_long = side == self.LONG_SIDE
        should_subtract = (is_long and is_stop_loss) or (not is_long and not is_stop_loss)

        if should_subtract:
            price = entry_price * (1 - percent / 100)
        else:
            price = entry_price * (1 + percent / 100)

        precision_price = self._exchange.price_to_precision(self._symbol, price)
        return float(precision_price) if precision_price is not None else float(price)

    # -------------------------------------------------------------------------
    # Extração de dados de posição (privados)
    # -------------------------------------------------------------------------
    def _extract_entry_price(self, position: Dict[str, Any]) -> Optional[float]:
        """Extrai o preço de entrada da posição."""
        info = position.get("info", {})
        raw_price = position.get("entryPrice") or info.get("entryPrice") or info.get("avgEntryPrice")

        try:
            price = float(raw_price)
            return price if price > 0 else None
        except (TypeError, ValueError):
            return None

    def _extract_size(self, position: Dict[str, Any]) -> float:
        """Extrai o tamanho da posição (valor absoluto)."""
        contracts = position.get("contracts") or position.get("info", {}).get("positionAmt")

        try:
            return abs(float(contracts or 0))
        except (TypeError, ValueError):
            return 0.0

    def _derive_side(self, position: Dict[str, Any]) -> Optional[str]:
        """Determina o lado da posição (buy/sell)."""
        side = position.get("side") or position.get("info", {}).get("positionSide")

        if side:
            side = str(side).lower()
            if side in ("long", "buy"):
                return self.LONG_SIDE
            if side in ("short", "sell"):
                return self.SHORT_SIDE

        contracts = position.get("contracts") or position.get("info", {}).get("positionAmt")

        try:
            value = float(contracts)
            if value > 0:
                return self.LONG_SIDE
            if value < 0:
                return self.SHORT_SIDE
        except (TypeError, ValueError):
            pass

        return None

    # -------------------------------------------------------------------------
    # Busca de dados na exchange (privados)
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _fetch_positions(self) -> List[Dict[str, Any]]:
        """Busca todas as posições para o símbolo."""
        return self._exchange.fetch_positions([self._symbol]) or []

    @handle_ccxt_exceptions
    def _fetch_open_orders(self) -> List[Dict[str, Any]]:
        """Busca todas as ordens abertas para o símbolo."""
        orders: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        def _collect(result: Optional[List[Dict[str, Any]]]) -> None:
            if not result:
                return
            for order in result:
                order_id = str(order.get("id")) if order.get("id") is not None else None
                if order_id and order_id in seen_ids:
                    continue
                if order_id:
                    seen_ids.add(order_id)
                orders.append(order)

        param_variants: List[Optional[Dict[str, Any]]] = [
            None,
            {"stop": True},
            {"type": "STOP"},
            {"type": "stop"},
            {"type": "STOP_MARKET"},
            {"type": "TAKE_PROFIT"},
            {"type": "TAKE_PROFIT_MARKET"},
            {"orderType": "STOP"},
            {"orderType": "TAKE_PROFIT"},
            {"stop": True, "reduceOnly": True},
        ]

        for params in param_variants:
            try:
                if params:
                    response = self._exchange.fetch_open_orders(self._symbol, None, None, params)
                else:
                    response = self._exchange.fetch_open_orders(self._symbol)
                _collect(response)
            except Exception as exc:
                self._log_order.debug(f"fetch_open_orders variant {params or 'default'} ignorado: {exc}")
                time.sleep(0.2)

        return orders

    # -------------------------------------------------------------------------
    # Detecção de ordens de proteção (privados)
    # -------------------------------------------------------------------------
    def _detect_protection_orders(self, position_side: str, entry_price: float) -> Tuple[bool, bool]:
        """Detecta ordens de SL e TP existentes para uma posição."""
        has_sl = False
        has_tp = False
        open_orders = self._fetch_open_orders()
        closing_side = self.SHORT_SIDE if position_side == self.LONG_SIDE else self.LONG_SIDE

        for order in open_orders:
            if not self._is_protection_order(order, closing_side):
                continue

            order_type = self._get_order_type(order)
            stop_price = self._get_stop_price(order)

            # Detecta pelo tipo da ordem
            if "take_profit" in order_type:
                has_tp = True
                continue
            if "stop" in order_type and "take_profit" not in order_type:
                has_sl = True
                continue

            # Detecta pelo preço
            if stop_price is not None:
                is_sl, is_tp = self._classify_by_price(position_side, entry_price, stop_price)
                has_sl = has_sl or is_sl
                has_tp = has_tp or is_tp

        return has_sl, has_tp

    def _is_protection_order(self, order: Dict[str, Any], closing_side: str) -> bool:
        """Verifica se a ordem é uma ordem de proteção válida."""
        reduce_only = order.get("reduceOnly") or order.get("info", {}).get("reduceOnly")
        if not reduce_only:
            return False

        order_side = (order.get("side") or order.get("info", {}).get("side") or "").lower()
        if order_side and order_side not in self.VALID_SIDES:
            if "sell" in order_side:
                order_side = self.SHORT_SIDE
            elif "buy" in order_side:
                order_side = self.LONG_SIDE

        return not order_side or order_side == closing_side

    def _get_order_type(self, order: Dict[str, Any]) -> str:
        """Extrai e normaliza o tipo da ordem."""
        info = order.get("info", {})
        type_candidates = [order.get("type"), info.get("type"), info.get("origType"), info.get("workingType")]
        type_candidates = [str(t).lower() for t in type_candidates if t]
        return " ".join(type_candidates)

    def _get_stop_price(self, order: Dict[str, Any]) -> Optional[float]:
        """Extrai o preço de stop da ordem."""
        raw_stop = order.get("stopPrice") or order.get("info", {}).get("stopPrice")
        if raw_stop is None:
            raw_stop = order.get("price") if order.get("type") in {"take_profit", "TAKE_PROFIT"} else None

        if raw_stop is not None:
            try:
                return float(raw_stop)
            except (TypeError, ValueError):
                pass
        return None

    def _classify_by_price(self, position_side: str, entry_price: float, stop_price: float) -> Tuple[bool, bool]:
        """Classifica a ordem como SL ou TP baseado no preço."""
        is_sl = False
        is_tp = False

        if position_side == self.LONG_SIDE:
            if stop_price < entry_price:
                is_sl = True
            elif stop_price > entry_price:
                is_tp = True
        else:
            if stop_price > entry_price:
                is_sl = True
            elif stop_price < entry_price:
                is_tp = True

        return is_sl, is_tp

    # -------------------------------------------------------------------------
    # Cancelamento de ordens (privados)
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _cancel_orders_individually(self) -> bool:
        """Cancela todas as ordens abertas individualmente."""
        orders = self._fetch_open_orders()
        success = True

        for order in orders:
            try:
                self._exchange.cancel_order(order["id"], self._symbol)
            except Exception as exc:
                success = False
                self._log_order.warning(f"Falha ao cancelar ordem {order.get('id')}: {exc}")

        if not orders:
            self._log_order.info("Nenhuma ordem pendente para cancelar.")

        return success

    @handle_ccxt_exceptions
    def _cancel_all_orders(self) -> None:
        """Cancela todas as ordens abertas usando múltiplas estratégias."""
        params_to_try: List[Optional[Dict[str, Any]]] = [
            None,
            {"type": "STOP"},
            {"type": "TAKE_PROFIT"},
            {"type": "STOP_MARKET"},
            {"type": "TAKE_PROFIT_MARKET"},
            {"stop": True},
            {"orderType": "STOP"},
            {"orderType": "TAKE_PROFIT"},
            {"reduceOnly": True, "stop": True},
        ]

        for params in params_to_try:
            try:
                if params is None:
                    self._exchange.cancel_all_orders(self._symbol)
                else:
                    self._exchange.cancel_all_orders(self._symbol, params=params)
                self._log_order.info(f"cancel_all_orders executado: {params or 'default'}")
            except Exception as exc:
                self._log_order.debug(f"cancel_all_orders ignorado ({params or 'default'}): {exc}")
                time.sleep(0.2)

        self._cancel_orders_individually()

    # -------------------------------------------------------------------------
    # Criação de ordens (privados)
    # -------------------------------------------------------------------------
    @handle_ccxt_exceptions
    def _create_protection_order(
        self, side: Literal["buy", "sell"], entry_price: float, order_type: str, percent: float, is_stop_loss: bool, amount: float
    ) -> Optional[Dict]:
        """Cria uma ordem de proteção (Stop Loss ou Take Profit)."""
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
    def _send_order(self, side: Literal["buy", "sell"], amount: float) -> Optional[Dict]:
        """Envia ordem de entrada com retry e limite de perseguição de preço."""
        max_retries = self._max_retries if self._max_retries > 0 else 1

        initial_price = self._get_current_price()
        if not initial_price or initial_price <= 0:
            self._log_order.error("Preço inicial inválido ou zero. Abortando ordem.")
            return None

        best_attempt: Optional[Dict] = None

        for attempt in range(1, max_retries + 1):
            current_price = self._get_current_price()
            if not current_price or current_price <= 0:
                self._log_order.warning("Preço atual inválido. Abortando tentativa.")
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

    def _recreate_missing_protection(self, side: str, entry_price: float, has_sl: bool, has_tp: bool) -> None:
        """Recria ordens de proteção faltantes."""
        typed_side = cast(Literal["buy", "sell"], side)

        if not has_sl:
            sl_order = self._create_protection_order(typed_side, entry_price, "stop_market", self._percent_sl, is_stop_loss=True, amount=self._amount)
            if not sl_order:
                self._log_order.warning("Falha ao recriar Stop Loss.")

        if not has_tp:
            tp_order = self._create_protection_order(
                typed_side, entry_price, "take_profit_market", self._percent_tp, is_stop_loss=False, amount=self._amount
            )
            if not tp_order:
                self._log_order.warning("Falha ao recriar Take Profit.")

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
            Dicionário com: success, order, entry_price, sl_order, tp_order.

        Raises:
            ValueError: Se o parâmetro side for inválido.
        """
        if side not in self.VALID_SIDES:
            self._log_order.error(f"Side deve ser '{self.LONG_SIDE}' ou '{self.SHORT_SIDE}': {side}")
            raise ValueError(f"Side inválido: {side}")

        result = {"success": False, "order": None, "entry_price": None, "sl_order": None, "tp_order": None}

        order_result = self._send_order(side, self._amount)
        if not order_result or not order_result.get("id"):
            self._log_order.warning("Falha ao criar a ordem principal.")
            return result

        result["order"] = order_result
        entry_price = order_result.get("price") or order_result.get("average")
        result["entry_price"] = entry_price

        filled_qty = float(order_result.get("filled") or 0)
        status = str(order_result.get("status") or "").lower()
        is_filled = filled_qty > 0 or status in {"closed", "filled"}

        if not is_filled:
            self._log_order.warning(f"Ordem criada mas não preenchida. [Id: {order_result.get('id')}] [Status: {status}]")
            return result

        self._log_order.info(f"Ordem preenchida! [Lado: {side}] [Preço: {entry_price}] [Id: {order_result['id']}]")

        if filled_qty > 0:
            self._amount = filled_qty

        if entry_price is None:
            entry_price = self._get_current_price()
            result["entry_price"] = entry_price

        if entry_price is None:
            self._log_order.warning("Preço de entrada indisponível. Não é possível criar SL/TP.")
            return result

        sl_order, tp_order = self.send_protection_orders(side, float(entry_price))
        result.update({"success": True, "entry_price": float(entry_price), "sl_order": sl_order, "tp_order": tp_order})

        return result

    def normalize_position_state(self) -> Optional[bool]:
        """
        Verifica e normaliza o estado da posição.

        Returns:
            True se posição ativa com proteção configurada.
            False se não há posição.
            None se houve erro ao verificar.
        """
        try:
            positions = self._fetch_positions()
        except RuntimeError:
            self._log_order.error("Não foi possível verificar posição. Mantendo estado atual por segurança.")
            return None

        active_position = next((p for p in positions if self._extract_size(p) > 0), None)

        if not active_position:
            self._log_order.info(f"Nenhuma posição ativa em {self._symbol}. Cancelando ordens pendentes.")
            self._cancel_all_orders()
            return False

        entry_price = self._extract_entry_price(active_position)
        side = self._derive_side(active_position)

        if entry_price is None or side is None:
            self._log_order.warning("Posição sem dados suficientes. Cancelando ordens por segurança.")
            self._cancel_all_orders()
            return False

        position_size = self._extract_size(active_position)
        if position_size > 0:
            self._amount = position_size

        has_sl, has_tp = self._detect_protection_orders(side, entry_price)

        if has_sl and has_tp:
            self._log_order.info(f"Posição ativa em {self._symbol}. SL/TP configurados. ✓")
            return True

        self._log_order.warning(f"Ordens de proteção incompletas (SL: {has_sl}, TP: {has_tp}). Recriando...")
        self._recreate_missing_protection(side, entry_price, has_sl, has_tp)

        return True
