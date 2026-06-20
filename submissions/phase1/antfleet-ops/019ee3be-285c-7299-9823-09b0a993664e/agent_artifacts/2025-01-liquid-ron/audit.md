# Audit: 2025-01-liquid-ron

**Broken onlyOperator access control**

- Location: src/LiquidRon.sol : onlyOperator (and all functions using it: harvest, harvestAndDelegateRewards, delegateAmount, redelegateAmount, undelegateAmount, finaliseRonRewardsForEpoch)
- Mechanism: The modifier contains the inverted condition `if (msg.sender != owner() || operator[msg.sender]) revert`. This evaluates to true (revert) for every operator and also for the owner once `operator[owner()]` is ever set to true. The intended check (`msg.sender == owner() || operator[msg.sender]`) was never implemented.
- Impact: No operator can ever successfully call any privileged staking/harvest/finalisation function. Only an owner that has never been added as an operator can execute them, completely breaking the intended operator model and allowing denial-of-service of all vault operations that require on-chain maintenance.

**Incorrect fee accounting on delegated rewards**

- Location: src/LiquidRon.sol : harvestAndDelegateRewards (lines calling `harvestAndDelegateRewards` then immediately `operatorFeeAmount += (harvestedAmount * operatorFee) / BIPS`)
- Mechanism: `LiquidProxy.harvestAndDelegateRewards` calls `delegateRewards` on the Ronin validator contract, which moves the rewards directly onto another validator instead of returning them to the proxy/vault. The vault nevertheless records a fee liability in `operatorFeeAmount` even though no RON was ever received.
- Impact: `fetchOperatorFee` can later attempt to withdraw more RON than the contract actually holds, or the fee counter can be inflated indefinitely, leading to accounting insolvency or loss of user funds when the fee recipient drains the vault.

**Missing zero-address and input validation on deployment**

- Location: src/LiquidRon.sol : constructor and deployStakingProxy
- Mechanism: `_roninStaking`, `_wron`, `_feeRecipient` and the newly deployed `LiquidProxy` addresses are never validated. `Escrow` and `LiquidProxy` constructors blindly trust their arguments.
- Impact: A single misconfiguration at deployment permanently bricks the vault (wrong staking target, unapproved WRON, etc.) with no way to recover.

**Reentrancy / state corruption via receive + deposit path**

- Location: src/LiquidRon.sol : receive() and deposit()
- Mechanism: Both paths perform `_depositRONTo(escrow, msg.value)` followed by an external call to `Escrow.deposit`. The `Escrow` constructor already granted infinite approval to the vault, and `LiquidRon.deposit(uint256,address)` (the ERC4626 one) is callable by anyone. No reentrancy guard exists around these flows.
- Impact: An attacker can re-enter during the WRON wrap/transfer sequence and cause the same RON to be processed multiple times, minting extra shares or corrupting the escrow balance.

**Arbitrary user can front-run or block withdrawals via requestWithdrawal**

- Location: src/LiquidRon.sol : requestWithdrawal and finaliseRonRewardsForEpoch
- Mechanism: `requestWithdrawal` lets any caller add shares to `lockedSharesPerEpoch[epoch]` with no limit or rate control. `finaliseRonRewardsForEpoch` then locks the price using the total of all such requests.
- Impact: Griefing attack that forces the operator to finalise an arbitrarily large epoch or prevents legitimate users from ever having their withdrawals processed in a timely manner.
