# Audit: 2024-03-abracadabra-money

 ## CauldronV4 `cook` allows draining leftover ETH
- Location: `src/cauldrons/CauldronV4.sol` : `cook`, `_call`
- Mechanism: `cook` is `payable` and forwards `values[i]` ETH for each action (e.g., `ACTION_CALL` and `ACTION_BENTO_DEPOSIT`), but it never checks that `sum(values[i]) == msg.value` and never refunds unused ETH. Any ETH that remains in the Cauldron contract—whether from overpaying a `ACTION_BENTO_DEPOSIT` or any other source—can be withdrawn by a later caller via an `ACTION_CALL` with `values[i] == address(this).balance`.
- Impact: Any ETH held by the Cauldron can be stolen by anyone.

## MagicLpAggregator reports a broken price because reserves are not returned
- Location: `src/oracles/aggregators/MagicLpAggregator.sol` : `_getReserves`, `latestAnswer`
- Mechanism: `_getReserves` assigns local variables `baseReserve` and `quoteReserve` but its return parameters are unnamed and the function never executes a `return`, so it effectively returns `(0,0)`. `latestAnswer` then computes `minAnswer * (baseReserve + quoteReserve) / pair.totalSupply()` using zero reserves. Additionally, `latestAnswer` casts `baseOracle.latestAnswer()` and `quoteOracle.latestAnswer()` to `uint256` without validating they are positive, so a negative oracle response would produce an enormous price.
- Impact: Any Cauldron or other consumer using this oracle will receive a zero or otherwise incorrect price, leading to improper liquidations, borrows, or collateral valuations.

## LockingMultiRewards owner can recover all reward tokens
- Location: `src/staking/LockingMultiRewards.sol` : `recover`
- Mechanism: `recover` restricts only the staking token (and only to the excess above `stakingTokenBalance`). For every other token, including reward tokens currently being distributed, the owner can transfer the full balance out without any restriction.
- Impact: A malicious or compromised owner can rug pull all unclaimed rewards, leaving stakers unable to receive them.

## MagicLP owner can drain pool reserves through `setParameters`
- Location: `src/mimswap/MagicLP.sol` : `setParameters`
- Mechanism: `setParameters` accepts arbitrary `baseOutAmount` and `quoteOutAmount` chosen by the owner and transfers them out of the pool before resetting reserves and targets. There is no validation that these amounts correspond only to excess/donated tokens or that they leave the pool solvent.
- Impact: A malicious owner can remove all base and quote tokens from the pool, draining all LPs.

## BlastGovernor owner has arbitrary execution power
- Location: `src/blast/BlastGovernor.sol` : `execute`
- Mechanism: `execute` lets the owner call any address with arbitrary calldata and ETH. Because BlastGovernor is configured as the Blast governor for protocol contracts, this also allows the owner to reconfigure yield modes, governors, and claim yields for those contracts.
- Impact: A malicious owner can drain ETH/gas/yield and reconfigure Blast settings for all governed contracts.
