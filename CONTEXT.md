# MCRITweb

The web front-end for MCRIT. It presents and filters what the mcrit backend stores
and computes, and holds no analysis logic of its own.

## Borrowed from mcrit

Owned and defined by the [mcrit](https://github.com/danielplohmann/mcrit) backend.
Repeated here because MCRITweb renders them, not because this repo defines them —
when the backend's definition changes, this section follows.

**Family**:
A named group of Samples, the top tier of the storage hierarchy.

**Sample**:
One analysed binary, belonging to exactly one Family.

**Function**:
One disassembled function within a Sample. The unit that matching operates on.

**Query**:
A Sample matched against the collection without being stored in it, so investigating
a binary's similarities leaves the database unpolluted. Carries negative sample and
function IDs, shown with a `*` prefix.
_Avoid_: search query, uploaded sample, temporary sample

**Search**:
Finding stored Families, Samples or Functions by field-prefixed terms
(`family_name:foo`). Looks up what already exists; a Query matches something new
against it.
_Avoid_: query

**Job**:
An async unit of work on the backend. Identified by a `job_id`, which also keys
MCRITweb's result cache.

**PicHash** / **PicBlockHash**:
Position-independent hashes of a function and of a basic block. The hash comparison
is exact; the code match it implies is quasi-exact, since identical
position-independent bytes do not guarantee the same function.

**MinHash**:
A fuzzy similarity estimate for a Function, derived from shingled code features.

**Band**:
The LSH band used to generate match candidates. MCRITweb exposes the number required
as a fuzziness setting — Off (PicHash only), Fast (3), Standard (2), Complete (1).

**Library**:
A flag on a Family or Sample marking it as third-party or shared code, so its matches
can be discounted or reported separately.

**LinkHunt**:
The matches most likely to reveal a relationship *between* Families, extracted from a
matching result and clustered.

**Unique Blocks**:
Basic blocks occurring in a chosen Family or set of Samples and nowhere else in the
collection — the basis for a generated YARA rule.

### Matching methods

Backend concepts; the names on the left are MCRITweb's, used in the UI and the manual.

**Compare 1vsN** (`requestMatchesForSample`):
One stored Sample against the whole collection.

**Compare 1vs1** (`requestMatchesForSampleVs`):
Two stored Samples against each other.

**Cross-Compare** (`requestMatchesCross`):
A group of Samples against each other, producing a clustered similarity matrix.

**Query** (`requestMatchesForSmdaReport` and variants):
An uploaded binary matched 1vsN without being stored. See Query above.

## MCRITweb's own

**Role**:
A user's access level — pending → visitor → contributor → admin. Pending users are
registered but not yet admitted.

**Operation mode**:
Whether the instance serves one user or many. Governs whether registration is open.

**API token**:
Per-user secret authenticating a caller to MCRITweb's `/api` passthrough. Stored on
the user; every user has one.
_Avoid_: token

**Server token**:
A single shared secret authenticating MCRITweb itself to the mcrit backend, stored on
the server rather than the user. Optional and empty by default — the backend only
enforces it when its `AUTH_TOKEN` config is non-empty. Known as `AUTH_TOKEN` in
mcrit's config, sent in the `apitoken` HTTP header, and passed to `McritClient` as
`apitoken=` — none of which is the API token above.
_Avoid_: backend token, mcrit token, api token

**Registration token**:
An optional shared secret a new user must supply to register, used to keep an
internet-facing instance closed. Empty means registration is open. Unrelated to
either token above.
_Avoid_: invite code, signup token

**User filters**:
A user's stored defaults for filtering match results — score thresholds, library and
PIC exclusion, uniqueness.

**Column settings**:
A user's chosen columns and their order, per table.
