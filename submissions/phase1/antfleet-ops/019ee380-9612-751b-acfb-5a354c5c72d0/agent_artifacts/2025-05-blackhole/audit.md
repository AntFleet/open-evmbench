# Audit: 2025-05-blackhole

Below are the genuine security vulnerabilities I identified in this codebase.

## Admin can drain unclaimed user rewards via `recoverERC20`
- Location: contracts/BlackClaims.sol : `recoverERC20`
- Mechanism: The function is documented ("Cannot be called to withdraw emissions tokens") to forbid recovering the reward token, but the implementation performs no such check — it only requires `tokenAddress_ != address(0)` and then transfers the contract's entire balance of the supplied token to the owner. After `finalize()` pulls the whole season `reward_amount` of BLACK into this contract, the owner can pass `address(BLACK)` and sweep all of it.
- Impact: A malicious/compromised owner can withdraw every user's unclaimed season rewards (the BLACK token balance) at any time, directly contradicting the stated guarantee and rugging claimants.

## Bribe rewards for auto-voted NFTs are sent to the wrong holder and become unrecoverable
- Location: contracts/Bribes.sol : `getReward` (interaction with AutoVotingEscrow)
- Mechanism: `getReward` computes `_owner = IVotingEscrow(ve).ownerOf(tokenId)` and only redirects to the real user when `_owner == avm`, where `avm = IVotingEscrow(ve).avm()` is the `AutoVotingEscrowManager`. However, `enableAutoVoting` transfers the NFT to a child `AutoVotingEscrow` instance (`votingEscrow.transferFrom(msg.sender, address(target), tokenId)`), not to the manager. So `ownerOf(tokenId)` returns the child contract, the `_owner == avm` branch is never taken, and `IERC20(tokens[i]).safeTransfer(_owner, _reward)` sends rewards to the child `AutoVotingEscrow`, which has no logic to forward ERC20 tokens. (Even if the manager held it, `IAutomatedVotingManager(avm).originalOwner(tokenId)` reads the never-populated `originalOwner` mapping and returns `address(0)`.)
- Impact: A user who enabled auto-voting can pass the `GaugeManager.claimBribes` authorization check (via `getOriginalOwner`) and trigger a claim, but the bribe tokens are irreversibly transferred to the child escrow contract and lost.

## Arbitrary token whitelisting via untrusted `genesisPool` in `depositToken`
- Location: contracts/GenesisPoolManager.sol : `depositToken`
- Mechanism: `depositToken(address genesisPool, uint256 amount)` accepts an arbitrary `genesisPool` address with no validation that it was produced by `genesisFactory`. It calls `IGenesisPool(genesisPool).depositToken(msg.sender, amount)` and, if the return value is `true`, calls `tokenHandler.whitelistToken(IGenesisPool(genesisPool).getGenesisInfo().nativeToken)` and `_preLaunchPool(genesisPool)`. An attacker deploys a fake contract whose `depositToken` returns `true` and whose `getGenesisInfo().nativeToken` returns any address. Because `GenesisPoolManager` holds the `GENESIS_MANAGER` role, `whitelistToken` succeeds.
- Impact: Any external caller can whitelist arbitrary tokens through the privileged `TokenHandler`, bypassing governance. Whitelisting is a trust gate for gauge creation and voting, so this enables creation of gauges around attacker-controlled tokens and downstream emission siphoning.

## Broken zero-address check allows setting `internal_bribe` to address(0)
- Location: contracts/GaugeV2.sol : `setInternalBribe`, and contracts/AlgebraCLVe33/GaugeCL.sol : `setInternalBribe`
- Mechanism: Both guards are written as `require(_int >= address(0), ...)`. An `address` is unsigned, so `_int >= address(0)` is always true; the check is a tautology and never blocks the zero address.
- Impact: The internal bribe (fee sink) can be set to `address(0)`. Subsequent `_claimFees` calls then `safeApprove`/`notifyRewardAmount` against the zero address, causing accrued LP fees to revert (DoS of fee distribution) or be misdirected, depending on path.

## `getAmountsIn` always reverts due to unsigned loop underflow
- Location: contracts/APIHelper/TradeHelper.sol : `getAmountsIn`
- Mechanism: The loop is `for (uint i = routes.length-1; i >= 0; i--)`. Since `i` is an unsigned integer, the condition `i >= 0` is always true; after processing `i == 0`, the `i--` decrement underflows, which reverts under Solidity 0.8 checked arithmetic. The loop can never terminate normally.
- Impact: `getAmountsIn` (and any routing/quoting that depends on it) is permanently unusable — a guaranteed revert/denial of service for reverse-amount quoting.

