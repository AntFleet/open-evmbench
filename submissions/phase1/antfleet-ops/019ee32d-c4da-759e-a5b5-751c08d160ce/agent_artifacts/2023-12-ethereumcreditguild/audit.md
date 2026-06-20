# Audit: 2023-12-ethereumcreditguild


An audit of the provided smart contracts has revealed several highly critical vulnerabilities. The details, location, mechanism, and impact of each vulnerability are documented below.

---

## Uninitialized Memory Read leading to Erroneous Slashed Logic in `SurplusGuildMinter.sol`
- **Location:** `SurplusGuildMinter.sol` : `getRewards`
- **Mechanism:** In `getRewards`, the contract evaluates whether a term has historically suffered a loss that has not yet been applied to the current user. To do so, it compares `lastGaugeLoss` with the user's `userStake.lastGaugeLoss`. However, this check is executed *before* the contract actually loads the state from storage into the returned `userStake` memory variable:
```solidity
        lastGaugeLoss = GuildToken(guild).lastGaugeLoss(term);
        if (lastGaugeLoss > uint256(userStake.lastGaugeLoss)) {
            slashed = true;
        }

        // if the user is not staking, do nothing
        userStake = _stakes[user][term];
```
Because `userStake` is a named output memory parameter in the function signature `returns (uint256 lastGaugeLoss, UserStake memory userStake, bool slashed)`, it is initialized as all-zero fields at the beginning of the call. Thus, `userStake.lastGaugeLoss` is always evaluated as `0`. Therefore, if a loss has ever occurred historically in the gauge (`lastGaugeLoss > 0`), the `slashed` flag is erroneously set to `true`.
- **Impact:** As soon as any gauge suffers even a single loss (setting `lastGaugeLoss[term] > 0`), any user who tries to interact with `SurplusGuildMinter` for that term (such as calling `stake()`, `unstake()`, or `getRewards()`) will be falsely processed as "slashed". Their entire staked CREDIT balance and GUILD rewards are instantly set to zero. This results in the complete loss of all user-staked funds and permanently bricks the staking module's usability for that term.

---

## Insufficient Permission/Access Control Revert in `LendingTermOffboarding.sol` Bricking PSM Redemptions
- **Location:** `LendingTermOffboarding.sol` : `cleanup`
- **Mechanism:** The `cleanup` function attempts to revoke the protocol permissions of an offboarded lending term:
```solidity
        // update protocol config
        core().revokeRole(CoreRoles.RATE_LIMITED_CREDIT_MINTER, term);
        core().revokeRole(CoreRoles.GAUGE_PNL_NOTIFIER, term);
```
In `Core.sol`, the admin of both `RATE_LIMITED_CREDIT_MINTER` and `GAUGE_PNL_NOTIFIER` is set to `CoreRoles.GOVERNOR`:
```solidity
        _setRoleAdmin(CoreRoles.RATE_LIMITED_CREDIT_MINTER, CoreRoles.GOVERNOR);
        _setRoleAdmin(CoreRoles.GAUGE_PNL_NOTIFIER, CoreRoles.GOVERNOR);
```
According to OpenZeppelin's `AccessControl` implementation, `revokeRole` can only be successfully executed by an account holding the admin role of the target role (in this case, `CoreRoles.GOVERNOR`). However, `LendingTermOffboarding` does not hold the `GOVERNOR` role, and standard system security architecture prevents granting the all-powerful `GOVERNOR` role to minor auxiliary helper contracts. Thus, calling the public `cleanup` function will always fail and revert due to unauthorized access control.
- **Impact:** The system can never successfully clean up any offboarded terms. Because `cleanup` always reverts, `nOffboardingsInProgress` can never be decremented back to 0, which keeps SimplePSM redemptions permanently paused (`SimplePSM(psm).redemptionsPaused() == true` forever), permanently locking up users' ability to redeem their CREDIT tokens.

---

## State Tracker Desynchronization resulting in Irreversibly Paused PSM Redemptions
- **Location:** `LendingTermOffboarding.sol` : `offboard` and `cleanup`
- **Mechanism:** When a lending term poll succeeds, `offboard()` is called, incrementing `nOffboardingsInProgress` and pausing PSM redemptions if it is the first offboarding. When the term's loans are fully closed, `cleanup()` is meant to be called to set `canOffboard[term] = false` and decrement `nOffboardingsInProgress`.
However, if a term is offboarded and subsequently re-onboarded (via `LendingTermOnboarding`) *before* `cleanup()` is called, the value of `canOffboard[term]` remains `true` and `nOffboardingsInProgress` remains incremented. Since it is live again, users can call `offboard()` a second time without a new poll. This second call to `offboard()` will succeed and increment `nOffboardingsInProgress` again (e.g., from 1 to 2).
When all loans are finally closed, `cleanup()` can only be called once, because the very first execution sets `canOffboard[term] = false`, and any subsequent calls will fail the `require(canOffboard[term])` check. Thus, `nOffboardingsInProgress` cannot be decremented twice, leaving it permanently high (at at least 1).
Additionally, because the term is now a deprecated gauge, a new offboard poll cannot be proposed to reset the state, because `proposeOffboard()` requires the term to be an active gauge.
- **Impact:** A term going through re-onboarding and subsequent offboarding will permanently desynchronize `nOffboardingsInProgress` to be strictly greater than 0, resulting in the PSM redemptions being permanently and irreversibly paused, preventing any further capital redemptions from the protocol.

---

## Division-by-
