# Audit: 2025-04-forte

Here are the vulnerabilities found in the codebase.

## Integer Underflow in Exponent Evaluation Leads to Floating Point Wrap-Around
- Location: `src/Float128.sol` : `add`, `sub`, `mul`, `div`
- Mechanism: The library executes integer arithmetic directly on the unsigned string format of unpacked exponents without validating bounds to prevent `uint` underflow. When dealing with extremely small floats, removing precision or padding values forces underflows. For example, in `Float128.add`, intermediate results compute `r := sub(aExp, shl(EXPONENT_BIT, MAX_DIGITS_M))`. Since `aExp / bExp` is simply `encoded_offset_exponent << 242`, an input with an un-offset exponent below `-8154` (offset exponent `< 38`) will cause `r` to massively underflow as a `uint256`. Its topmost bits flip to `1`. The subsequent `rExp := shr(EXPONENT_BIT, r)` shift treats this as an astronomically large exponent field (e.g., `16356`), fooling threshold checks like `lt(rExp, maxExp)`. L-flag transitions append the wrapped integer top-bits correctly into the exponent mask, completely breaking IEEE parity and turning `< 1e-8154` scale operations into enormously positive exponents like `+8168`. Similar uncontrolled behavior manifests in `mul` and `div` on `aExp + bExp / aExp - bExp` routines.
- Impact: A malicious actor can supply carefully chosen microscopic numeric dust (e.g. manipulating protocol accounting using `1e-8192`) causing internal operations that should approximate to zero to wrap into virtually infinite float representations. An attacker can leverage this mathematical inversion to drain liquidity pools, mint massive numbers of shares, or manipulate algorithmic reserves.

## Missing Normalization on Extreme Lower Bounds Causes Silent Truncation 
- Location: `src/Float128.sol` : `mul`
- Mechanism: In the initial extraction and validation phase of `mul()`, `aExp` and `bExp` offsets can fall precisely causing `rExp := sub(add(shr(EXPONENT_BIT, aExp), shr(EXPONENT_BIT, bExp)), ZERO_OFFSET)` to underflow into maximum `uint` values when `shr(...) + shr(...)` is fundamentally smaller than `8192` (`ZERO_OFFSET`). Without strict reversion blocks on valid underflow, the fallback logic misclassifies the float as a multi-digit truncation issue causing it to push wrapped parameters directly into the returned struct.
- Impact: The protocol interprets standard near-zero underflows (which should round to zero or revert) as extremely huge positive float entities in math, facilitating system draining via multiplication against fractional attacker inputs.
