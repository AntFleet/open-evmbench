# Audit: 2024-05-arbitrum-foundation

## ERC20Inbox allows theft of native tokens held by the inbox contract

- **Location:** `ERC20Inbox.sol` : `_deliverToBridge`
- **Mechanism:** The function `_deliverToBridge` checks if the inbox’s own balance of the native token is less than the `tokenAmount` being sent to the bridge. If it is, it transfers the difference from `msg.sender`. If the inbox already holds enough tokens (e.g. from a previous direct transfer or a pre‑funding design), no tokens are taken from the caller, yet the bridge still pulls `tokenAmount` from the inbox. This means any tokens sitting in the inbox contract can be used to pay for messages initiated by any caller, effectively stealing those tokens from whoever deposited them.
- **Impact:** An attacker can call `depositERC20` or `createRetryableTicket` with `tokenAmount` equal to the inbox’s current balance. The inbox will pay the bridge using its own tokens while the attacker receives the corresponding L2 credit (e.g. a deposit or a retryable ticket) without providing any tokens themselves. The inbox balance is drained, causing loss to the rightful depositors.

---

## Missing chain‑ID check in several Inbox functions allows replay after L1 fork

- **Location:** `AbsInbox.sol` : `sendUnsignedTransaction`, `sendContractTransaction`, `depositEth` (and inherited functions in `Inbox.sol` and `ERC20Inbox.sol`)
- **Mechanism:** The `sendL2Message` function reverts when the chain ID has changed (`_chainIdChanged()`), but other message‑creation functions (`sendUnsignedTransaction`, `sendContractTransaction`, `depositEth`, `depositERC20`, etc.) do not perform this check. In the event of a hard fork that changes the L1 chain ID, these functions would remain callable on the new chain, allowing a transaction that was already sent on the old chain to be replayed without any chain‑specific replay protection.
- **Impact:** An attacker could replay a previously submitted message (e.g. a deposit or an unsigned transaction) on the forked chain, causing double‑spending or unintended state changes on L2. The severity depends on the likelihood of a chain‑ID change, but the inconsistency is a logic error that breaks the intended fork‑protection.
