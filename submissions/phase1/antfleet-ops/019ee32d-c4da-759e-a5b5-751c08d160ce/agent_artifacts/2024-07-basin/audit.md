# Audit: 2024-07-basin


Wait, $7000/400 = 17$.
$xNew = 20 - (20 - 17)/3 = 20 - 1 = 19$.
5. $x = 19$.
   $t0 = 361$.
   $x \times t0 = 6859 < 7000$.
   $xNew = 19 + (7000/361 - 19)/3$.
   $7000/361 = 19$.
   $xNew = 19 + (19 - 19)/3 = 19$.
So it converges to 19!
Wait, what if $a0 = 7200$?
True root is $7200^{1/3} \approx 19.31$.
If $x = 19$:
$t0 = 361$.
$x \times t0 = 6859 < 7200$.
$7200 / 361 = 19$.
$xNew = 19$ (converges).

What if $a0 = 7500$?
True root is $7500^{1/3} \approx 19.57$.
If $x = 20$:
$t0 = 400$.
$x \times t0 = 8000 > 7500$.
$7500 / 400 = 18$.
$xNew = 20 - (20 - 18)/3 = 20 - 0 = 20$ (converged).
If $x = 19$:
$t0 = 361$.
$x \times t0 = 6859 < 7500$.
$7500 / 361 = 20$.
$xNew = 19 + (20 - 19)/3 = 19 + 0 = 19$ (converged).
Wait! If both 19 and 20 are stationary points, does it depend on where we start?
If we start at 10, it goes:
$10 \to 30 \to $ wait, let's trace $a0=7500$ starting at 10:
$10 \to 10 + (75 - 10)/3 = 10 + 21 = 31$.
$31 \to t0 = 961$. $7500/961 = 7$. $31 - (31 - 7)/3 = 31 - 8 = 23$.
$23 \to t0 = 529$. $7500/529 = 14$. $23 - (23 - 14)/3 = 23 - 3 = 20$ (converged to 20).
So it doesn't cycle.

But wait! What if $a0 = 5$?
If $n = 3$, $a0 = 5$.
Start at $x = 10$.
`t0 = 100`.
`7500` replaced by `5`.
`xNew = 10 - (10 - 0)/3 = 7`.
`xNew = 7 - (7 - 0)/3 = 5`.
`xNew = 5 - (5 - 0)/3 = 4`.
`xNew = 4 - (4 - 0)/3 = 3`.
`xNew = 3 - (3 - 0)/3 = 2`.
`xNew = 2 - (2 - 0)/3 = 2` (converges to 2).

Wait, let's try $a0 = 6$.
`xNew` goes to 2.
At `x = 2`, `t0 = 4`. `2 * 4 = 8 > 6`.
`xNew = 2 - (2 - 6/4)/3 = 2 - (2 - 1)/3 = 2 - 0 = 2` (converges).

What if we choose $n = 3$ and some other value of $a0$?
Is there any mathematical proof that this iteration can cycle?
Actually, let's look at:
`xNew = x - (x - a0 / t0) / n`
If `x - a0/t0 < n` and `a0/t0 < x`, then `(x - a0/t0) / n = 0`, so `xNew = x` and it converges.
If `a0/t0 - x < n` and `a0/t0 > x`, then `(a0/t0 - x) / n = 0`, so `xNew = x` and it converges.
So if `|x - a0/t0| < n`, it ALWAYS converges!
Wait, is it possible that `x` oscillates when `|x - a0/t0| >= n`?
But if `|x - a0/t0| >= n`, then the step size is non-zero, so `x` changes.
Since the function is monotonic and we have no negative values (everything is positive), the only way it could cycle is if it overshoots and lands on a previous value.
But because of the division by `n`, it behaves as a damped Newton method, which is very stable.
Wait, let's check if there is a known oscillation in the literature for this specific integer iteration:
$x_{k+
