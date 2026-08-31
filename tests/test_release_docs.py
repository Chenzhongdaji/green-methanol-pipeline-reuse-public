from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DOCS = (
    "README.md",
    "DATA_AVAILABILITY.md",
    "CODE_AVAILABILITY.md",
    "RELEASE_STATUS.md",
    "LICENSE-DATA",
    "NOTICE.md",
    "CITATION.cff",
)
REPOSITORY_URL = "https://github.com/Chenzhongdaji/green-methanol-pipeline-reuse-public"


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_release_documents_describe_full_public_reproduction() -> None:
    texts = {name: _text(name) for name in RELEASE_DOCS}
    readme = texts["README.md"]
    data = texts["DATA_AVAILABILITY.md"]
    code = texts["CODE_AVAILABILITY.md"]
    status = texts["RELEASE_STATUS.md"]

    assert "full public reproducibility" in readme.casefold()
    assert "python scripts/reproduce.py --mode full" in readme
    assert "Figure 2e" in readme and "reproduced" in readme.casefold()
    assert "Figure 2e" in data and "reproduced" in data.casefold()
    assert "Figure 2e" in code and "reproduced" in code.casefold()
    assert "Figure 2e" in status and "reproduced" in status.casefold()
    for name, text in texts.items():
        assert "1.0.0" in text, name
        assert REPOSITORY_URL in text, name


def test_legacy_bounded_release_language_is_absent() -> None:
    texts = "\n".join(_text(name) for name in RELEASE_DOCS)
    legacy_markers = (
        "provisional candidate",
        "Level 1",
        "Level 2",
        "NOT_REPRODUCED",
        "rights-limited",
        "controlled or rights-limited",
        "panel e is withheld",
        "panel e remains withheld",
        "panel e restricted-map-not-released",
        "restricted network/map payload",
        "Figure 2e is withheld",
        "Figure 2e remains withheld",
    )
    lowered = texts.casefold()
    for marker in legacy_markers:
        assert marker.casefold() not in lowered, marker


def test_private_directory_is_the_sole_explicit_exclusion() -> None:
    readme = _text("README.md")
    data = _text("DATA_AVAILABILITY.md")
    notice = _text("NOTICE.md")
    for text in (readme, data, notice):
        assert "管道数据" in text
    assert "does not depend" in " ".join(readme.casefold().split())
    assert "does not depend" in " ".join(data.casefold().split())
    assert "only exclusion" in notice.casefold()


def test_figure_2e_has_public_input_commands_and_outputs() -> None:
    texts = "\n".join(_text(name) for name in RELEASE_DOCS)
    for token in (
        "data/figure_source/figure-02.csv",
        "scripts/build_figure_02.py --panel e",
        "figures/figure-02e.png",
        "figures/figure-02e.pdf",
        "analytical coordinates",
    ):
        assert token in texts, token


def test_data_availability_binds_registries_and_lawful_third_party_route() -> None:
    data = _text("DATA_AVAILABILITY.md")
    normalized = " ".join(data.split())
    for token in (
        "data/dataset_registry.csv",
        "data/output_registry.csv",
        "data/public_sources.csv",
        "data/external/maps/standard_map_gs2023_2767.json",
        "metadata-only",
        "official acquisition route",
        "lawful derived carrier",
        "third-party",
    ):
        assert token in normalized, token
    assert "raw payload" not in normalized.casefold()


def test_data_license_has_a_narrow_explicit_allowlist() -> None:
    license_text = _text("LICENSE-DATA")
    assert "Creative Commons Attribution 4.0 International" in license_text
    assert "https://creativecommons.org/licenses/by/4.0/" in license_text
    carriers = (
        "data/author_derived/figure2_aggregate_source.csv",
        "data/author_derived/terminal_gap_aggregate.csv",
        "figures/source_data/figure-01.csv",
        "figures/source_data/figure-03.csv",
        "figures/source_data/figure-04.csv",
        "figures/source_data/figure-05.csv",
        "qa/expected/headline_claims.csv",
        "figures/panel_map.csv",
    )
    for carrier in carriers:
        assert f"`{carrier}`" in license_text, carrier
    assert "public-source" in license_text.casefold()
    assert "third-party" in license_text.casefold()
    assert "not covered" in license_text.casefold()
    assert "data/raw/" not in license_text
    assert "data/external/" not in license_text


def test_citation_binds_the_current_repository_and_code_version_without_archive_fields() -> None:
    citation = _text("CITATION.cff")
    assert 'title: "Green methanol pipeline reuse: full public reproducibility release"' in citation
    assert "version: 1.0.0" in citation
    assert f'repository-code: "{REPOSITORY_URL}"' in citation
    assert "license: MIT" in citation
    assert re.search(r"(?im)^\s*doi\s*:", citation) is None
    assert re.search(r"(?im)^\s*(?:date-released|url|accession)\s*:", citation) is None


def test_obsolete_controlled_registers_are_removed() -> None:
    assert not (ROOT / "data/controlled_inputs_metadata.csv").exists()
    assert not (ROOT / "data/dictionaries/controlled_inputs.md").exists()


def test_release_docs_do_not_disclose_machine_local_paths() -> None:
    local_path = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|(?<![A-Za-z0-9])/(?:home|Users|root)/")
    for name in RELEASE_DOCS:
        assert local_path.search(_text(name)) is None, name
