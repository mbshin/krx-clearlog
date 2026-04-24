# KRX Code Sets

Enumerated code values referenced by fields in
[`messages.md`](./messages.md). Each section lists the code, its
meaning, and which messages/fields use it.

These should be loaded by the parser as Python `Enum` / `StrEnum`
types so invalid values raise at parse time rather than silently
passing through to the DB.

## 1. Transaction codes (TR codes)

Field: `TRANSACTION_CODE` (seq 2) — identifies the message type. The
parser's schema registry is keyed on this value.

| Code          | Description                                                | Market |
| ------------- | ---------------------------------------------------------- | ------ |
| `TCSMIH41301` | 장중추가증거금 — 기초자산변동률 부과요건                   | 파생   |
| `TCSMIH42101` | 거래증거금 — 종목별 증거금률                               | 증권   |
| `TCSMIH42201` | 거래증거금 — 위탁·자기별 거래증거금 소요액                 | 증권   |
| `TCSMIH42301` | 거래증거금 — 과부족 내역 통보                              | 증권   |
| `TCSMIH42401` | 거래증거금 — 위탁·자기별 종목별 거래량가중평균가격         | 증권   |
| `TCSMIH43101` | 장중추가증거금 — 기초자산변동률 부과요건                   | 증권   |
| `TCSMIH43201` | 장중추가증거금 — 위탁·자기별 거래증거금 소요액             | 증권   |
| `TCSMIH43301` | 장중추가증거금 — 부과내역 통보                             | 증권   |
| `TCSMIH43401` | 장중추가증거금 — 해제내역 통보                             | 증권   |
| `TCSMIH43501` | 장중추가증거금 — 위탁·자기별 종목별 포지션 / VWAP          | 증권   |
| `TCSMIH43601` | 장중추가증거금 — 증거금기준가격                            | 증권   |

## 2. Y/N flags

### `EMSG_COMPLT_YN` — 전문완료여부 (all messages, seq 4)

| Code | Meaning             |
| ---- | ------------------- |
| `Y`  | 전송완료 / 전문완료 |
| `N`  | 전송중              |

### `IM_PRC_CHG_BAS_SATISFACT_YN` — 장중추가증거금 가격변동기준 충족여부

Used in TCSMIH41301 (seq 16), TCSMIH43101 (seq 16).

| Code | Meaning                                  |
| ---- | ---------------------------------------- |
| `Y`  | 기초자산 가격변동률 기준 충족            |
| `N`  | 불충족                                   |

## 3. `MRGN_KIND_TP_CD` — 증거금종류구분코드

Used in TCSMIH41301 (seq 8), TCSMIH43101 (seq 8).

| Code | Meaning     | Notes                               |
| ---- | ----------- | ----------------------------------- |
| `1`  | 거래증거금  |                                     |
| `2`  | 위탁증거금  | TCSMIH43101 restricts value to `1`. |

## 4. `TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE` — 위탁자기통합구분코드

Used in TCSMIH42201 (seq 7), TCSMIH42401 (seq 7), TCSMIH43201 (seq 10),
TCSMIH43501 (seq 10).

| Code | Meaning |
| ---- | ------- |
| `10` | 위탁    |
| `20` | 자기    |

## 5. 과부족 구분 (over/short type)

### `OVRES_SHORTS_TYPE_CODE` — TCSMIH42301 seq 11 (거래증거금 과부족)

### `CASHABLE_ASSET_TRADING_MARGIN_OVRES_SHORTS_TYPE_CODE` — TCSMIH42301 seq 15 (현금성자산 과부족)

Shared value set:

| Code | Meaning | Comparison rule (for 현금성자산)                             |
| ---- | ------- | ------------------------------------------------------------ |
| `1`  | 초과    | 소요액 `<` 평가금액                                          |
| `2`  | 부족    | 소요액 `>` 평가금액                                          |
| `3`  | 일치    | 소요액 `=` 평가금액                                          |

## 6. `CLEARING_SETTLEMENT_MARKET_IDENTIFICATION` — 청산결제시장ID

Used in TCSMIH43301 (seq 7), TCSMIH43401 (seq 7).

| Code  | Meaning   |
| ----- | --------- |
| `SPT` | 증권시장  |

> The spec lists only `SPT` in-scope for these messages. If the parser
> encounters another value, log and reject until the code set is
> confirmed.

## 7. External code sets (referenced, not enumerated)

Three fields reference external KRX code registries whose values are
not enumerated inline in the message spec. The parser should store the
raw string value and rely on a sidecar lookup table if a typed resolver
is needed later.

| Field                              | External reference                        | Length |
| ---------------------------------- | ----------------------------------------- | ------ |
| `MARKET_IDENTIFICATION`            | KRX 차세대 상품 ID체계 — 시장ID           | 3      |
| `SECURITIES_GROUP_IDENTIFICATION`  | KRX 차세대 상품 ID체계 — 증권그룹ID       | 2      |
| `UNDERLYING_ASSET_CODE`            | ISIN표준코드 체계의 대상물코드            | 2      |

Sidecar tables (to be added under `krx_parser/codes/`) once reference
data is obtained:

- `market_identification.csv`
- `securities_group_identification.csv`
- `underlying_asset_code.csv`
