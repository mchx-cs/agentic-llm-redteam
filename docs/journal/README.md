# Journal

The project's dated record: what was built  what was measured  what broke  and
what a defect taught. **Each entry is true of its date and none is rewritten**
— the same reason the 91 original French commits and the 18 sealed audit
trails are not rewritten. A reader meeting a figure here reads a date  never
an inconsistency.

So this is the half of the documentation that does **not** rot. The state of
the project NOW is in [`CLAUDE.md`](../../CLAUDE.md)  which goes stale in
silence at every commit that does not touch it  and is therefore kept to a
screen and guarded by tests.

## What lives here

One file per working day  because the journal is a single month and a
month-sized file would be 11 155 lines — navigable by nobody. A
second month adds its own section to this table.

### 2026-11

| day | entries | lines |
|---|---|---|
| [2026-11-17](2026-11-17.md) | 1 | 77 |
| [2026-11-18](2026-11-18.md) | 8 | 653 |
| [2026-11-19](2026-11-19.md) | 18 | 1 708 |
| [2026-11-20](2026-11-20.md) | 7 | 857 |
| [2026-11-21](2026-11-21.md) | 1 | 71 |
| [2026-11-23](2026-11-23.md) | 3 | 439 |
| [2026-11-24](2026-11-24.md) | 14 | 1 088 |
| [2026-11-25](2026-11-25.md) | 11 | 1 521 |
| [2026-11-26](2026-11-26.md) | 15 | 1 574 |
| [2026-11-27](2026-11-27.md) | 32 | 3 167 |
| [2026-11-28](2026-11-28.md) | 2 | 303 |

**112 entries over 11 working days.**

## These files were MOVED  not rewritten

They lived in `CLAUDE.md` until 2026-11-28  where they were 69% of a 900 KB
file that an agent loads in full on every session. The split is **checkable
rather than asserted**: `tests/test_claude_md_structure.py` re-assembles every
day file in date order  prepends the preamble still held in `CLAUDE.md`  and
compares the result with

```
sha256  4860acb178b2fbaadb5d89af614be40ce7f06ce7752c0326887f141b8459e309
```

the digest of the 110 entries as they stood there. One byte of drift fails the suite. That
is the only form of "nothing was lost" that proves anything — re-reading the
result would prove nothing  and this project has recorded enough silent
defects to know that a re-read is not a proof.

## What stood above these entries until 2026-11-28

One thing was rewritten rather than moved: the paragraph that introduced the
entries inside `CLAUDE.md`. It opened on *"Everything below is dated"*, and
after the split nothing is below it — so keeping it verbatim there would have
left a false sentence in a section that describes the present. It is quoted
here instead, whole, because 745 bytes of explanation are worth preserving and
because *nothing was lost* should be checkable rather than claimed:

> **This file has TWO regimes of truth, and only one of them rots.** Everything
> below is dated: each entry is true of its date, none is rewritten — the same
> reason the 91 French commits and the 18 sealed trails are not rewritten. A
> reader meeting a figure here reads a date, never an inconsistency.
>
> The sections ABOVE describe the state NOW, so every sentence in them is a claim
> that goes stale in silence at each commit that does not touch it. That is why
> they are kept to a screen, why their figures carry executable guards, and why
> an addition to them should DISPLACE something rather than accumulate.
>
> Before this heading existed, these entries were filed under *What remains*,
> which promised the present and delivered 6,400 lines of history.
