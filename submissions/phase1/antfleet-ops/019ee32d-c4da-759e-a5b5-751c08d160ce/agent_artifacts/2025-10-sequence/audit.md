# Audit: 2025-10-sequence

validateUserOp`**.

Let's look at `DelegateCallNotAllowed` in `Guest.sol`:
```solidity
      if (call.delegateCall) {
        revert DelegateCallNotAllowed(i);
      }
```
Yes, this prevents delegatecalls inside the `Guest` fallback, which is secure.

Wait! What about `Implementation.sol`?
```solidity
  function _setImplementation(
    address _imp
  ) internal {
    assembly {
      sstore(address(), _imp)
    }
  }
```
Is `address()` a safe storage slot for the implementation in a proxy?
Wait! `address()` is the address of the contract itself!
If the contract is deployed at address `0x1234...5678`, then the storage slot used is `0x1234...5678`.
Is it possible for another contract/storage variable to use `address()` as its slot?
In standard Solidity, state variables are allocated sequentially starting from slot 0.
So unless there are over $10^{48}$ state variables, slot `0x1234...5678` (which is a massive 160-bit number) will never be reached by sequential allocation!
What about mappings?
Mappings use `keccak256(key, slot)` to calculate the storage slot. Heuristically, the probability of a mapping slot colliding with `address()` is $1/2^{256}$, which is negligibly small.
So storing the implementation at `address()` slot is extremely safe against collisions with other state variables.
But wait! Is there any other place where `sstore(address(), ...)` is called?
No, only in `_setImplementation`.
But wait! In `getImplementation`:
```solidity
  function _getImplementation() internal view returns (address _imp) {
    assembly {
      _imp := sload(address())
    }
  }
```
This is correct.

Let's look at `BaseSig.sol` where signatures are parsed.
Is there any risk of signature replay or bypass?
```solidity
  function recover(
    Payload.Decoded memory _payload,
    bytes calldata _signature,
    bool _ignoreCheckpointer,
    address _checkpointer
  ) internal view returns (uint256 threshold, uint256 weight, bytes32 imageHash, uint256 checkpoint, bytes32 opHash) {
```
And inside `recoverBranch`:
```solidity
        // Signature Sapient (0x09)
        if (flag == FLAG_SIGNATURE_SAPIENT) {
          ...
          bytes32 sapientImageHash = ISapient(addr).recoverSapientSignature(_payload, _signature[rindex:nrindex]);
          rindex = nrindex;

          // Add the weight and compute the merkle root
          weight += addrWeight;
          bytes32 node = _leafForSapient(addr, addrWeight, sapientImageHash);
          root = root != bytes32(0) ? LibOptim.fkeccak256(root, node) : node;
          continue;
        }
```
Wait! Look at `FLAG_SIGNATURE_SAPIENT_COMPACT` (0x0A):
```solidity
        // Signature Sapient Compact (0x0A)
        if (flag == FLAG_SIGNATURE_SAPIENT_COMPACT) {
          ...
          bytes32 sapientImageHash =
            ISapientCompact(addr).recoverSapientSignatureCompact(_opHash, _signature[rindex:nrindex]);
          ...
```
Wait! `_opHash` is passed to `recoverSapientSignatureCompact`.
And what is `_opHash`?
`_opHash = _payload.hash();`
And inside `recover`:
`opHash = _payload.hash();`
Wait! Is `_opHash` unique to the wallet?
Let's look at `Payload.hash`:
```solidity
  function hash(
    Decoded memory _decoded
  ) internal view returns (bytes32) {
    bytes32 domain = domainSeparator(_decoded.noChainId, address(this));
    bytes32 structHash = toEIP712(_decoded);
    return keccak256(abi.encodePacked("\x19\x01", domain, structHash));
  }
```
Yes, `address(this)` is included in `domainSeparator`!
```solidity
  function domainSeparator(bool _noChainId, address _wallet) internal view returns (bytes32 _domainSeparator) {
    return keccak256(
      abi.encode(
         ...
        _noChainId ? uint256(0) : uint256(block.chainid),
        _wallet
      )
    );
  }
```
But wait! What if `_payload.noChainId` is `true`?
Then `chainId` is omitted. But `_wallet` (which is `address(this)`) is still included in `domainSeparator`!
Wait, but what if we look at `FLAG_SIGNATURE_ANY_ADDRESS_SUBDIGEST` (0x08)?
```solidity
        // Signature Any address subdigest (0x08)
        // similar to subdigest, but allows for counter-factual payloads
        if (flag == FLAG_SIGNATURE_ANY_ADDRESS_SUBDIGEST) {
          ...
          bytes32 hardcoded;
          (hardcoded, rindex) = _signature.readBytes32(rindex);
          bytes32 anyAddressOpHash = _payload.hashFor(address(0));
          if (hardcoded == anyAddressOpHash) {
            weight = type(uint25
