# Key verification resolutions

The answer keys next to this file (vsq-a.yaml, mvsp-b.yaml) are derived from the fact sheet by code
(`python -m datakit.derive_key dev`). To check that the rendered documents really support them, a fresh blind
reader answered all 89 questions (64 in VSQ-A, 25 in MVSP-B) from the documents alone. It never saw the fact
sheet, the keys or the plans. Its folder (`python -m datakit.compare prepare dev OUT`) held only the numbered
text of the 22 documents, a metadata table (kind, status, date, scope, evidence allowed) and the two question
lists, and it applied the decision rules of spec section 6.7 as its first prompt stated them (that prompt had one
mistake, noted below). `python -m datakit.compare diff` then listed where its label or value differed from the
key: 86 of 89 agreed (VSQ-A 62 of 64, MVSP-B 24 of 25). The three disagreements are decided below.

Future verifier prompts treat "planned" and "not yet" as no today. The first prompt listed them as partly-yes
cues, which caused the two VSQ disagreements: a control planned for later does not exist today.

## VSQ-36 (public bug bounty)

- Key: verified / No (honest negative H3). Evidence: SOC 2 "The Company does not currently operate a public bug
  bounty program." and FAQ "A public bug bounty program is planned for 2027."
- Verifier: partial / Partial. "SOC 2 says there is no public bug bounty now and the FAQ only says one is planned
  for 2027."
- Decision: key stands.
- Fix: none. Both quotes say no. A control planned for later does not exist today, and spec 6.7 rule 4 downgrades
  only a yes-stance quote on a negation-flagged passage. The verifier's prompt wrongly listed "planned" as a
  partly-yes cue.

## VSQ-38 (DAST)

- Key: verified / No (honest negative H4). Evidence: secure development policy "Dynamic application security
  testing (DAST) is not yet performed." and FAQ "DAST scanning is planned for the first quarter of 2027."
- Verifier: partial / Partial. "The policy says DAST is not yet performed and the FAQ says it is only planned for
  Q1 2027."
- Decision: key stands.
- Fix: none. Same reason as VSQ-36: both quotes say no, and "not yet" and "planned" describe a control that does
  not exist today.

## MVSP-2.2 (served only over HTTPS)

- Key: verified / Yes. Its only evidence was the cryptography policy sentence "Data in transit is encrypted using
  TLS 1.2 or higher."
- Verifier: unknown / none. "No document mentions HTTPS or HTTP-only serving; the TLS-in-transit statement is a
  related but different claim."
- Decision: the document was ambiguous. Encryption in transit does not say the application is served only over
  HTTPS, so the key was not supported by the text. Fix the source.
- Fix: data/dev/src/crypto.md now has the sentence "The Kestrelyn application is served only over HTTPS, and
  HTTP requests are redirected to HTTPS." as its own paragraph after the TLS sentence. It is registered in
  facts.yaml as statement crypto-https-only (doc crypto, control encryption-in-transit, stance yes).
  cryptography-policy.docx was re-rendered and both keys re-derived. VSQ-18 and MVSP-2.2 stay verified / Yes and
  gain the new quote as evidence; the tallies (Yes/No/Partial/Conflict/Unknown) are unchanged: VSQ-A 30/5/9/7/13,
  MVSP-B 17/1/1/0/6.
- Re-verified by a fresh blind reader: verified Yes, citing the new sentence (cryptography-policy.docx line 15).
  On the TLS sentence alone its reply was "related but a different topic, so I did not count it", the same
  judgement as before.
