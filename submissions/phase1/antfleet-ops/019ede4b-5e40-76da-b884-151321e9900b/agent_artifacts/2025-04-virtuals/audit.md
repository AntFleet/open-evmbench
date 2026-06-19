# Audit: 2025-04-virtuals

## Division by Zero in AgentRewardV3 Claim Functions
- Location: `contracts/AgentRewardV3.sol` : `getClaimableStakerRewards` / `getClaimableValidatorRewards`
- Mechanism: The claim functions calculate the final reward by dividing by `agentReward.totalProposals` (e.g., `stakerReward = (stakerReward * uptime) / agentReward.totalProposals;`). If an agent's DAO has 0 proposals at the time the reward epoch is distributed, `totalProposals` is recorded as 0. When a user subsequently attempts to claim their rewards, the division by zero causes the transaction to revert.
- Impact: Permanent Denial of Service (DoS) for all staker and validator reward claims associated with any agent whose DAO had 0 proposals during the reward distribution block, resulting in locked/lost funds.

## ERC20 Invariant Broken in FERC20 (_totalSupply not updated on burn)
- Location: `contracts/fun/FERC20.sol` : `_burn` / `burnFrom`
- Mechanism: The `_burn` and `burnFrom` functions deduct the burned amount from the user's `_balances` mapping but fail to decrement the `_totalSupply` state variable. 
- Impact: The `totalSupply()` function will perpetually return the initial minted supply regardless of how many tokens are burned. This breaks the core ERC20 invariant (`sum(balances) == totalSupply`), which can cause severe pricing errors, incorrect market cap calculations in `Bonding.sol`, and integration failures with external DEXs, bridges, or portfolio trackers that rely on `totalSupply()`.

## Reentrancy and State Manipulation in Bonding.sol buy/sell
- Location: `contracts/fun/Bonding.sol` : `buy` / `sell`
- Mechanism: The `buy` and `sell` functions lack a `nonReentrant` modifier and violate the Checks-Effects-Interactions pattern. They execute external token swaps via the `router` before updating the internal `tokenInfo` state (price, market cap, volume, and liquidity). 
- Impact: An attacker can reenter `buy` or `sell` during the external router call, executing secondary trades with stale price/volume data. This can be exploited to bypass trading limits, manipulate the graduation threshold check (`newReserveA <= gradThreshold`), or corrupt the token's statistical data on the platform.

## Unrestricted Access to `unwrapToken` in Bonding.sol
- Location: `contracts/fun/Bonding.sol` : `unwrapToken`
- Mechanism: The `unwrapToken` function is marked `public` and lacks any access control or validation that the caller is the token owner. It iterates over an arbitrary list of accounts, forcibly burning their `FERC20` balance (bypassing allowance since `Bonding` is the owner of `FERC20`) and transferring the graduated `agentToken` to them.
- Impact: Any malicious user can force-unwrap other users' tokens at any time after graduation. This bypasses user consent, potentially forcing them into unwanted tax events, disrupting their trading strategies, or causing unintended interactions with other protocols that expect the legacy token.

## Division by Zero in AgentRewardV2 Staker Reward Claim
- Location: `contracts/AgentRewardV2.sol` : `_getClaimableStakerRewardsAt`
- Mechanism: The function calculates the staker's share using the formula `((validatorGroupRewards * tokens) / votes)`. If the delegatee has 0 voting power at the `mainReward.blockNumber` (e.g., due to delegation changes or decay), `votes` evaluates to 0, causing a division by zero.
- Impact: If a user delegates to an address with 0 voting power, or if the delegatee's voting power drops to 0 before the snapshot block, attempting to claim staker rewards will revert. This permanently locks the user's rewards for that epoch.
