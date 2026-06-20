# Audit: 2024-05-arbitrum-foundation

## Broken Interactive Challenge Security via Timer Theft in Parent Edges

- **Location**: `src/challengeV2/libraries/EdgeChallengeManagerLib.sol` : `checkClaimIdLink` (called via `updateTimerCacheByClaim`)
- **Mechanism**: The helper function `checkClaimIdLink` validates the relationship between a parent edge (`edgeId`) and the claiming child edge (`claimingEdgeId`) before the parent inherits the child's unrivaled time. However, this validator only checks that the parent's `mutualId()` equals the child's `originId`, and that the child is exactly one level below:
  ```solidity
  function checkClaimIdLink(EdgeStore storage store, bytes32 edgeId, bytes32 claimingEdgeId, uint8 numBigStepLevel)
      private
      view
  {
      if (store.edges[edgeId].mutualId() != store.edges[claimingEdgeId].originId) {
          revert OriginIdMutualIdMismatch(store.edges[edgeId].mutualId(), store.edges[claimingEdgeId].originId);
      }
      if (nextEdgeLevel(store.edges[edgeId].level, numBigStepLevel) != store.edges[claimingEdgeId].level) {
          revert EdgeLevelInvalid(
              edgeId,
              claimingEdgeId,
              nextEdgeLevel(store.edges[edgeId].level, numBigStepLevel),
              store.edges[claimingEdgeId].level
          );
      }
  }
  ```
  It completely fails to verify that the child edge actually claims the specific parent edge (i.e. checking `store.edges[claimingEdgeId].claimId == edgeId`). Because all rival parent edges share the exact same `mutualId`, they also share the exact same child `originId`. Therefore, an attacker can create a dishonest rival parent edge and successfully call `updateTimerCacheByClaim` using an honest child edge that is actually claiming the honest rival parent.

- **Impact**: Attackers can hijack/steal the accrued unrivaled time from sub-challenges belonging to honest parent edges. This allows them to easily confirm dishonest or invalid parent assertions on-chain, bypassing the entire dispute resolution game and violating the Nitro rollup's core security invariants.

---

## Immutable `deployTimeChainId` Breaks Multi-Chain Proxies and Bypasses Force Inclusion Delay

- **Location**: `src/bridge/AbsInbox.sol` & `src/bridge/SequencerInbox.sol`
- **Mechanism**: Both the `AbsInbox` and `SequencerInbox` contracts use an upgradeable proxy pattern. However, they initialize the chain ID inside the constructor as an `immutable` variable:
  ```solidity
  uint256 internal immutable deployTimeChainId = block.chainid;
  ```
  Because `immutable` variables are evaluated at the implementation contract's deployment time and compiled directly into the logic bytecode rather than being stored in proxy storage, they return L1 deployment chain ID values (typically `1` for Mainnet) when executed via proxy `delegatecall` on other chains (L2/L3) or sidechains. This forces `_chainIdChanged()` to always evaluate to `true` on those home environments.

- **Impact**:
  - In `AbsInbox.sol`, standard L2 operations relying on `sendL2Message` are frozen because they always revert with `L1Forked()`. Meanwhile, users can permanently invoke unaliased fork methods (e.g. `sendUnsignedTransactionToFork`), bypassing L2 state aliasing security entirely.
  - In `SequencerInbox.sol`, any user can call `removeDelayAfterFork()` at any time. This permanently sets the sequencer force-inclusion parameters (`delayBlocks`, etc.) to `1`. Consequently, malicious users can immediately force-include transactions into the inbox, bypassing the sequencer's priority queues and enabling front-running, gas exploitation, and sequencer DoS.
