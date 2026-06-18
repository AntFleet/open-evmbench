# Audit: 2024-05-loop

## Broken calldata decoding allows arbitrary exchange proxy calls

- **Location:** `src/PrelaunchPoints.sol` : `_validateData`, `_decodeUniswapV3Data`, `_decodeTransformERC20Data`
- **Mechanism:** The contract relies on `_validateData` to ensure that the `_data` supplied by a user during a non‑ETH `claim` exactly matches the intended swap (correct input token, output ETH, amount, and recipient). To do this it decodes fields from `_data` using inline assembly. The assembly assumes `_data.offset` points directly to the selector of the exchange‑proxy call, but in Solidity a `bytes calldata` argument is ABI‑encoded with a 32‑byte *length* prefix at that offset. Consequently every offset computed (`p+4`, `p+36`, `p+64`, …) reads from a completely wrong section of calldata. An attacker can set the length of `_data` so that its first 4 bytes equal the expected selector and can place other required values (amount, recipient) at the mis‑aligned reads, making the checks pass. The validated `_data` is later executed unchanged via `exchangeProxy.call{value: 0}(_data)`.
- **Impact:** Any user who has locked a non‑ETH token can call `claim` with a malicious `_data` that passes validation. The subsequent `_fillQuote` will grant the attacker’s chosen input‑token allowance to the exchange proxy and then invoke the proxy with attacker‑controlled calldata. This can cause the proxy to transfer the approved tokens directly to the attacker, or to swap them and send the resulting ETH to an attacker‑controlled address, stealing all funds associated with that token lock.

## `_claim` uses entire ETH balance instead of swap proceeds

- **Location:** `src/PrelaunchPoints.sol` : `_claim` (non‑ETH branch)
- **Mechanism:** After a token‑to‑ETH swap (`_fillQuote`), the code sets `claimedAmount = address(this).balance`. It does not measure only the ETH obtained from the swap (e.g., balance‑before minus balance‑after). The contract has a payable `receive()` function, so anyone can donate ETH to it at any time. If any ETH is already sitting in the contract, a caller will receive that ETH as lpETH in addition to the swap proceeds.
- **Impact:** An attacker can front‑run a `claim` transaction with a dust ETH donation, forcing the claimer to mint extra lpETH that is not backed by the token swap. This inflates the lpETH supply at the expense of the donor (or of previously deposited ETH) and can be used to manipulate the staking economics or to “steal” value that belongs to the contract.
