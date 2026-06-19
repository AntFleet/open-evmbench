# Audit: 2024-03-canto

# Security Audit Report

## Missing caller verification on `lzCompose`
- **Location:** `contracts/asd/asdRouter.sol` : `lzCompose`
- **Mechanism:** The `lzCompose` function is `external` and `payable` but performs no check that `msg.sender` is the LayerZero endpoint or a registered executor. Any EOA or contract can invoke it directly with a fully self‑constructed `_message`. The function then decodes attacker‑controlled compose data (`_cantoAsdAddress`, `_cantoRefundAddress`, `_feeForSend`, …) and processes it.
- **Impact:** A direct caller can drive the entire deposit → swap → mint → send pipeline using their own funds, and — more importantly — can specify a malicious `_cantoAsdAddress` so that the `_sendASD` branch hands the protocol's native fee to an arbitrary contract (see also "Untrusted external call in `_sendASD`"). It also lets an attacker grief the executor by forcing it down arbitrary code paths or causing reverts that must be handled by the endpoint.

---

## Unchecked ERC20 `transfer` return value in refunds
- **Location:** `contracts/asd/asdRouter.sol` : `_refundToken`
- **Mechanism:** The function calls `IERC20(_tokenAddress).transfer(_refundAddress, _amount)` and ignores the boolean return value. Tokens such as USDT, or any fee‑on‑transfer / blacklisted token, can make this call return `false` (or revert only inside `SafeERC20`'s optional path). Because the result is not checked, the refund silently fails and the function continues to emit `TokenRefund` and forward native value as if the refund succeeded.
- **Impact:** Users who should receive a refund of an unsupported or failing token permanently lose those tokens; the contract still pays out the native portion of the refund, so the protocol subsidises a failed refund.

---

## Hard‑coded 2300 gas `transfer()` for native refunds
- **Location:** `contracts/asd/asdRouter.sol` : `_refundToken`
- **Mechanism:** `payable(_refundAddress).transfer(_nativeAmount)` forwards native tokens with the EVM‑inherited 2300 gas stipend. Since `_refundAddress` is taken straight from the user‑controlled compose payload (`payload._cantoRefundAddress`) and can be any address — including a contract with a non‑trivial `receive`/`fallback` or one whose gas costs are inflated by chain state — the call can revert out of gas.
- **Impact:** Native refunds fail silently for contract recipients or after gas‑cost changes (e.g. post‑EIP‑1884 style chains), leaving the native value stuck in the router while the event logs a successful refund.

---

## Cross‑chain refund address used in same‑chain `transfer`
- **Location:** `contracts/asd/asdRouter.sol` : `_refundToken` (called from `lzCompose`)
- **Mechanism:** `_refundToken` performs plain `IERC20.transfer` and `payable.transfer` to `_refundAddress`. The comments and variable names make clear that `_refundAddress` is intended to be a Canto address — but the ASDRouter executes on whatever chain it was deployed on. There is no `require(msg.sender == endpoint)` and no `block.chainid` check, so the contract may be deployed on a chain other than Canto. In that case the "Canto refund address" is just an arbitrary EVM address on the router's chain.
- **Impact:** Refund flows either send tokens to an address the user does not control on the router's chain or revert; in either case the cross‑chain refund design is broken and tokens can be permanently lost or misdirected.

---

## Decimal underflow in `ASDUSDC.deposit` / `withdraw`
- **Location:** `contracts/asd/asdUSDC.sol` : `deposit`, `withdraw`, `recover`
- **Mechanism:** The scaling factor `10 ** (this.decimals() - ERC20(_usdcVersion).decimals())` is computed without checking the sign of the exponent. `asdUSDC` defaults to 18 decimals; if a whitelisted USDC version has more than 18 decimals (or simply returns a higher value from `decimals()`), the subtraction underflows in Solidity 0.8.x and the entire transaction reverts.
- **Impact:** Any whitelisted token with `decimals() > asdUSDC.decimals()` makes `deposit`, `withdraw`, and `recover` permanently unusable for that version, bricking that asset's integration. Because whitelisting is owner‑controlled, a single misconfiguration locks user funds.

---

## Fee‑on‑transfer / rebasing token accounting in `ASDUSDC`
- **Location:** `contracts/asd/asdUSDC.sol` : `deposit`
- **Mechanism:** `deposit` credits `usdcBalances[_usdcVersion] += _amount` and mints `asdUSDC` based on the *input* `_amount`, never measuring the actual balance change of the contract. For any token with a transfer fee, rebasing supply, or any other mechanism that delivers fewer tokens than `safeTransferFrom` requested, the contract records more underlying than it actually holds and issues more `asdUSDC` than justified.
- **Impact:** A depositor using such a token mints `asdUSDC` against value the contract never received. Subsequent withdrawers can drain the real USDC balance because `usdcBalances` is inflated, while the last withdrawers receive nothing — the classic "first‑in drains, last‑in reverts" loss pattern.

---

## Untrusted external call with value in `_sendASD`
- **Location:** `contracts/asd/asdRouter.sol` : `_sendASD`
- **Mechanism:** The function performs `payable(_payload._cantoAsdAddress).call{value: _payload._feeForSend}(abi.encodeWithSelector(IOFT.send.selector, …))`. `_payload._cantoAsdAddress` is decoded from the user‑controlled compose message, and no on‑chain check verifies that the target is a legitimate OFT contract, that it is deployed, or that it is non‑malicious. The native fee is forwarded before any post‑conditions are checked.
- **Impact:** Anyone who can influence the composed payload (a compromised composer on a peer chain, or a direct caller of `lzCompose`) can point `_cantoAsdAddress` at an attacker contract that accepts the native fee, returns success, and never actually sends the ASD — leaving the user's NOTE already swapped and the freshly minted ASD stuck (or moved by the attacker via the malicious contract). The native LayerZero fee is irrecoverably lost.

---

## `calcImpact` oracle used without slippage protection between read and write
- **Location:** `contracts/asd/asdRouter.sol` : `_swapOFTForNote`
- **Mechanism:** The router first calls `ICrocImpact.calcImpact` to assert that the swap will yield ≥ `_minAmountNote`, then performs the actual `swap` in a separate call. `calcImpact` is a view function over the live pool state; between the two calls the pool can be moved by a searcher who sandwiches the composed message in the mempool (the entire `lzCompose` is a single user‑submitted tx, but the router contract is observable and its destination pool is a known, low‑liquidity Ambient pool).
- **Impact:** A searcher can push the pool price against the trade after `calcImpact` reads it. The actual swap then either reverts (consuming the user's compose fee and forcing a refund path that itself has the bugs above) or, worse, the `minOut` passed into the real `swap` is `_minAmountNote`, which is the user‑specified floor — so MEV extraction is possible whenever the user sets a generous `_minAmountASD`. The `calcImpact` check is effectively redundant with the swap's `minOut` and provides no additional security guarantee.

---

## `withdrawCarry` sends all accrued interest to a single owner
- **Location:** `contracts/asd/asdOFT.sol` : `withdrawCarry`
- **Mechanism:** `withdrawCarry` is `onlyOwner` and sends the entire excess NOTE (interest earned on cNOTE minus the 1:1 redemption buffer) directly to `msg.sender`. There is no timelock, no multisig requirement, no event before the transfer, and no cap per call. The owner key effectively controls a continuously growing pool of NOTE.
- **Impact:** Owner key compromise (or a malicious/rug‑pulling deployer) lets the attacker drain all accrued carry in a single transaction. Because there is no pending‑withdraw pattern or timelock, the action is irreversible once mined.

---

## Missing approval before `IOFT.send` in `_sendASD`
- **Location:** `contracts/asd/asdRouter.sol` : `_sendASD`
- **Mechanism:** Before calling `IOFT.send` on `_payload._cantoAsdAddress`, the router never approves the OFT contract to spend the ASD it just minted to itself. Standard OFT `send` implementations pull tokens via `transferFrom(msg.sender, address(this), amount)`, which requires the caller (the router) to have granted an allowance.
- **Impact:** Every cross‑chain send path will revert inside `send`, the router will fall into the `_refundToken` branch, and the user's NOTE is already gone — the ASD mint was non‑reversible by the time the failure surfaces. Combined with the refund bugs above, this means users systematically lose value on the non‑Canto destination path.

---

## `lzCompose` does not validate compose message source or payload
- **Location:** `contracts/asd/asdRouter.sol` : `lzCompose`
- **Mechanism:** Beyond the missing caller check, the function trusts every field of the decoded `OftComposeMessage`. The check `composeMsg.length != 224` is the only structural validation; the contained addresses, EID, and fee values are used as‑is. There is no allow‑list of acceptable source chains, no check that `_cantoAsdAddress` matches the locally configured `cantoLzEID` mapping, and no check that `_feeForSend` is plausible.
- **Impact:** Combined with the other bugs, a malicious composer can redirect native fees, force the contract to interact with arbitrary contracts, and trigger the broken refund path at will. The router has no defense‑in‑depth against a compromised peer‑chain composer.

---

## Centralised, single‑key ownership over critical infrastructure
- **Location:** `contracts/asd/asdOFT.sol` (constructor), `contracts/asd/asdRouter.sol`, `contracts/asd/asdUSDC.sol`
- **Mechanism:** `asdOFT` sets `msg.sender` as the LayerZero delegate and `Ownable` owner. `ASDRouter` and `ASDUSDC` likewise use a single `Ownable`. The router owner can rewrite `crocSwapAddress`, `crocImpactAddress`, `asdUSDC`, `cantoLzEID`, and `noteAddress`. The `asdUSDC` owner can whitelist arbitrary tokens (interacting with the fee‑on‑transfer bug above) and call `recover` to mint `asdUSDC` against any tokens sent to the contract.
- **Impact:** A compromised owner key on any of the three contracts can substitute malicious implementations for the DEX, the OFT wrapper, or the USDC wrapper, enabling theft of all in‑flight and routed user funds. There is no timelock or multisig requirement to slow such an attack.
