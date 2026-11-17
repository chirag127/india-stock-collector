"""Broker behind an interface. Simulator is default; Shoonya only via official OAuth SDK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OrderRequest:
    uid: str
    actid: str
    exchange: str
    tsym: str
    quantity: int
    limit_price: float
    remarks: str
    product: str = "C"  # CNC delivery only
    price_type: str = "LMT"  # limit only
    retention: str = "DAY"
    ordersource: str = "API"


@dataclass
class OrderResponse:
    stat: str  # Ok | Not_Ok
    norenordno: str = ""
    emsg: str = ""


class BrokerAdapter(Protocol):
    name: str
    def place_order(self, req: OrderRequest) -> OrderResponse: ...
    def order_book(self) -> list[dict]: ...
    def get_quote(self, exchange: str, tsym: str) -> dict: ...


class SimulatorBroker:
    """Deterministic simulator implementing BrokerAdapter. No network calls."""

    name = "simulator"

    def __init__(self) -> None:
        self.orders: list[dict] = []
        self._seq = 0

    def place_order(self, req: OrderRequest) -> OrderResponse:
        # Enforce interface-level safety: delivery limit buys only.
        if req.product != "C" or req.price_type != "LMT" or req.quantity <= 0:
            return OrderResponse(stat="Not_Ok", emsg="simulator rejects non-CNC/limit")
        self._seq += 1
        norenordno = f"SIM{self._seq:08d}"
        self.orders.append({"norenordno": norenordno, "remarks": req.remarks,
                            "tsym": req.tsym, "qty": req.quantity,
                            "price": req.limit_price, "status": "Complete"})
        return OrderResponse(stat="Ok", norenordno=norenordno)

    def order_book(self) -> list[dict]:
        return list(self.orders)

    def get_quote(self, exchange: str, tsym: str) -> dict:
        return {"stat": "Not_Ok", "emsg": "simulator uses recorded quotes"}


class ShoonyaBroker:
    """Live adapter. Wraps official NorenRestApiOAuth SDK lazily; import only on use."""

    name = "shoonya"

    def __init__(self, api=None) -> None:
        self._api = api  # injected NorenApi (OAuth) or None until connect()

    def _require(self):
        if self._api is None:
            raise RuntimeError("Shoonya not connected (OAuth required)")
        return self._api

    def place_order(self, req: OrderRequest) -> OrderResponse:
        api = self._require()
        if req.product != "C" or req.price_type != "LMT":
            return OrderResponse(stat="Not_Ok", emsg="only CNC limit orders allowed")
        payload = {
            "uid": req.uid, "actid": req.actid, "exch": req.exchange,
            "tsym": req.tsym, "qty": str(req.quantity), "dscqty": "0",
            "prc": f"{req.limit_price:.2f}", "prd": "C",
            "trantype": "B", "prctyp": "LMT", "ret": req.retention,
            "ordersource": "API", "remarks": req.remarks,
        }
        try:
            ret = api.place_order(**_sdk_kwargs(payload))
        except Exception as exc:  # network error is ambiguous, never a failure verdict
            return OrderResponse(stat="Not_Ok", emsg=f"ambiguous: {exc}")
        if isinstance(ret, dict) and ret.get("stat") == "Ok":
            return OrderResponse(stat="Ok", norenordno=str(ret.get("norenordno", "")))
        emsg = ret.get("emsg", "rejected") if isinstance(ret, dict) else "rejected"
        return OrderResponse(stat="Not_Ok", emsg=str(emsg))

    def order_book(self) -> list[dict]:
        try:
            ret = self._require().get_orderbook()
        except Exception as exc:
            return [{"error": f"ambiguous: {exc}"}]
        return ret if isinstance(ret, list) else [ret]

    def get_quote(self, exchange: str, tsym: str) -> dict:
        try:
            return self._require().get_quotes(exchange, tsym)
        except Exception as exc:
            return {"stat": "Not_Ok", "emsg": f"ambiguous: {exc}"}


def _sdk_kwargs(payload: dict) -> dict:
    # Map REST fields to official SDK place_order signature without inventing fields.
    return {
        "buy_or_sell": "B",
        "product_type": payload["prd"],
        "exchange": payload["exch"],
        "tradingsymbol": payload["tsym"],
        "quantity": int(payload["qty"]),
        "discloseqty": 0,
        "price_type": payload["prctyp"],
        "price": float(payload["prc"]),
        "retention": payload["ret"],
        "remarks": payload.get("remarks", ""),
    }
