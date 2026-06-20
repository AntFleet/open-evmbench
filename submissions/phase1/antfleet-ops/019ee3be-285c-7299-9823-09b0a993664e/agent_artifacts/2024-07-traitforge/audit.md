# Audit: 2024-07-traitforge

**## Insecure use of tx.origin for token transfer**

- Location: contracts/Airdrop/Airdrop.sol : startAirdrop
- Mechanism: `startAirdrop` performs `traitToken.transferFrom(tx.origin, address(this), amount)` instead of using `msg.sender`. This allows any contract the original EOA has approved to call `startAirdrop` (directly or via proxy) and pull the caller's tokens using the EOA's approval.
- Impact: An attacker can drain approved Trait tokens from any user who interacts with a malicious contract that forwards the call, bypassing normal approval checks.

**## Incorrect reward accounting – totalValue never decreases on claim**

- Location: contracts/Airdrop/Airdrop.sol : claim
- Mechanism: `claim` computes `amount = (totalTokenAmount * userInfo[msg.sender]) / totalValue`, transfers tokens, then only does `userInfo[msg.sender] = 0`. `totalValue` is never reduced. Subsequent claimants therefore divide by an inflated denominator.
- Impact: Later claimants receive strictly less than their proportional share; unclaimed tokens remain permanently stuck in the contract.

**## Division-by-zero / zero-totalValue path reachable**

- Location: contracts/Airdrop/Airdrop.sol : claim
- Mechanism: The only guard is `require(userInfo[msg.sender] > 0)`. Nothing prevents `totalValue` from being zero when that check passes (e.g., via earlier `subUserAmount` calls that reduce it to zero while a user still has a non-zero entry, or race conditions before any adds).
- Impact: Transaction reverts with an arithmetic error (or returns zero), DoS-ing eligible users.

**## No slippage protection on swap (MEV / sandwich attack)**

- Location: contracts/DAOFund/DAOFund.sol : receive
- Mechanism: `swapExactETHForTokens` is called with `amountOutMin = 0` and `block.timestamp` as deadline. Any MEV bot can front-run or back-run the swap.
- Impact: Attacker can force the contract to receive far fewer (or zero) Trait tokens, which are then burned, wasting the ETH sent to the DAO fund.

**## Weak, miner-manipulable entropy source**

- Location: contracts/EntropyGenerator/EntropyGenerator.sol : writeEntropyBatch*, getNextEntropy, getEntropy
- Mechanism: All entropy values are derived from `keccak256(abi.encodePacked(block.number, i))` or `blockhash(block.number-1)` + `block.timestamp`. The special 999999 slot-selection point is also predictable.
- Impact: Miners (or sophisticated callers) can influence or pre-compute token entropy, forge potential, nuke factors, and forger/merger roles, allowing targeted minting or unfair advantage in forging/nuking.

**## Owner can arbitrarily change whitelist root and timing after deployment**

- Location: contracts/TraitForgeNft/TraitForgeNft.sol : setRootHash, setWhitelistEndTime
- Mechanism: Both functions are onlyOwner and can be called at any time, including after the original whitelist period or after users have already minted under the previous root.
- Impact: Owner (or a compromised key) can retroactively whitelist new addresses or extend/re-open the whitelist, minting tokens at the privileged price or bypassing intended distribution.

**## Missing update of totalValue when users are removed before airdrop starts**

- Location: contracts/Airdrop/Airdrop.sol : subUserAmount
- Mechanism: `subUserAmount` decrements both `userInfo[user]` and `totalValue`, but `addUserAmount` only runs while `!started`. If the owner removes users after some have been added, the remaining `totalValue` no longer matches the sum of non-zero `userInfo` entries that will be used in `claim`.
- Impact: Claim calculations become inconsistent; some users receive more or less than intended, or the contract can be left with dust.

**## Reentrancy risk on ETH transfer in receive (DevFund)**

- Location: contracts/DevFund/DevFund.sol : receive
- Mechanism: When `totalDevWeight == 0`, the entire `msg.value` is sent to `owner()` via an unguarded `.call`. No ReentrancyGuard on receive.
- Impact: A malicious owner (or contract that becomes owner) can re-enter receive during the call and manipulate `totalRewardDebt` or cause accounting inconsistencies.

**## Unsafe external call to potentially unset nukeFundAddress**

- Location: contracts/EntityTrading/EntityTrading.sol : transferToNukeFund (and similar in EntityForging.forgeWithListed)
- Mechanism: `nukeFundAddress.call{value: amount}('')` is performed after only an `onlyOwner` setter; no zero-address check at call time.
- Impact: If the owner never sets (or accidentally clears) the address, funds are lost or sent to address(0).

**## Generation counter can be advanced by owner-controlled parameters, breaking economic assumptions**

- Location: contracts/TraitForgeNft/TraitForgeNft.sol : setMaxGeneration, _incrementGeneration
- Mechanism: Owner can raise `maxGeneration` at any time and the internal generation counter advances automatically once `maxTokensPerGen` is reached. No cap on how many times this can occur.
- Impact: Owner can arbitrarily increase total token supply beyond the originally advertised 10 generations, diluting existing holders and nuke-fund economics.
