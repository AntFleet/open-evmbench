# Audit: 2025-06-panoptic

**Missing access control on execute functions allows unauthorized execution**

- Location: `src/HypoVault.sol` : `executeDeposit`, `executeWithdrawal`
- Mechanism: Both functions lack `onlyManager` (or any other restriction) and only perform the `epoch < currentEpoch` check before reading `queued*` state, performing prorated math, minting/transferring, and moving remainders to `epoch+1`. Anyone can therefore invoke them on arbitrary users/epochs once the manager has called `fulfill*`.
- Impact: An attacker can force execution (or repeated failed attempts) of any user's pending deposit/withdrawal, move remainders across epochs, trigger fee transfers, or interfere with the manager's intended sequencing and accounting of epochs.

**Underflow/DoS in fulfillDeposits when assetsToFulfill exceeds deposited amount**

- Location: `src/HypoVault.sol` : `fulfillDeposits`
- Mechanism: `assetsRemaining = epochState.assetsDeposited - assetsToFulfill` (and the subsequent `DepositEpochState` write) is performed with no upper-bound check on `assetsToFulfill` relative to `epochState.assetsDeposited`.
- Impact: A malicious or compromised manager (or a call with bad calldata) causes an arithmetic underflow revert, permanently blocking fulfillment of that epoch.

**Arbitrary external calls via manager allow theft of vault assets**

- Location: `src/HypoVault.sol` : `manage(address,bytes,uint256)` and the array variant
- Mechanism: `onlyManager` delegates completely to `target.functionCallWithValue(data, value)` with no whitelist, no value/asset limits, and no reentrancy guards. The vault holds `underlyingToken` balances plus any tokens/ETH sent via `requestDeposit` or `manage`.
- Impact: A compromised manager (or owner who set a malicious manager) can drain all tokens, ETH, or call arbitrary contracts (including token approvals/transfers) to steal vault funds.

**Initial totalSupply inflation with zero balances enables incorrect share accounting**

- Location: `src/HypoVault.sol` : constructor + `fulfillDeposits`, `fulfillWithdrawals`, `_mintVirtual`/`_burnVirtual`
- Mechanism: Constructor sets `totalSupply = 1_000_000` while all balances are zero and no corresponding `_mint` occurs. Virtual mint/burn operations and epoch fulfillment math (`sharesReceived = mulDiv(..., _totalSupply, totalAssets)`) treat this inflated supply as real.
- Impact: All share-price calculations, withdrawal proceeds, and performance-fee basis are permanently distorted; early depositors receive an incorrect number of shares relative to assets.

**NAV manipulation via manager-supplied prices within deviation tolerance**

- Location: `src/accountants/PanopticVaultAccountant.sol` : `computeNAV`
- Mechanism: Manager-provided `ManagerPrices` are accepted as long as `|managerPrice - TWAP| <= maxPriceDeviation`; position valuation (`getAmountsForLiquidity`) and conversions then use the manager price (or TWAP derived from it).
- Impact: A manager (or attacker who can supply `managerInput`) can inflate/deflate reported NAV within the configured deviation band, causing incorrect share minting on deposits, excess assets on withdrawals, or incorrect performance fees.
