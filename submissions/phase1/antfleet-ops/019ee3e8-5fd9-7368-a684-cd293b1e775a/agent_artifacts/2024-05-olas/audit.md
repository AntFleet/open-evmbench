# Audit: 2024-05-olas

## <GovernorOLA : Reentrancy inqueue>
- Location: `governance/audits/internal/analysis/contracts/GovernorOLA-flatten.sol` : `function propose`
- Mechanism: The `GovernorCompatibilityBravo` module uses `IGovernorCompatibilityBravo` which extends the `Governor` to add Compound-like functionality by changing the voting and execution logic.
- Impact: An attacker can manipulate the governance process by submitting a proposal, allowing someone to call the `uzzi` function, and re-entering the `queueOrExecute` logic in `GovernorTimelockControl`, potentially draining the contract.

## <buOLA : Unprotected burn>
- Location: `governance/audits/internal/analysis/contracts/buOLA-flatten.sol` : `function burn`
- Mechanism: `buOLA` contract stores `OLA` tokens for `buOLA` token burns. An attacker can burn its tokens to attack `buOLA`.
- Impact: An attacker can drain the contract by triggering a burn on the contract.

## <VotingEscrow : Unprotected release mechanisms>
- Location: `governance/audits/internal/analysis/contracts/VotingEscrow-flatten.sol` : `function createLock`, `function increaseAmount`, `function increaseUnlockTime`, `function withdraw`
- Mechanism: An attacker can create a lock for a user and manipulate the user's unlock time, increasing the release amount.
- Impact: An attacker can drain the contract of `OLA` tokens.

## <GuardCM : Unauthorized multisig transactions>
- Location: `governance/audits/internal10/analysis/contracts/GuardCM-flatten.sol` : `function checkTransaction`
- Mechanism: An attacker can bypass the timelock and multisig checks by manipulating the transaction hash and nonces.
- Impact: An attacker can execute unauthorized multisig transactions, potentially draining the contract.
