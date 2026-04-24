# KRX 청산결제 Messages — Field Specifications

Field-level layouts for every message type the parser supports.
Architecture and parsing rules live in [`design.md`](./design.md).
Enumerated code-value sets for fields that reference them live in
[`codes.md`](./codes.md); in the tables below, an English field name
rendered as a link points to the matching section of `codes.md`.

## Conventions

- **Type**:
  - `Long` — fixed-length ASCII integer, left-padded with `'0'`.
  - `String` — fixed-length ASCII/EUC-KR, right-padded with spaces.
  - `Float` — fixed-length ASCII with **implied decimal placement**
    `I.F` (e.g., `18.3` = 18 integer digits + 3 fractional digits).
    The ASCII slice has no decimal point; the parser divides the
    integer value by 10^F to produce a `Decimal`.
- **Len** — byte length of the field.
- **I.F** — implied integer.fractional digit split for `Float` fields.
- **Array** — for messages with repeating groups, the array size and
  total bytes are noted in the message header.
- Fields 1–4 of each **DATA body** are the body-level shared header:
  `MESSAGE_SEQUENCE_NUMBER` (Long, 11),
  [`TRANSACTION_CODE`](./codes.md#1-transaction-codes-tr-codes) (String, 11),
  `TRANSMIT_DATE` (String, 8, YYYYMMDD),
  [`EMSG_COMPLT_YN`](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) (String, 1, Y/N).
  The DATA body is preceded by the 82-byte KMAPv2 frame header (§0).

---

## 0. KMAPv2 frame header (transport envelope)

Every on-wire message is carried inside a `KMAPv2.0` frame: an 82-byte
fixed-width ASCII header followed by a DATA block whose layout is
determined by the TR code (§1 onward). Real log captures (see
`samples/`) show the frame serialised as
`KMAPv2.0<msg_len><msg_type><…><data>` — the parser must peel this
envelope before applying the TR-code schema.

| Seq | Field (KR)                 | Field (EN)                     | Type   | Len | M/O | Notes |
| --- | -------------------------- | ------------------------------ | ------ | --- | --- | ----- |
| 1   | 전문유형                   | MESSAGE_KIND                   | String | 8   | M   | Always `KMAPv2.0`. |
| 2   | 메시지길이                 | MESSAGE_LENGTH                 | Long   | 6   | M   | Byte length of the DATA block (excludes this 82-byte header). Encrypted payloads report the encrypted length. |
| 3   | 메시지 타입                | MESSAGE_TYPE                   | String | 11  | M   | TR code (`TCSMIH…`). Must match seq 2 of the DATA body. |
| 4   | 일련번호                   | SEQUENCE_NUMBER                | Long   | 11  | M   | Transport-level sequence; distinct from the DATA body's `MESSAGE_SEQUENCE_NUMBER` even though samples often agree. |
| 5   | 회원번호                   | MEMBER_NUMBER                  | String | 5   | M   | Originating member. |
| 6   | 연계시도착 회원사 번호     | CONNECT_RECV_MEMBER_NUMBER     | String | 10  | O   | Blank when not routed via a relay. |
| 7   | 회신시송신 회원사 번호     | REPLY_SEND_MEMBER_NUMBER       | String | 10  | O   | Blank on outbound/non-reply traffic. |
| 8   | 전송일시                   | TRANSMIT_DATETIME              | String | 17  | M   | `YYYYMMDDhhmmssSSS` (millisecond precision). Example: `20071221091022328`. |
| 9   | 데이터 건수                | DATA_COUNT                     | Long   | 3   | M   | Number of logical records packed in DATA (typically `001`). |
| 10  | 암호화 유무                | ENCRYPTED_YN                   | String | 1   | M   | `Y` / `N`. When `Y` the DATA block is cipher-text; parsers must decrypt before applying the TR schema. |

Total header length = 8 + 6 + 11 + 11 + 5 + 10 + 10 + 17 + 3 + 1 = **82
bytes**. DATA immediately follows (no separator). A complete on-wire
frame is therefore `82 + MESSAGE_LENGTH` bytes.

Observed in `samples/`: `[KMAPv2.0001200TCSMIH42101…]` (plain-text,
1,200-byte body matching our TCSMIH42101 schema) and
`[KMAPv2.0001624TCSMIH42101…]` (encrypted body, 1,624 bytes after
padding) — the same logical message before and after
`TG_DecryptLOG`.

### DATA block

> **트랜잭션코드(TR CODE)별 메시지 — 업무별로 별도 정의.**

Each TR code defines its own DATA layout in §1 onward.

---

## 1. TCSMIH41301 — 장중추가증거금_기초자산변동률부과요건 (파생시장)

| Seq | Field (KR)                           | Field (EN)                         | Type   | Len   | I.F  | Notes |
| --- | ------------------------------------ | ---------------------------------- | ------ | ----- | ---- | ----- |
| 1   | 메세지일련번호                       | MESSAGE_SEQUENCE_NUMBER            | Long   | 11    |      | |
| 2   | 트랜잭션코드                         | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11    |      | `TCSMIH41301` |
| 3   | 전송일자                             | TRANSMIT_DATE                      | String | 8     |      | `YYYYMMDD` |
| 4   | 전문완료여부                         | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1     |      | `Y`:전문완료, `N`:전송중 |
| 5   | 회차번호                             | RND_NO                             | Long   | 4     |      | 1회차 = 부과용산출 + 해제용산출; not sequential |
| 6   | 회차시각                             | RND_TM                             | String | 9     |      | `HHMMSSsss` |
| 7   | 데이터산출기준시각                   | IM_CALC_BAS_TM                     | String | 9     |      | `HHMMSSsss` |
| 8   | 증거금종류구분코드                   | [MRGN_KIND_TP_CD](./codes.md#3-mrgn_kind_tp_cd--증거금종류구분코드) | String | 1     |      | `1`:거래증거금, `2`:위탁증거금 |
| 9   | 기초자산코드                         | [UNDERLYING_ASSET_CODE](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 2     |      | ISIN 체계의 대상물코드 |
| 10  | 종가                                 | CLSPRC                             | Float  | 11    | 7.3  | 산출기준시각 기초자산 가격 (3 byte unaccounted — see §Issues) |
| 11  | 전일조정종가                         | PREVDD_ADJ_CLSPRC                  | Float  | 18    | 9.8  | 조정 있으면 전일조정종가, 없으면 전일종가 |
| 12  | 가격변동률                           | PRC_CHG_RT                         | Float  | 13    | 6.6  | `|(산출시점 종가 − 전일조정종가)/전일조정종가|`, 단위 % |
| 13  | 가격변동증거금률                     | PRC_CHG_MRGN_RT                    | String | 13    | 6.6  | 거래증거금=거래증거금률 / 위탁증거금=유지증거금률, 단위 % |
| 14  | 가격변동률대비증거금률비율           | PRC_CHG_RT_CMP_MRGN_RT_RTO         | String | 13    | 6.6  | 가격변동률/가격변동증거금률 |
| 15  | 가격변동률대비증거금률기준비율       | PRC_CHG_RT_CMP_MRGN_RT_BAS_RTO     | String | 13    | 6.6  | 기준비율; 비율이 이 값 이상이면 부과요건 만족 |
| 16  | 장중추가증거금가격변동기준충족여부   | [IM_PRC_CHG_BAS_SATISFACT_YN](./codes.md#im_prc_chg_bas_satisfact_yn--장중추가증거금-가격변동기준-충족여부) | String | 1     |      | `Y`:충족, `N`:불충족 |
| 17  | 필러값                               | FILLER_VALUE                       | String | 1,062 |      | Padding |

---

## 2. TCSMIH42101 — 거래증거금_종목별증거금률 (증권시장)

- **Header fields (seq 1–4)**: shared header.
- **Repeating group** (seq 5–9): **16 × 70 bytes = 1,120 bytes**.

| Seq | Field (KR)          | Field (EN)                       | Type   | Len | I.F | Notes |
| --- | ------------------- | -------------------------------- | ------ | --- | --- | ----- |
| 1   | 메세지일련번호      | MESSAGE_SEQUENCE_NUMBER          | Long   | 11  |     | |
| 2   | 트랜잭션코드        | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  |     | `TCSMIH42101` |
| 3   | 전송일자            | TRANSMIT_DATE                    | String | 8   |     | `YYYYMMDD`; 생성일자 = 적용일 (적용일 15시 송신) |
| 4   | 전문완료여부        | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   |     | `Y`:전송완료, `N`:전송중 |
| 5   | 시장ID              | [MARKET_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 3   |     | KRX 차세대 상품 ID체계 |
| 6   | 증권그룹ID          | [SECURITIES_GROUP_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 2   |     | KRX 차세대 상품 ID체계 |
| 7   | 종목코드            | ISSUE_CODE                       | String | 12  |     | |
| 8   | 종목한글약명        | ISU_KOR_ABBRV                    | String | 40  |     | EUC-KR |
| 9   | 거래증거금률        | TRD_MRGN_RT                      | String | 13  | 6.6 | 단위 %; stored numeric but declared String in source |
| 10  | 필러값              | FILLER_VALUE                     | String | 49  |     | Padding |

---

## 3. TCSMIH42201 — 거래증거금_위탁자기별거래증거금소요액 (증권시장)

| Seq | Field (KR)               | Field (EN)                             | Type   | Len   | I.F  | Notes |
| --- | ------------------------ | -------------------------------------- | ------ | ----- | ---- | ----- |
| 1   | 메세지일련번호           | MESSAGE_SEQUENCE_NUMBER                | Long   | 11    |      | |
| 2   | 트랜잭션코드             | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11    |      | `TCSMIH42201` |
| 3   | 전송일자                 | TRANSMIT_DATE                          | String | 8     |      | `YYYYMMDD` |
| 4   | 전문완료여부             | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1     |      | `Y`/`N` |
| 5   | 회원번호                 | MEMBER_NUMBER                          | String | 5     |      | |
| 6   | 거래전문회원번호         | NON_CLEARING_MEMBER_NUMBER             | String | 5     |      | |
| 7   | 위탁자기통합구분코드     | [TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE](./codes.md#4-trust_principal_integration_type_code--위탁자기통합구분코드)  | String | 2     |      | `10`:위탁, `20`:자기 |
| 8   | 거래증거금소요액         | TRADING_MARGIN_REQUIRED_VALUE          | Float  | 22    | 18.3 | 단위 원 |
| 9   | 현금성자산납부소요액     | CASHABLE_ASSET_PAY_REQUIRED_VALUE      | Float  | 22    | 18.3 | 소요액 × (1 − 비현금성자산 납입한도비율) |
| 10  | 필러값                   | FILLER_VALUE                           | String | 1,113 |      | Padding |

---

## 4. TCSMIH42301 — 거래증거금과부족내역통보 (증권시장)

| Seq | Field (KR)                             | Field (EN)                                              | Type   | Len | I.F  | Notes |
| --- | -------------------------------------- | ------------------------------------------------------- | ------ | --- | ---- | ----- |
| 1   | 메세지일련번호                         | MESSAGE_SEQUENCE_NUMBER                                 | Long   | 11  |      | |
| 2   | 트랜잭션코드                           | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  |      | `TCSMIH42301` |
| 3   | 전송일자                               | TRANSMIT_DATE                                           | String | 8   |      | `YYYYMMDD` |
| 4   | 전문완료여부                           | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   |      | `Y`/`N` |
| 5   | 회원번호                               | MEMBER_NUMBER                                           | String | 5   |      | |
| 6   | 전전일거래증거금소요액                 | BEFORE_PREVIOUS_DAY_TRADING_MARGIN_REQUIRED_VALUE       | Float  | 22  | 18.3 | 단위 원; T−2 거래분 |
| 7   | 전일거래증거금소요액                   | PREVDD_TRADING_MARGIN_REQUIRED_VALUE                    | Float  | 22  | 18.3 | 단위 원; T−1 거래분 |
| 8   | 거래증거금소요액                       | TRADING_MARGIN_REQUIRED_VALUE                           | Float  | 22  | 18.3 | 단위 원; T−1 + T−2 |
| 9   | 인출제한금액                           | WITHDRAWAL_LIMIT_AMOUNT                                 | Float  | 22  | 18.3 | 단위 원; 08:00 시점 |
| 10  | 거래증거금평가금액                     | TRADING_MARGIN_VALUATION                                | Float  | 22  | 18.3 | 단위 원 |
| 11  | 과부족구분코드                         | [OVRES_SHORTS_TYPE_CODE](./codes.md#ovres_shorts_type_code--tcsmih42301-seq-11-거래증거금-과부족) | String | 1   |      | `1`:초과, `2`:부족, `3`:일치 |
| 12  | 거래증거금과부족금액                   | TRADING_MARGIN_VALUATION_AMOUNT                         | Float  | 22  | 18.3 | 단위 원 |
| 13  | 현금성자산거래증거금소요액             | CASHABLE_ASSET_TRADING_MARGIN_REQUIRED_VALUE            | Float  | 22  | 18.3 | 소요액 × (1 − 비현금성자산 납입한도비율) |
| 14  | 현금성자산거래증거금평가금액           | CASHABLE_ASSET_TRADING_MARGIN_VALUATION                 | Float  | 22  | 18.3 | 현금 + 외화/국채/특수채/지방채/외화증권 |
| 15  | 현금성자산과부족구분코드               | [CASHABLE_ASSET_TRADING_MARGIN_OVRES_SHORTS_TYPE_CODE](./codes.md#cashable_asset_trading_margin_ovres_shorts_type_code--tcsmih42301-seq-15-현금성자산-과부족) | String | 1   |      | 소요액 vs 평가금액 비교 (`1`/`2`/`3`) |
| 16  | 현금성자산거래증거금과부족금액         | CASHABLE_ASSET_TRADING_MARGIN_VALUATION_AMOUNT          | Float  | 22  | 18.3 | 단위 원 |
| 17  | 필러값                                 | FILLER_VALUE                                            | String | 964 |      | Padding |

---

## 5. TCSMIH42401 — 거래증거금_위탁자기별종목별거래량가중평균가격 (증권시장)

- **Repeating group** (seq 7–11): **30 × 29 bytes = 870 bytes**.

| Seq | Field (KR)               | Field (EN)                            | Type   | Len | Notes |
| --- | ------------------------ | ------------------------------------- | ------ | --- | ----- |
| 1   | 메세지일련번호           | MESSAGE_SEQUENCE_NUMBER               | Long   | 11  | |
| 2   | 트랜잭션코드             | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  | `TCSMIH42401` |
| 3   | 전송일자                 | TRANSMIT_DATE                         | String | 8   | `YYYYMMDD` |
| 4   | 전문완료여부             | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   | `Y`/`N` |
| 5   | 회원번호                 | MEMBER_NUMBER                         | String | 5   | |
| 6   | 거래전문회원번호         | NON_CLEARING_MEMBER_NUMBER            | String | 5   | |
| 7   | 위탁자기통합구분코드     | [TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE](./codes.md#4-trust_principal_integration_type_code--위탁자기통합구분코드) | String | 2   | `10`:위탁, `20`:자기 |
| 8   | 시장ID                   | [MARKET_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 3   | |
| 9   | 증권그룹ID               | [SECURITIES_GROUP_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 2   | KRX 차세대 상품 ID체계 |
| 10  | 종목코드                 | ISSUE_CODE                            | String | 12  | |
| 11  | 거래량가중평균가격       | TRADING_VOLUME_WEIGHTED_AVERAGE_PRICE | Long   | 10  | |
| 12  | 필러값                   | FILLER_VALUE                          | String | 289 | Padding |

---

## 6. TCSMIH43101 — 장중추가증거금_기초자산변동률부과요건 (증권시장)

Same field layout as **TCSMIH41301** (§1) but for equity market, with
one content difference:

- Seq 8 [`MRGN_KIND_TP_CD`](./codes.md#3-mrgn_kind_tp_cd--증거금종류구분코드) is restricted to `1`:거래증거금 (no 위탁).
- Seq 13 `PRC_CHG_MRGN_RT` note is simply 거래증거금률 (no 유지증거금률 branch).
- Trailing filler seq 17 `FILLER_VALUE` remains 1,062 bytes.

---

## 7. TCSMIH43201 — 장중추가증거금_위탁자기별거래증거금소요액 (증권시장)

| Seq | Field (KR)               | Field (EN)                             | Type   | Len   | I.F  | Notes |
| --- | ------------------------ | -------------------------------------- | ------ | ----- | ---- | ----- |
| 1   | 메세지일련번호           | MESSAGE_SEQUENCE_NUMBER                | Long   | 11    |      | |
| 2   | 트랜잭션코드             | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11    |      | `TCSMIH43201` |
| 3   | 전송일자                 | TRANSMIT_DATE                          | String | 8     |      | `YYYYMMDD` |
| 4   | 전문완료여부             | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1     |      | `Y`/`N` |
| 5   | 회차번호                 | RND_NO                                 | Long   | 4     |      | not sequential |
| 6   | 회차시각                 | RND_TM                                 | String | 9     |      | `HHMMSSsss` |
| 7   | 데이터산출기준시각       | IM_CALC_BAS_TM                         | String | 9     |      | `HHMMSSsss` |
| 8   | 회원번호                 | MEMBER_NUMBER                          | String | 5     |      | |
| 9   | 거래전문회원번호         | NON_CLEARING_MEMBER_NUMBER             | String | 5     |      | |
| 10  | 위탁자기통합구분코드     | [TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE](./codes.md#4-trust_principal_integration_type_code--위탁자기통합구분코드)  | String | 2     |      | `10`:위탁, `20`:자기 |
| 11  | 거래증거금소요액         | TRADING_MARGIN_REQUIRED_VALUE          | Float  | 22    | 18.3 | 단위 원 |
| 12  | 필러값                   | FILLER_VALUE                           | String | 1,113 |      | Padding |

---

## 8. TCSMIH43301 — 장중추가증거금_부과내역통보 (증권시장)

| Seq | Field (KR)                                 | Field (EN)                         | Type   | Len | I.F  | Notes |
| --- | ------------------------------------------ | ---------------------------------- | ------ | --- | ---- | ----- |
| 1   | 메세지일련번호                             | MESSAGE_SEQUENCE_NUMBER            | Long   | 11  |      | |
| 2   | 트랜잭션코드                               | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  |      | `TCSMIH43301` |
| 3   | 전송일자                                   | TRANSMIT_DATE                      | String | 8   |      | `YYYYMMDD` |
| 4   | 전문완료여부                               | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   |      | `Y`/`N` |
| 5   | 회차번호                                   | RND_NO                             | Long   | 4   |      | not sequential |
| 6   | 회차시각                                   | RND_TM                             | String | 9   |      | `HHMMSSsss` |
| 7   | 청산결제시장ID                             | [CLEARING_SETTLEMENT_MARKET_IDENTIFICATION](./codes.md#6-clearing_settlement_market_identification--청산결제시장id) | String | 3 |      | `SPT`:증권시장 |
| 8   | 회원번호                                   | MEMBER_NUMBER                      | String | 5   |      | |
| 9   | 위탁순위험증거금                           | TRST_NET_RISK_MRGN                 | Float  | 23  | 19.3 | |
| 10  | 위탁변동증거금                             | TRST_VARI_MRGN                     | Float  | 23  | 19.3 | |
| 11  | 위탁필요액                                 | TRST_REQVAL                        | Float  | 28  | 24.3 | 위탁거래증거금 소요액; `≤ 0` |
| 12  | 자기순위험증거금                           | PRINC_NET_RISK_MRGN                | Float  | 23  | 19.3 | |
| 13  | 자기변동증거금                             | PRINC_VARI_MRGN                    | Float  | 23  | 19.3 | |
| 14  | 자기필요액                                 | PRINC_REQVAL                       | Float  | 28  | 24.3 | 자기거래증거금 소요액; `≤ 0` |
| 15  | 필요액합계                                 | REQVAL_AGG                         | Float  | 28  | 24.3 | 위탁 + 자기; `≤ 0`; 단위 원 |
| 16  | 부과산출기준시각(T시)                      | IMPOST_BAS_TM                      | String | 9   |      | `HHMMSSsss` |
| 17  | 부과산출기준시각_총예탁금액                | IMPOST_BAS_TM_TOT_DEPO_AMT         | Float  | 22  | 18.3 | 단위 원 |
| 18  | 예탁액대비장중추가증거금필요액비율         | DEPO_VAL_CMP_IM_REQVAL_RTO         | Float  | 10  | 7.2  | 필요액합계/총예탁금액; 단위 %; 0의 자리에서 절사 |
| 19  | 부과기준시각(T+1시)                        | IMPOST_BAS_TM (T+1)                | String | 9   |      | `HHMMSSsss` (KR notes same EN name — disambiguate in schema) |
| 20  | 부과기준시각_총예탁금액                    | IMPOST_BAS_TM_TOT_DEPO_AMT (T+1)   | Float  | 22  | 18.3 | 단위 원 |
| 21  | 장중추가증거금                             | IM                                 | Float  | 22  | 18.3 | 납부 대상 금액; 필요액합계(T) + 예탁금액(T+1) < 0 |
| 22  | 확정시각                                   | FINAL_TM                           | String | 9   |      | `HHMMSSsss` 부과확정시각 |
| 23  | 납부시한                                   | PAY_DEADLINE                       | String | 9   |      | `HHMMSSsss` 확정시각 + 2시간 |
| 24  | 필러값                                     | FILLER_VALUE                       | String | 860 |      | Padding |

> **Note** — source spec names both seq 16 and seq 19 `IMPOST_BAS_TM` and
> both seq 17/20 `IMPOST_BAS_TM_TOT_DEPO_AMT`. In the parser schema
> disambiguate as `_T` / `_T_PLUS_1` suffixes.

---

## 9. TCSMIH43401 — 장중추가증거금_해제내역통보 (증권시장)

| Seq | Field (KR)                                         | Field (EN)                                 | Type   | Len | I.F  | Notes |
| --- | -------------------------------------------------- | ------------------------------------------ | ------ | --- | ---- | ----- |
| 1   | 메세지일련번호                                     | MESSAGE_SEQUENCE_NUMBER                    | Long   | 11  |      | |
| 2   | 트랜잭션코드                                       | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  |      | `TCSMIH43401` |
| 3   | 전송일자                                           | TRANSMIT_DATE                              | String | 8   |      | `YYYYMMDD` |
| 4   | 전문완료여부                                       | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   |      | `Y`/`N` |
| 5   | 회차번호                                           | RND_NO                                     | Long   | 4   |      | not sequential |
| 6   | 회차시각                                           | RND_TM                                     | String | 9   |      | `HHMMSSsss` |
| 7   | 청산결제시장ID                                     | [CLEARING_SETTLEMENT_MARKET_IDENTIFICATION](./codes.md#6-clearing_settlement_market_identification--청산결제시장id)  | String | 3   |      | `SPT`:증권시장 |
| 8   | 회원번호                                           | MEMBER_NUMBER                              | String | 5   |      | |
| 9   | 위탁순위험증거금(T+1.5시)                          | TRST_NET_RISK_MRGN                         | Float  | 23  | 19.3 | |
| 10  | 위탁변동증거금(T+1.5시)                            | TRST_VARI_MRGN                             | Float  | 23  | 19.3 | |
| 11  | 위탁필요액(T+1.5시)                                | TRST_REQVAL                                | Float  | 28  | 24.3 | `≤ 0` |
| 12  | 자기순위험증거금(T+1.5시)                          | PRINC_NET_RISK_MRGN                        | Float  | 23  | 19.3 | |
| 13  | 자기변동증거금(T+1.5시)                            | PRINC_VARI_MRGN                            | Float  | 23  | 19.3 | |
| 14  | 자기필요액(T+1.5시)                                | PRINC_REQVAL                               | Float  | 28  | 24.3 | `≤ 0` |
| 15  | 필요액합계(T+1.5시)                                | REQVAL_AGG                                 | Float  | 28  | 24.3 | `≤ 0`; 단위 원 |
| 16  | 해제기준시각(T+2시)                                | RELEAS_BAS_TM                              | String | 9   |      | `HHMMSSsss` |
| 17  | 해제기준시각_총예탁금액(T+2시)                     | RELEAS_BAS_TM_TOT_DEPO_AMT                 | Float  | 22  | 18.3 | 단위 원 |
| 18  | 예탁액대비장중추가증거금필요액비율(T+2시)          | DEPO_VAL_CMP_IM_REQVAL_RTO                 | Float  | 10  | 7.2  | 단위 %; 0의 자리에서 절사 |
| 19  | 확정시각                                           | FINAL_TM                                   | String | 9   |      | `HHMMSSsss` 해제확정시각 |
| 20  | 필러값                                             | FILLER_VALUE                               | String | 922 |      | Padding |

---

## 10. TCSMIH43501 — 장중추가증거금_위탁자기별종목별포지션/VWAP (증권시장)

- **Repeating group** (seq 10–14, per §Issues): **20 × 53 bytes = 1,060 bytes**.
  The source spec reuses seq numbers 12/13 for two different fields
  — below we treat them in insertion order and renumber the second
  occurrences as seq 14/15 in the schema YAML.

| Seq | Field (KR)                 | Field (EN)                             | Type   | Len | Notes |
| --- | -------------------------- | -------------------------------------- | ------ | --- | ----- |
| 1   | 메세지일련번호             | MESSAGE_SEQUENCE_NUMBER                | Long   | 11  | |
| 2   | 트랜잭션코드               | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  | `TCSMIH43501` |
| 3   | 전송일자                   | TRANSMIT_DATE                          | String | 8   | `YYYYMMDD` |
| 4   | 전문완료여부               | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   | `Y`/`N` |
| 5   | 회차번호                   | ROUND_NUMBER                           | Long   | 4   | |
| 6   | 회차시각                   | ROUND_TIME                             | String | 9   | `HHMMSSsss` |
| 7   | 데이터산출기준시각         | CALCULATE_BASE_TIME                    | String | 9   | `HHMMSSsss` |
| 8   | 회원번호                   | MEMBER_NUMBER                          | String | 5   | |
| 9   | 거래전문회원번호           | NON_CLEARING_MEMBER_NUMBER             | String | 5   | |
| 10  | 위탁자기통합구분코드       | [TRUST_PRINCIPAL_INTEGRATION_TYPE_CODE](./codes.md#4-trust_principal_integration_type_code--위탁자기통합구분코드)  | String | 2   | `10`:위탁, `20`:자기 |
| 11  | 시장ID                     | [MARKET_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 3   | |
| 12  | 증권그룹ID                 | [SECURITIES_GROUP_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 2   | KRX 차세대 상품 ID체계 |
| 13  | 종목코드                   | ISSUE_CODE                             | String | 12  | |
| 14  | 매도체결수량               | ASK_TRADING_VOLUME                     | Long   | 12  | 당일 체결분; 거래정정 미반영 |
| 15  | 매수체결수량               | BID_TRADING_VOLUME                     | Long   | 12  | 당일 체결분; 거래정정 미반영 |
| 16  | 거래량가중평균가격         | TRADING_VOLUME_WEIGHTED_AVERAGE_PRICE  | Long   | 10  | |
| 17  | 필러값                     | FILLER_VALUE                           | String | 77  | Padding |

> **Issue** — the source annotates "20개 배열 (1060 Bytes)" on seq 10.
> Sum of per-record bytes (seq 10–16) = 2+3+2+12+12+12+10 = 53;
> 53 × 20 = 1,060 → matches. Confirmed interpretation.

---

## 11. TCSMIH43601 — 장중추가증거금_증거금기준가격 (증권시장)

- **Repeating group** (seq 8–11 below): **30 × 35 bytes = 1,050 bytes**.
- **Source typo** — seq 2 `TRANSACTION_CODE` value is written as
  `TCSMIH43501` in the source spec; the correct literal for this
  message is `TCSMIH43601`. Flag for confirmation.
- Source skips seq numbers 8, 9, 10 (goes 7 → 11). Below we renumber
  contiguously.

| Seq | Field (KR)                 | Field (EN)                           | Type   | Len | I.F  | Notes |
| --- | -------------------------- | ------------------------------------ | ------ | --- | ---- | ----- |
| 1   | 메세지일련번호             | MESSAGE_SEQUENCE_NUMBER              | Long   | 11  |      | |
| 2   | 트랜잭션코드               | [TRANSACTION_CODE](./codes.md#1-transaction-codes-tr-codes) | String | 11  |      | `TCSMIH43601` (see typo note) |
| 3   | 전송일자                   | TRANSMIT_DATE                        | String | 8   |      | `YYYYMMDD` |
| 4   | 전문완료여부               | [EMSG_COMPLT_YN](./codes.md#emsg_complt_yn--전문완료여부-all-messages-seq-4) | String | 1   |      | `Y`/`N` |
| 5   | 회차번호                   | ROUND_NUMBER                         | Long   | 4   |      | |
| 6   | 회차시각                   | ROUND_TIME                           | String | 9   |      | `HHMMSSsss` |
| 7   | 데이터산출기준시각         | CALCULATE_BASE_TIME                  | String | 9   |      | `HHMMSSsss` |
| 8   | 시장ID                     | [MARKET_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 3   |      | |
| 9   | 증권그룹ID                 | [SECURITIES_GROUP_IDENTIFICATION](./codes.md#7-external-code-sets-referenced-not-enumerated) | String | 2   |      | KRX 차세대 상품 ID체계 |
| 10  | 종목코드                   | ISSUE_CODE                           | String | 12  |      | |
| 11  | 증거금기준가격             | MARGIN_BASE_PRICE                    | Float  | 18  | 9.8  | |
| 12  | 필러값                     | FILLER_VALUE                         | String | 97  |      | Padding |

---

## 12. Known Issues / Follow-ups

1. **TCSMIH41301 seq 10 `CLSPRC` byte count** — declared `Float`
   length 11 with decimal split `7.3`. 7+3=10, leaving 1 byte
   unaccounted (possibly a sign byte or unused pad). Confirm with
   live sample.
2. **TCSMIH43601 seq 2** — source prints `TCSMIH43501` as the
   literal; almost certainly a typo for `TCSMIH43601`.
3. **TCSMIH43501 seq 12/13** — source reuses seq 12 and 13 for two
   different sets of fields; renumber as described in §10.
4. **TCSMIH43301 seq 16/19 and seq 17/20** — same EN field name used
   for T and T+1 instants; disambiguate with `_T` / `_T_PLUS_1`
   suffixes in the schema YAML.
5. **TCSMIH42101 seq 9 `TRD_MRGN_RT`** — source declares type `String`
   but the format `6.6` and 단위 % indicate a numeric value. Parse as
   `Decimal` using `I.F` = `6.6`; preserve raw string if parse fails.
6. **Text encoding** — EUC-KR assumed for Korean fields (e.g.,
   `ISU_KOR_ABBRV`); confirm against a live file before freezing.
7. **Record terminator** — unknown (fixed-length back-to-back, newline,
   or length-prefixed). Determine from sample files.
