# Audit: 2025-04-forte
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

# Merged Security Audit — Float128 / Ln libraries

Inputs: 6 reports total (claude-opus-4-8 shots 1–3; gpt-5.5 shots 1–3). All reports agree these are pure, stateless base-10 floating-point math libraries (no storage, access control, external calls, token/share accounting, or oracles), so all genuine findings fall under arithmetic / type-safety / encoding correctness. 7 distinct findings surfaced across the 6 reports; all 7 are reproduced below.

---

## Consensus findings

## `ln` accepts non-positive (negative and zero) inputs instead of reverting
*(consensus, 6 of 6 reports)*
- Location: `src/Ln.sol` : `ln` / `ln_helper`
- Mechanism: `ln` decodes `mantissa := and(input, MANTISSA_MASK)`, the exponent, and the `MANTISSA_L_FLAG_MASK`, but never reads the sign bit (`MANTISSA_SIGN_MASK`, bit 240) and never rejects a zero mantissa. So `ln(-x)` returns `ln(|x|)`; the `ln(1)=0` fast path even matches the encoding of `-1` (sign ignored), so it claims `ln(-1)=0`; `ln(0)` skips the `==1` guard and runs `ln_helper(0, -8192, …)` on a zero mantissa, returning a garbage finite value. Unlike sibling `sqrt` (reverts on negative) and `div` (reverts on zero), `ln` has no domain guard.
- Impact: A protocol feeding a possibly-negative or zero value (signed PnL, a price/rate difference, a log-return numerator, a ratio that underflowed to zero) into `ln` receives a well-formed but mathematically wrong result instead of a revert, cannot distinguish the error, and propagates the corrupted magnitude into downstream pricing/accounting/risk math.
- Reviewer disagreement: none — all six reports flagged this.

## Unchecked exponent silently wraps the 14-bit packed field
*(consensus, 5 of 6 reports)*
- Location: `src/Float128.sol` : `toPackedFloat`, `mul`, `div`, `add`, `sub`, `sqrt` (final `shl(EXPONENT_BIT, rExp)` / `shl(EXPONENT_BIT, add(exponent, ZERO_OFFSET))` encoding)
- Mechanism: The exponent field is 14 bits (`EXPONENT_BIT = 242`, biased `[0,16383]` → actual `[-8192,+8191]`). No function checks that the computed/encoded exponent stays in range. `toPackedFloat` adds `ZERO_OFFSET` and packs an arbitrary `int` exponent; `mul`/`div` sum operand exponents (the `div` exponent inside an explicit `unchecked` block); `add`/`sub`/`sqrt` write `rExp` directly. An out-of-range value shifts its high bit past bit 255 / wraps modulo `2^14`, silently corrupting the magnitude with no revert. Reported reachable even from documented-range inputs, e.g. `toPackedFloat(1, -8192)` normalizes the mantissa by `1e37`, pushing the exponent to `-8229` and encoding it as a large positive exponent.
- Impact: An attacker controlling operands (or supplying a crafted `packedFloat` / extreme exponent) near the boundary can make tiny values encode as enormous ones (off by ~`10^16384`) or vice versa; any consumer using these floats for balances, prices, limits, interest, liquidation thresholds, or fees then decides on corrupted magnitudes. Practical reachability in typical financial ranges is limited (needs ≈`10^±8191`), but the corruption is silent rather than a revert.
- Reviewer disagreement: opus shot 1 treated `toPackedFloat`/normalization as sound, but only checked mantissa×coefficient products against `2^256` overflow and did not address the exponent range.

## `sqrt(0)` halts the whole call via `stop()` instead of returning `0`
*(consensus, 4 of 6 reports)*
- Location: `src/Float128.sol` : `sqrt` (zero-input branch, `if iszero(a) { stop() }`)
- Mechanism: `sqrt` is `internal` and inlined into its caller. The zero branch executes the EVM `STOP` opcode, which terminates the entire external call with *success* and *empty* return data, committing every state change made before that point, instead of returning `√0 = 0` to the caller. `sqrt(0)` is reachable in normal use, e.g. `a.sub(b).sqrt()` when `a == b`. External wrappers around `sqrt` return malformed empty returndata instead of a 32-byte zero.
- Impact: A caller-controlled zero aborts the transaction as a success, skipping all post-`sqrt` logic (crediting shares, finishing a swap, post-condition checks, lock release, events). Combined with a state-mutating caller (token pull / balance debit before the call), prior writes are committed while the follow-on logic never runs, leaving inconsistent state or stranded funds with no revert to signal failure. Availability bug at minimum; fund-safety bug with a state-mutating caller.
- Reviewer disagreement: none — no report defended the `stop()` branch.

## `eq` / `le` / `ge` return "not equal" for numerically-equal M vs L encodings
*(consensus, 4 of 6 reports)*
- Location: `src/Float128.sol` : `eq`, `le`, `ge`
- Mechanism: A value can be encoded as a 38-digit "M" mantissa or a 72-digit "L" mantissa (different `MANTISSA_L_FLAG_MASK` bit, width, and shifted exponent). `lt`/`gt` renormalize the M operand up to L (`aMan := mul(aMan, BASE_TO_THE_DIGIT_DIFF)`, `aExp := sub(aExp, …DIGIT_DIFF_L_M)`) before comparing and are correct; `eq`/`le`/`ge` do not. `eq` is pure bitwise `unwrap(a)==unwrap(b)`, so the two encodings of one value differ in bits and return `false`. `le`/`ge` detect equality only via the same bitwise early-return; on miss, their bodies copy `lt`/`gt` with strict comparisons, so after renormalization two equal operands give `lt(aMan,bMan)=false` and `le`/`ge` wrongly return `false` at exact equality. Reachable via the library's own API, e.g. `eq/le/ge(divL(3,2), div(3,2))` where both `= 1.5`.
- Impact: Consumers mixing M- and L-precision values get wrong results precisely at the equality boundary: `require(debt.le(collateral))` reverts when `debt == collateral` (DoS at the threshold); `if (price.ge(strike)) settle()` fails to fire when `price == strike`; an `eq`-based "fully repaid / matched / target reached" check reports `false`, locking funds or permitting a bypass/replay.
- Reviewer disagreement: opus shot 2 explicitly defended all four comparison operators (`lt`/`le`/`gt`/`ge`) as correct.

---

## Minority findings

## Subtraction yielding exactly 72 digits loses the L-mantissa flag
*(minority, 1 of 6 reports)* *(conflicting reviews: 2 of 6 reports defended this code path)*
- Location: `src/Float128.sol` : `add` / `sub` — the `if (isSubtraction)` normalization block (the `!((M range)||(L range))` big-norm branch vs. the `else if` L→M down-convert; there is no third branch)
- Mechanism: When a subtraction's normalized magnitude `addition` lands exactly in the L range `[10^71, 10^72)` (72 digits), the first condition `!((M)||(L))` is `false`, so the big-normalization branch — the only place that sets `MANTISSA_L_FLAG_MASK` (bit 241) for subtraction — is skipped. The `else if` only fires when `rExp < 8140` (result exponent `< -52`, down-converting L→M). For result exponent `>= -52` (`rExp >= 8140`) neither branch runs, so `r := or(r, addition)` stores a full 72-digit mantissa without the L flag — an M-typed float carrying an L-sized mantissa. Example: `sub(1.0005e24, 1.0000e24)`, both L-typed → `addition = 5e71`, `rExp = 8141`, L flag unset.
- Impact: Reachable with ordinary inputs. `decode()` still returns the right value (masking the bug), but downstream ops branch on the missing flag: `mul` takes the non-L path and computes `5e71 × up-to-1e38 ≈ 2^364`, silently overflowing `uint256`; `lt`/`gt`/`add` multiply the 72-digit mantissa by `10^34`, overflowing the mantissa field and producing wrong comparisons. A protocol that subtracts two nearby large values and chains further float math gets corrupted numbers (wrong prices, wrong collateral/debt comparisons) with no revert.
- Reviewer disagreement: opus shots 1 and 2 examined `add`/`sub` and reported the two's-complement sign handling and M/L overflow bounds as correct.

## `sqrt` halves a negative exponent with unsigned `div`, setting the L flag on every assembly-path result
*(minority, 1 of 6 reports)*
- Location: `src/Float128.sol` : `sqrt` — assembly (`else`) branch, `aExp := add(div(sub(aExp, ZERO_OFFSET), 2), ZERO_OFFSET)`
- Mechanism: The assembly branch is taken whenever biased `aExp <= 8174` (internal exp `<= -18`), the common case since mantissas normalize to 38 digits (e.g. `4.0` stored as `4e37 × 10^-37`, biased `8155`). `sub(aExp, ZERO_OFFSET)` is then negative (two's complement `2^256 - |v|`), but the code halves it with the **unsigned** `div` instead of `sdiv`: `div(2^256 - |v|, 2) = 2^255 - |v|/2`. After `+ ZERO_OFFSET` and `shl(EXPONENT_BIT, …)`, the spurious `2^255` term lands on bit 241 = `MANTISSA_L_FLAG_MASK`. The numeric exponent comes out right, but the L flag is set on every assembly-path result (a 38-digit M mantissa masquerading as L). The sibling "large" branch uses Solidity signed `/`, confirming signed division was intended.
- Impact: `sqrt` of essentially any value below ~`10^20` returns a malformed `packedFloat`. It `decode()`s correctly, but feeding it back breaks: `mul(sqrt(4.0), sqrt(4.0))` treats `2e37` as a 72-digit L mantissa, computes `div512x256(2e37·2e37, 1e71) ≈ 4e3`, nowhere near `4.0`. Any consumer taking a square root (volatility, AMM invariants, geometric means) then doing further float math gets silently wrong results.
- Reviewer disagreement: none specific — other reports examined `sqrt` for the `stop()` and exponent-wrap issues but did not address the `div`-vs-`sdiv` path.

## Comparators treat non-canonical zero (zero mantissa, nonzero exponent/sign bits) as nonzero
*(minority, 1 of 6 reports)* *(conflicting reviews: 1 of 6 reports defended this code path)*
- Location: `src/Float128.sol` : `lt`, `le`, `gt`, `ge` (raw-word zero/equality checks)
- Mechanism: `packedFloat` is a `uint256` at the ABI boundary, and the comparators assume canonical inputs. They use raw-word zero/equality checks and never validate that a nonzero word actually has a nonzero mantissa. A value with a zero mantissa but nonzero exponent/sign bits is therefore treated as nonzero in the ordering logic, so a crafted non-canonical encoding does not represent the assumed numeric value.
- Impact: A consumer accepting untrusted `packedFloat` values and using these helpers for thresholds, limits, or authorization-relevant numeric checks can be fed crafted encodings (zero mantissa with nonzero exponent/sign) that order incorrectly and take the wrong branch (fail open or closed). Precondition: an exposed path where callers supply raw packed floats without first canonicalizing through `toPackedFloat`.
- Reviewer disagreement: opus shot 2 defended all four comparison operators (`lt`/`le`/`gt`/`ge`) as correct.

