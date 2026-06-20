# Audit: 2024-03-abracadabra-money

## Unliquidatable bad debt can freeze insolvent positions
- Location: `src/cauldrons/CauldronV4.sol` : `liquidate`
- Mechanism: `liquidate` derives `collateralShare` from the requested `borrowPart` and current exchange rate, but never caps that seizure to `userCollateralShare[user]`. Once a position is deeply underwater, the computed `collateralShare` exceeds the user’s remaining collateral and `userCollateralShare[user].sub(collateralShare)` underflows, reverting the whole liquidation path. There is no fallback branch for bad debt, so the protocol cannot clear severely insolvent accounts.
- Impact: attackers or market moves can leave permanently unliquidatable bad debt in a cauldron, making the market insolvent and pushing losses onto the protocol’s lenders/backing.

## Deflationary tokens can mint unbacked BentoBox shares
- Location: `src/DegenBox.sol` : `deposit`
- Mechanism: `deposit` mints shares and increases `totals[token].elastic` from the requested `amount`, then performs `token.safeTransferFrom(from, address(this), amount)` without checking how many tokens actually arrived. For fee-on-transfer / deflationary tokens, the vault receives less than `amount` but still credits the depositor with full shares. That leaves BentoBox accounting overstated versus real balances, and the deficit is later paid by other depositors or strategy-held funds.
- Impact: if such a token is enabled, an attacker can deposit taxed tokens, receive full-value shares, and later withdraw more value than they actually contributed.

## Deflationary supported tokens can overcredit onboarding balances
- Location: `src/blast/BlastOnboarding.sol` : `deposit`
- Mechanism: `deposit` records `amount` into `totals[token]` and `balances[msg.sender][token]` after `safeTransferFrom`, but never measures the actual token delta received. A fee-on-transfer supported token therefore lets a user obtain larger locked/unlocked balances than the contract really holds. Later `withdraw`, `bootstrap`, and `claim` flows all trust these inflated balances as fully funded.
- Impact: a depositor can drain honest users or distort LP-share distribution by depositing a taxed token and being credited for more than the contract received.

## Broken fee bound check allows permanent >100% fee configuration
- Location: `src/mixins/FeeCollectable.sol` : `setFeeParameters`
- Mechanism: the function checks `if (feeBips > BIPS)` against the old storage value instead of the new `_feeBips`. An authorized fee operator can therefore set `_feeBips` above 10,000 on the first call. After that, the contract becomes stuck because future calls revert on the now-invalid stored `feeBips`, while `calculateFees` can return confiscatory fees or underflow when `feeAmount > amountIn`.
- Impact: in any inheriting contract, an authorized fee operator can brick fee-taking functionality or force users into effectively confiscatory fee behavior.

