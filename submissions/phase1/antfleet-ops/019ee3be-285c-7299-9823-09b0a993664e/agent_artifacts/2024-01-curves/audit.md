# Audit: 2024-01-curves

**Broken access control modifiers allow unauthorized execution of privileged functions**

- Location: contracts/Security.sol : onlyOwner, onlyManager
- Mechanism: The `onlyOwner` modifier executes `msg.sender == owner;` (a no-op expression) then unconditionally continues to `_`; `onlyManager` does the same with `managers[msg.sender] == true;`. No `require`, `if` + revert, or assertion enforces the condition. All call sites (`setFeeRedistributor`, `setProtocolFeePercent`, `setExternalFeePercent`, `setMaxFeePercent`, `setERC20Factory`, `setManager`, `transferOwnership`, `addFees`, `onBalanceChange`, etc.) therefore execute for any caller.
- Impact: An attacker can arbitrarily change fee percentages/destinations, replace the FeeSplitter or ERC20 factory, add/remove managers, transfer ownership, inject fees, or manipulate holder accounting, fully compromising the protocol's economic controls and token minting.

**Missing access control on FeeSplitter.setCurves**

- Location: contracts/FeeSplitter.sol : setCurves
- Mechanism: The function is declared `public` with no `onlyOwner`/`onlyManager` modifier (or any other guard) and directly overwrites the `curves` storage variable used by every balance/supply/fee calculation.
- Impact: An attacker can point FeeSplitter at a malicious Curves contract (or a contract that returns attacker-controlled balances), allowing theft of accumulated holder fees via `claimFees`/`batchClaiming` or permanent denial of fee distribution.

**Reentrancy via external calls in fee distribution before state finalization in some paths**

- Location: contracts/Curves.sol : _transferFees (called from _buyCurvesToken, sellCurvesToken, buyCurvesTokenWithName, buyCurvesTokenForPresale, buyCurvesTokenWhitelisted)
- Mechanism: After updating `curvesTokenBalance`/`curvesTokenSupply` in the caller, `_transferFees` performs three `.call{value:...}("")` transfers to `protocolFeeDestination`, `curvesTokenSubject`, and `referralFeeDestination[curvesTokenSubject]` (plus `feeRedistributor.addFees`) before the outer function returns. These destinations are fully attacker-controlled.
- Impact: A malicious destination can re-enter `buyCurvesToken*` or `sellCurvesToken` (or `transfer*`) while the supply/balance updates are only partially visible to other state variables such as `ownedCurvesTokenSubjects` or presale accounting, enabling double-spend of tokens or bypassing `LastTokenCannotBeSold` / `ExceededMaxBuyAmount` checks.

**Presale whitelist bypass and double-buy via missing proof consumption**

- Location: contracts/Curves.sol : buyCurvesTokenWhitelisted
- Mechanism: `presalesBuys[curvesTokenSubject][msg.sender] += amount` and the `maxBuy` check occur before `verifyMerkle` (which only reads the root). The same `proof` can be reused by the same address on subsequent calls, and nothing marks a leaf as used.
- Impact: An attacker on the Merkle tree can buy more than `maxBuy` tokens during the presale window (or any address can front-run and buy before the legitimate whitelisted buyer), violating the intended presale cap and allowing early accumulation of discounted supply.

**Integer division / rounding in fee and price calculations allows precision griefing**

- Location: contracts/Curves.sol : getFees, getPrice (and all buy/sell price helpers)
- Mechanism: All fee calculations perform `(price * percent) / 1 ether` and the bonding-curve summation uses integer division by 16000 with no rounding-up or accumulated dust handling; `getSellPriceAfterFee` subtracts fees after the price is computed.
- Impact: An attacker can repeatedly buy/sell tiny amounts to force rounding losses onto the protocol fee destinations or holders, or (combined with the broken access control) set fee percentages that deliberately create dust that can never be claimed.

**ERC20 mint/burn authorization tied to a mutable external contract reference**

- Location: contracts/Curves.sol : withdraw, deposit, sellExternalCurvesToken (and _deployERC20)
- Mechanism: `externalCurvesTokens[curvesTokenSubject].token` is written by `_deployERC20` (called from several paths) and the Curves contract itself is the `owner` of the deployed CurvesERC20; any caller that can reach `_mint`/`_burn` via the Curves contract can therefore mint arbitrary ERC20 amounts.
- Impact: Combined with the broken `onlyOwner`/`onlyManager` modifiers or a malicious factory, an attacker can mint unlimited wrapped ERC20 tokens or drain the CurvesERC20 contract's minting power, breaking the 1:1 Curves-token ↔ ERC20 invariant.
