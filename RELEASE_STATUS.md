# Release status

## Provisional public candidate

This tree is a manifest-closed Level-1 release candidate (`v1.0.0`; initial
candidate 2026-08-14, metadata rebound 2026-08-22). Its public development
repository is
<https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public>.
The repository is not yet a frozen archival release and has no release tag,
DOI or accession number. The private-development source fact `origin/main
d0c13d0` is recorded only for provenance; it is not the public release source.

The deterministic `FILE_MANIFEST.csv` excludes both generated inventory files.
`CHECKSUMS.sha256` includes the manifest and all payload files but excludes
itself, which closes the inventory without a checksum self-reference cycle.

## Manuscript binding

The candidate is bound to the current rev03 data/code manuscript and Supplementary
Information pair and their SHA-256 values in [MANUSCRIPT_SCOPE.md](MANUSCRIPT_SCOPE.md).
The authority DOCX files are not redistributed here.

## Included and excluded evidence

Author-generated aggregate source carriers cover Figures 1 and 3-5 and Figure
2 panels a-d and f-h. Figure 2 panel e remains withheld because its restricted
network/map payload and formal map review are not released.
Level 1 smoke reproduction, dictionaries, provenance metadata, and the
fail-closed audit are included. Level 2 full-network rerun remains
`NOT_REPRODUCED`: exact directed topology, facility mappings, candidate-link
geometry, map payloads, and third-party raw tables are excluded.

## Rights and author confirmation

Code and documentation are MIT-licensed. Only explicitly labelled
author-generated aggregate carriers are CC BY 4.0; public-source payloads,
controlled metadata, restricted inputs, and third-party material remain outside
that grant. The organizational citation `Research team` is used because
individual author metadata cannot be confirmed from this package. Author
confirmation is required before any public citation or archive deposition.

## Remaining publication gates

Authors must confirm the citation metadata, create and verify a frozen public
archive/release tag, assign a persistent identifier if required, and close
the owner/legal review and lawful access route for controlled inputs. Until
those external gates are completed, this development repository must not be
described as a DOI-backed archival release or as a Level 2 reproducibility
release.
