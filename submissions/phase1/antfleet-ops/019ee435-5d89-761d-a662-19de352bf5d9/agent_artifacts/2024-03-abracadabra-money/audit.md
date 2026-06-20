# Audit: 2024-03-abracadabra-money

## Cauldron `cook` can skip the solvency check
- Location: `src/cauldrons/CauldronV4.sol` : `cook`
- Mechanism: `cook` sets `status.needsSolvencyCheck = true` after `ACTION_BORROW` and `ACTION_REMOVE_COLLATERAL`, but any later unhandled action falls into `_additionalCookAction`; the base implementation returns a default `CookStatus`, and `cook` assigns `status = returnStatus`. A caller can append an unhandled action such as `ACTION_ACCRUE` (`8`) after borrowing/removing collateral, clearing the pending solvency flag before the final check.
- Impact: An attacker can borrow MIM or remove collateral through `cook` while ending insolvent, draining borrowable MIM from the cauldron.

## Flash-loan fees are left as skimmable surplus
- Location: `src/DegenBox.sol` : `flashLoan`, `batchFlashLoan`, `deposit`
- Mechanism: Flash loans require repayment of `amount + fee`, but the fee is never added to `totals[token].elastic`. The extra tokens remain as unaccounted vault surplus. Since `deposit` intentionally allows `from == address(this)` skimming up to `_tokenBalanceOf(token) - total.elastic`, anyone can mint shares against accumulated flash-loan fees without paying tokens. In `batchFlashLoan`, repeated entries for the same token are also checked per-entry rather than against aggregate fees.
- Impact: Attackers can steal flash-loan fees owed to depositors and can underpay fees in duplicate-token batch flash loans.

## MagicLP TWAP uses the post-manipulation price for the whole elapsed interval
- Location: `src/mimswap/MagicLP.sol` : `_twapUpdate`
- Mechanism: Reserve-changing paths update `_BASE_RESERVE_` / `_QUOTE_RESERVE_` first and then call `_twapUpdate()`. `_twapUpdate()` computes `getMidPrice() * timeElapsed`, so the newly manipulated reserves are treated as if they had existed for the entire elapsed period since the previous update.
- Impact: Any integration using `_BASE_PRICE_CUMULATIVE_LAST_` as a TWAP can be manipulated by a one-block reserve change, allowing attacker-controlled oracle prices and loss-making downstream trades/liquidations.

## Initial LP rounding can break the configured `I` price invariant
- Location: `src/mimswap/MagicLP.sol` : `buyShares`
- Mechanism: On first liquidity, `buyShares` decides whether quote is sufficient using `DecimalMath.mulFloor(baseBalance, _I_)`. Flooring can make an insufficient quote balance appear sufficient, so `shares = baseBalance` is selected and `_QUOTE_TARGET_ = mulFloor(shares, _I_)` is set too low relative to `_BASE_TARGET_`. The pool then starts with targets that do not match the configured `I` ratio.
- Impact: An attacker can initialize a factory-created pool with distorted targets and cause later traders to receive prices materially different from the advertised `I` parameter, extracting value from users.

## Imbalanced pool bootstrap leaves exploitable reserve/target mismatch
- Location: `src/blast/BlastOnboardingBoot.sol` : `bootstrap`
- Mechanism: `bootstrap` sends all locked MIM and USDB into `Router.createPool`, which forwards all amounts to the new MagicLP. `MagicLP.buyShares` mints initial shares from the limiting side but still leaves all transferred tokens in reserves while targets are based only on the limiting amount. If locked MIM and USDB are imbalanced, reserves and targets diverge immediately.
- Impact: After launch, an attacker can trade against the malformed PMM state and extract value from the bootstrapped pool, causing losses to users whose locked deposits funded the pool.

## MagicLP LP oracle is broken and reserve-manipulable
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves`, `latestAnswer`
- Mechanism: The base `_getReserves()` assigns `pair.getReserves()` to local variables but never returns them, so `latestAnswer()` receives `(0, 0)` and returns a zero LP price. The intended virtual hook pattern is also unsafe: when overridden to return real reserves, `latestAnswer()` prices the LP from raw spot reserves without checking the pool’s internal price against the base/quote oracle prices.
- Impact: Deployed directly, the oracle can value LP collateral at zero and brick or corrupt lending markets. With a real reserve-returning override, an attacker can flash-manipulate reserves to inflate LP collateral value and borrow against an overpriced asset.

## Bad debt can become unliquidatable
- Location: `src/cauldrons/CauldronV4.sol` : `liquidate`
- Mechanism: `liquidate` computes `collateralShare` from the requested `borrowPart`, liquidation multiplier, and exchange rate, then subtracts it from `userCollateralShare[user]` without capping it to the user’s available collateral. Deeply underwater positions can require more collateral than the user has, causing an underflow revert unless liquidators manually choose a smaller partial amount.
- Impact: Insolvent accounts can leave residual bad debt that cannot be cleared through the normal liquidation path, pushing losses onto the cauldron/protocol.

## Fee-on-transfer tokens overmint DegenBox shares
- Location: `src/DegenBox.sol` : `deposit`
- Mechanism: `deposit` calculates shares and increments `totals[token].elastic` from the requested `amount`, then calls `safeTransferFrom` without measuring the actual token balance delta. For fee-on-transfer tokens, the vault receives less than `amount` while crediting the depositor with full shares.
- Impact: If such a token is accepted, an attacker can deposit taxed tokens, receive overcredited shares, and withdraw value supplied by other depositors.

## Fee-on-transfer tokens overcredit onboarding balances
- Location: `src/blast/BlastOnboarding.sol` : `deposit`
- Mechanism: `deposit` records the requested `amount` into user and global balances after `safeTransferFrom`, but never checks how many tokens were actually received. A taxed supported token therefore inflates `balances[user][token]` and `totals[token]` relative to real holdings.
- Impact: An attacker can withdraw more than they contributed, or inflate locked balances used by `bootstrap` / `claim`, draining or diluting honest participants if a fee-on-transfer token is supported.

