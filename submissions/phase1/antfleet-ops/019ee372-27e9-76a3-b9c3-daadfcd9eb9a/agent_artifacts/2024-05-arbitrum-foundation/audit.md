# Audit: 2024-05-arbitrum-foundation

An analysis of the contract codebase reveals the following genuine security vulnerability:

## EdgeStakingPool creates edge regardless of expected claimId
- Location: `src/assertionStakingPool/EdgeStakingPool.sol` : `createEdge`
- Mechanism: In `EdgeStakingPool.sol`, the pool checks that the newly created edge ID exactly matches the predefined `edgeId`. However, the calculation for `calculateEdgeId` (and by extension `idComponent`) for layer-zero edges incorporates the `originId`, the start/end roots, and heights, but **deliberately does not include the `claimId`** (which assertion is being claimed). For block-level edges, `originId` is defined as the *predecessor* assertion's hash. Sibling assertions (rival claims) naturally share the same predecessor, and would thus generate identical `originId`s.
- Impact: A malicious actor or griefer can take the valid parameters intended for an honest edge pool, but mutate the `args.claimId` to point to a competing (or invalid) sibling assertion that also has the same `endHistoryRoot` (due to an empty or non-state-mutating update, or simply because it's early in the disputable sequence where states haven't diverged). `EdgeStakingPool` will check the calculated `newEdgeId` and find it effectively matches `edgeId` (since `claimId` changes don't alter the `edgeId` hash) and blindly stake the pool's deposited funds in the challenge manager against the incorrect `claimId`. The pool effectively stakes its funds backing a potentially invalid assertion or rival, guaranteeing a loss of user funds.
