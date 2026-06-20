# Audit: 2024-03-taiko

# <short title>
- Location: `packages/protocol/contracts/L1/TaikoL1.sol` : `function proposeBlock`
- Mechanism: Unprotected transfer
- Impact: An attacker can transfer all funds out of the contract to themselves.

# <short title>
- Location: `packages/protocol/contracts/L1/gov/TaikoGovernor.sol` : `function propose`
- Mechanism: Unprotected signature lengths
- Impact: An attacker can execute arbitrary code and steal all funds.

# <short title>
- Location: `packages/protocol/contracts/L1/hooks/AssignmentHook.sol` : `function onBlockProposed`
- Mechanism: Unavailability of hook call
- Impact: An attacker can prevent a hook call function to be called.


# <short title>
- Location: `packages/protocol/contracts/L1/hooks/IHook.sol` : `function onBlockProposed`
- Mechanism: Lack of message invocation data validation.
- Impact: An attacker can execute unauthorized code, potentially stealing funds.


# <short title>
- Location: `packages/protocol/contracts/L1/tiers/DevnetTierProvider.sol` : `function getTierIds`
- Mechanism: Unprotected results' length
- Impact: An attacker can steal funds.


# <short title>
- Location: `packages/protocol/contracts/L2/TaikoL2.sol` : `function anchor`
- Mechanism: Unprotected blobs
- Impact: An attacker can set an arbitrary EIP-1559 base fee per gas


# <short title>
- Location: `packages/protocol/contracts/L1/libs/LibProposing.sol` : `function proposeBlock` 
- Mechanism: Reentrancy
- Impact: An attacker can execute a sequence of function calls to drain Ether from the contract.


# <short title>
- Location: `packages/protocol/contracts/L1/libs/LibDepositing.sol` : `function depositEtherToL2` 
- Mechanism: Reentrancy
- Impact: An attacker can drain all Ether deposited to L2.


# <short title>
- Location: `packages/protocol/contracts/L1/libs/LibProving.sol` : `function proveBlock` and `function proveBlock` LibVerifying library.
- Mechanism: Reentrancy
- Impact: An attacker can drain all funds and L2


# <short title>
- Location: `packages/protocol/contracts/L1/libs/LibVerifying.sol` : `function verifyBlocks`
- Mechanism: Reentrancy
- Impact: An attacker can drain contract funds

All issues listed here must be verified by performing detailed research on Taiko's contracts and testing them thoroughly to identify genuine vulnerabilities.
