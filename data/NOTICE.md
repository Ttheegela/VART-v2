# Data notices

- **JupiterOne security-policy-templates** (https://github.com/JupiterOne/security-policy-templates, commit
  3b433626dbe1c355777ac9b7ff83805cdfa43dc9), CC BY-SA 4.0. The policies marked with a `source_template` in
  `data/*/facts.yaml` were adapted from these templates: placeholders filled for a fictional company, sentences
  rewritten or removed, planted inconsistencies added for evaluation. Changes were made.
- **Google VSAQ** (https://github.com/google/vsaq, commit 366d670e7e2a544166f74182e1093e6162786eb7), Apache-2.0.
  Questions are written for this project, informed by VSAQ items and MVSP controls; `source` names the closest VSAQ
  item or MVSP control, which for some topics is only adjacent.
- **MVSP** (https://github.com/vendorsec/mvsp, commit 2428bd529bdedec72d47cb3068a174cbfa4ced1a), CC0 1.0.
- **NIST CSF 2.0** subcategory identifiers (public domain, U.S. Government work).
- **NIST CSF 2.0 Reference Tool export** (https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all,
  retrieved on the date in `data/csf/source/csf-2.0-extract.json`), public domain (U.S. Government work). The extract
  keeps NIST's outcome identifiers, function and category names, outcome text and SP 800-53 Rev 5.2.0 references,
  verbatim; the export's other informative references (ISO/IEC, PCI, CCM and others) are not kept. `tier` and
  `question` in `data/csf/csf-2.0.json` are this project's.
