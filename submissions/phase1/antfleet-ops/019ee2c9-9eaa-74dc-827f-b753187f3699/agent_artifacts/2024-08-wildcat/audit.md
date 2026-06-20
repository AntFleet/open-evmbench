# Audit: 2024-08-wildcat

## Disabled hooks templates remain usable through predeployed instances
- Location: `src/HooksFactory.sol` : `deployMarket` / `_deployMarket`
- Mechanism: Template disablement is only enforced in `_deployHooksInstance`, which blocks creation of new hook instances from a disabled template. `deployMarket` accepts any previously deployed hooks instance by looking up `getHooksTemplateForInstance[hooksInstance]`, loading `_templateDetails[hooksTemplate]`, and then calling `_deployMarket` without ever re-checking `templateDetails.enabled`. As a result, once a borrower has deployed one hooks instance from a template, that instance remains a permanent capability token for creating additional markets even after governance disables the template.
- Impact: A borrower can bypass an emergency template shutdown and keep launching new markets with a template the arch-controller owner explicitly disabled. If a template is disabled because it is vulnerable, misconfigured, or no longer approved, this bug defeats the shutdown and leaves new lenders exposed.

## `nukeFromOrbit` is permissionless instead of sentinel-only
- Location: `src/market/WildcatMarketConfig.sol` : `nukeFromOrbit`
- Mechanism: The sanctions-enforcement entrypoint does not authenticate `msg.sender` against `sentinel`. The function only checks whether the target `accountAddress` is currently sanctioned and then proceeds to call `hooks.onNukeFromOrbit`, queue a full withdrawal, and eventually route funds to escrow. This contradicts the stated interface behavior for `BadLaunchCode` and turns a privileged enforcement action into a public one.
- Impact: Any external account can forcibly eject any sanctioned lender from the market, converting their full position into a queued withdrawal / escrowed balance. An attacker cannot steal the funds directly, but can permanently strip the lender of market exposure and yield, and can front-run any borrower-side override or remediation process.

## Fee-on-transfer / non-standard ERC20 assets break market solvency and payout accounting
- Location: `src/market/WildcatMarket.sol` : `_depositUpTo`; `src/market/WildcatMarketWithdrawals.sol` : `_executeWithdrawal`; also outbound/inbound asset paths such as `collectFees`, `borrow`, and repayment flows
- Mechanism: The market assumes every `asset.safeTransferFrom` and `asset.safeTransfer` moves exactly the nominal `amount`, but it never verifies balance deltas before mutating supply, withdrawal, or fee accounting. On deposit, shares are minted from the requested `amount` even if the token taxes or burns part of the transfer. On withdrawal and fee collection, state is reduced as if the full amount was paid even if the recipient receives less because of transfer fees. The protocol therefore only works safely for strict ERC20s with exact-value transfers, but that requirement is not enforced on-chain.
- Impact: A borrower can launch a market on a transfer-tax token, let lenders mint claims against more assets than the market actually received, and then borrow out the real balance, leaving the market undercollateralized from inception. The same issue can also shortchange withdrawing lenders or fee recipients while the contract marks them as fully paid.

