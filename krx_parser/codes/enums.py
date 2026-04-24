"""Enumerated code sets from `spec/codes.md`.

These are `StrEnum`s so values compare equal to the raw strings that
appear in message payloads. Unknown values raise at construction time,
giving the parser a natural validation point when it wants to coerce a
raw field to a typed enum.
"""

from __future__ import annotations

from enum import StrEnum


class TransactionCode(StrEnum):
    """TR codes (`TRANSACTION_CODE`, seq 2) — one per message type."""

    TCSMIH41301 = "TCSMIH41301"
    TCSMIH42101 = "TCSMIH42101"
    TCSMIH42201 = "TCSMIH42201"
    TCSMIH42301 = "TCSMIH42301"
    TCSMIH42401 = "TCSMIH42401"
    TCSMIH43101 = "TCSMIH43101"
    TCSMIH43201 = "TCSMIH43201"
    TCSMIH43301 = "TCSMIH43301"
    TCSMIH43401 = "TCSMIH43401"
    TCSMIH43501 = "TCSMIH43501"
    TCSMIH43601 = "TCSMIH43601"


class EmsgCompltYn(StrEnum):
    """EMSG_COMPLT_YN — 전문완료여부 (all messages, seq 4)."""

    COMPLETE = "Y"
    IN_FLIGHT = "N"


class ImPrcChgBasSatisfactYn(StrEnum):
    """IM_PRC_CHG_BAS_SATISFACT_YN — 장중추가증거금 가격변동기준 충족여부."""

    SATISFIED = "Y"
    NOT_SATISFIED = "N"


class MrgnKindTpCd(StrEnum):
    """MRGN_KIND_TP_CD — 증거금종류구분코드."""

    TRADING = "1"         # 거래증거금
    TRUST = "2"           # 위탁증거금 (TCSMIH43101 restricts to TRADING)


class TrustPrincipalIntegrationTypeCode(StrEnum):
    """TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE — 위탁자기통합구분코드."""

    TRUST = "10"          # 위탁
    PRINCIPAL = "20"      # 자기


class OvresShortsTypeCode(StrEnum):
    """OVRES_SHORTS_TYPE_CODE — 과부족구분 (TCSMIH42301 seq 11)."""

    OVER = "1"            # 초과
    SHORT = "2"           # 부족
    EQUAL = "3"           # 일치


# Shared value set; dedicated type so the field identity is preserved.
CashableAssetOvresShortsTypeCode = OvresShortsTypeCode


class ClearingSettlementMarketIdentification(StrEnum):
    """CLEARING_SETTLEMENT_MARKET_IDENTIFICATION — 청산결제시장ID.

    Only `SPT` (증권시장) is in-scope for TCSMIH43301 / TCSMIH43401 per
    the current spec. Any other value should be rejected by the caller.
    """

    SPT = "SPT"
