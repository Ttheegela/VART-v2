# Key verification resolutions (holdout pack)

The answer keys next to this file (vsq-a.yaml, mvsp-b.yaml) are derived from the fact sheet by code
(`python -m datakit.derive_key holdout`). A fresh blind reader answered all 89 questions (64 in VSQ-A, 25 in MVSP-B)
from the documents alone, without the fact sheet, the keys or the trap rules. `python -m datakit.compare diff` listed
where its label or value differed from the key: 83 of 89 agreed. The six disagreements are decided below. Three
source fixes (VSQ-49, VSQ-56, MVSP-3.3) were re-verified by a fresh blind reader; the `compare diff` lines for
VSQ-49 and MVSP-3.3 still show the first verifier's answers to the old text.

## VSQ-10 (leaver access removed within 24 hours)

- Key: partial / Partial. Evidence: access control standard "...removed on the day a person leaves, and in any case
  within 24 hours." (yes) and SOC 2 "For 3 of 40 leavers sampled, access was removed 4 days after the leaving date."
  (partial).
- Verifier: conflict. "Policy 24h; SOC 2 exception shows 4 days for 3 of 40."
- Decision: key stands.
- Fix: none. Spec 6.7 rule 6 needs a `no` stance for a conflict. The SOC 2 sentence reports exceptions in a sample
  (37 of 40 were on time), so it is partly met, and yes plus partial is partial.

## VSQ-35 (most recent pentest findings remediated)

- Key: partial / Partial. Evidence: "One high-severity finding and one medium-severity finding remain open as of the
  report date."
- Verifier: verified / No. "High and medium findings remain open."
- Decision: key stands.
- Fix: none. The report also says both low findings were fixed and confirmed, so "not remediated" overstates it:
  some findings are remediated and the most serious are not, which is partial.

## VSQ-49 (each vendor assessed at least annually)

- Re-verified by a fresh blind reader.

- Key: verified / Yes. Its evidence said "Every vendor with access to customer data is assessed...".
- Verifier: partial. "Only vendors with customer data access."
- Decision: the document was ambiguous. The question asks about each vendor and the sentence covers a subset, so Yes
  was not supported by the text. Fix the source.
- Fix: supplier-risk-policy.docx (src/vrm.md) now says "Marrowgate assesses the security risk of each vendor at least
  once a year." Statement vrm-vendor-assessment in facts.yaml has the same text. Key stays verified / Yes with the new
  quote. Re-verified by a fresh blind reader.

## VSQ-56 (inventory of information assets)

- Re-verified by a fresh blind reader.

- Key: partial / Partial. Its only evidence was the draft asset lifecycle policy (draft ceiling).
- Verifier: verified / Yes. "Infrastructure register kept."
- Decision: the fact sheet registered the wrong stance. The dated infrastructure register is a real inventory of
  accounts, laptops and SaaS, so the truth is not "draft policy only", and the control had no registered evidence from
  it. Fix the fact sheet.
- Fix: facts.yaml registers the register's first row (ainv-inventory, control asset-inventory, stance yes) and the
  control truth now names the register. VSQ-56 re-derived as verified / Yes with two citations (amp draft, ainv).
  The draft-only trap minimum is unaffected (R1 and R2 carry it). The verifier's answer now agrees.

## MVSP-2.4 (password policy such as a minimum length)

- Key: verified / Yes. Evidence: "Passwords for workforce accounts must be at least 16 characters long."
- Verifier: partial. "Length rule for workforce accounts only."
- Decision: key stands by derivation; known limit. password-standard is shared with VSQ-12 (employee accounts, which
  the same sentence fully answers), and the only password rule is workforce-only, so a correct engine "partial" on
  MVSP-2.4 counts as a miss. The holdout score is pessimistic here, never flattering.
- Fix: none. An attempt to widen the sentence to customer accounts was reverted: it contradicted the standard's own
  internal-systems scope (a fresh blind reader caught it). An attempt to derive partial was dropped because it
  flipped VSQ-12 too. Source and facts are as in the first commit minus any customer claim.

## MVSP-3.3 (developer training on five vulnerability classes)

- Re-verified by a fresh blind reader.

- Key: verified / Yes. Its evidence named injection, cross-site scripting and authorization flaws.
- Verifier: partial. "Covers injection, XSS, authorization; not CSRF or sessions."
- Decision: the document was ambiguous. The question lists five classes and the sentence covered three. Fix the source.
- Fix: people-security-policy.docx (src/hrp.md) now says "...training every year that covers authorization bypass,
  session management, injection, cross-site scripting and cross-site request forgery." Same text in the
  hrp-developer-training statement. Key stays verified / Yes. Re-verified by a fresh blind reader.
