import csv
import shutil
from pathlib import Path

import pytest

import green_methanol_release.inventory as inventory_module
from green_methanol_release.inventory import (
    DATASET_REGISTRY_FIELDS,
    EXPECTED_OUTPUT_IDS,
    MANIFEST_FIELDS,
    PUBLIC_SOURCE_FIELDS,
    write_release_inventories,
    load_public_sources,
    validate_inventory,
)


ROOT = Path(__file__).resolve().parents[1]


def _sandbox_inventory(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir(parents=True)
    for name in (
        "public_sources.csv",
        "dataset_registry.csv",
        "output_registry.csv",
    ):
        shutil.copy2(ROOT / "data" / name, data / name)
    return tmp_path


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_public_source_register_is_complete_and_non_redistributive():
    result = validate_inventory(ROOT)
    assert result["public_source_rows"] >= 37
    assert result["engineering_source_rows"] == 8


def test_public_registry_exposes_current_dataset_and_output_counts():
    result = validate_inventory(ROOT)
    assert result["dataset_rows"] == 40
    assert result["output_rows"] == 11
    assert result["referenced_dataset_rows"] == 17


def test_third_party_sources_are_not_cc_by_relicensed():
    result = validate_inventory(ROOT)
    assert result["third_party_cc_by_rows"] == 0


def test_connector_scenario_base_locator_matches_reviewed_source():
    row = next(
        row
        for row in load_public_sources(ROOT / "data" / "public_sources.csv")
        if row["source_id"] == "CONNECTOR-SCENARIO-BASE"
    )
    assert row["stable_url_or_doi"] == (
        "https://sthjt.shaanxi.gov.cn/xxgk/fdnr/zcwj/shpf/"
        "202602/t20260224_3614544.html"
    )


def test_cc_by_separator_variants_are_rejected_for_third_party_rows(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    rows[0]["licence_or_rights_status"] = "CC-BY-4.0"
    _write_rows(path, PUBLIC_SOURCE_FIELDS, rows)

    with pytest.raises(ValueError, match="third-party"):
        validate_inventory(root)


def test_author_derived_source_type_alias_cannot_claim_repository_cc_by(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    rows[0]["source_type"] = "author-derived aggregate"
    rows[0]["licence_or_rights_status"] = "CC BY 4.0"
    _write_rows(path, PUBLIC_SOURCE_FIELDS, rows)

    with pytest.raises(ValueError, match="third-party"):
        validate_inventory(root)


def test_inventory_rejects_extra_columns(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(*PUBLIC_SOURCE_FIELDS, "extra"),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "extra": "unexpected"})

    with pytest.raises(ValueError, match="columns"):
        validate_inventory(root)


def test_inventory_rejects_duplicate_identifiers(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "public_sources.csv"
    rows = _read_rows(path)
    rows[1]["source_id"] = rows[0]["source_id"]
    _write_rows(path, PUBLIC_SOURCE_FIELDS, rows)

    with pytest.raises(ValueError, match="duplicate"):
        validate_inventory(root)


def test_inventory_rejects_non_lowercase_digest(tmp_path: Path):
    root = _sandbox_inventory(tmp_path)
    path = root / "data" / "dataset_registry.csv"
    rows = _read_rows(path)
    rows[0]["sha256"] = "A" * 64
    _write_rows(path, DATASET_REGISTRY_FIELDS, rows)

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        inventory_module.load_dataset_registry(path)


def test_release_inventories_are_deterministic_and_exclude_self_reference(tmp_path: Path):
    root = _sandbox_inventory(tmp_path / "release")
    (root / "README.md").write_text("offline candidate\n", encoding="utf-8", newline="\n")
    first = write_release_inventories(root)
    first_manifest = (root / "FILE_MANIFEST.csv").read_bytes()
    first_checksums = (root / "CHECKSUMS.sha256").read_bytes()

    second = write_release_inventories(root)
    assert first == second
    assert first_manifest == (root / "FILE_MANIFEST.csv").read_bytes()
    assert first_checksums == (root / "CHECKSUMS.sha256").read_bytes()

    manifest_rows = list(csv.DictReader((root / "FILE_MANIFEST.csv").open(encoding="utf-8", newline="")))
    paths = [row["path"] for row in manifest_rows]
    assert tuple((root / "FILE_MANIFEST.csv").read_text(encoding="utf-8").splitlines()[0].split(",")) == MANIFEST_FIELDS
    assert paths == sorted(paths)
    assert "FILE_MANIFEST.csv" not in paths
    assert "CHECKSUMS.sha256" not in paths
    checksum_paths = [line.split("  ", 1)[1] for line in first_checksums.decode("utf-8").splitlines()]
    assert "FILE_MANIFEST.csv" in checksum_paths
    assert "CHECKSUMS.sha256" not in checksum_paths
    assert all(":" not in path and not path.startswith("/") for path in paths)


def test_data_licence_file_is_not_classified_as_mit(tmp_path: Path):
    root = _sandbox_inventory(tmp_path / "release")
    (root / "LICENSE").write_text("MIT License\n", encoding="utf-8", newline="\n")
    (root / "LICENSE-DATA").write_text("CC BY 4.0 terms\n", encoding="utf-8", newline="\n")
    write_release_inventories(root)

    rows = {
        row["path"]: row
        for row in csv.DictReader((root / "FILE_MANIFEST.csv").open(encoding="utf-8", newline=""))
    }
    assert rows["LICENSE"]["licence_scope"] == "MIT"
    assert rows["LICENSE-DATA"]["licence_scope"] == "CC BY 4.0 terms"


def test_figure2_aggregate_carrier_is_classified_as_cc_by(tmp_path: Path):
    root = _sandbox_inventory(tmp_path / "release")
    carrier = root / "data" / "author_derived" / "figure2_aggregate_source.csv"
    carrier.parent.mkdir(parents=True, exist_ok=True)
    carrier.write_text("panel,value\na,1\n", encoding="utf-8", newline="\n")
    write_release_inventories(root)

    rows = {
        row["path"]: row
        for row in csv.DictReader((root / "FILE_MANIFEST.csv").open(encoding="utf-8", newline=""))
    }
    assert rows["data/author_derived/figure2_aggregate_source.csv"]["licence_scope"] == "CC BY 4.0"


OUTPUT_REGISTRY_FIELDS = (
    "output_id",
    "manuscript_location",
    "generation_command",
    "input_dataset_ids",
    "expected_artifact",
    "secondary_artifacts",
)


def _write_registry(
    root: Path,
    dataset_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
) -> Path:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    _write_rows(data / "dataset_registry.csv", DATASET_REGISTRY_FIELDS, dataset_rows)
    _write_rows(data / "output_registry.csv", OUTPUT_REGISTRY_FIELDS, output_rows)
    return root


def _dataset_row(
    dataset_id: str = "dataset-1",
    public_path: str = "data/example.csv",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "dataset_id": dataset_id,
        "public_path": public_path,
        "role": "figure source",
        "origin": "author-generated",
        "access_route": "repository carrier",
        "license": "CC BY 4.0",
        "sha256": "a" * 64,
        "acquisition_command": "",
        "processing_command": "terminal source-data carrier",
        "manuscript_uses": "Figure 1",
        "source_relative_path": "",
        "stage_action": "existing",
    }
    row.update(overrides)
    return row


def _output_row(
    output_id: str = "figure-01",
    input_dataset_ids: str = "dataset-1",
    expected_artifact: str = "figures/figure-01.png",
    input_path: str = "data/example.csv",
    secondary_artifacts: str = "",
    **overrides: str,
) -> dict[str, str]:
    row = {
        "output_id": output_id,
        "manuscript_location": "Figure 1",
        "generation_command": (
            "python scripts/build_output.py --input "
            f"{input_path} --output {expected_artifact}"
        ),
        "input_dataset_ids": input_dataset_ids,
        "expected_artifact": expected_artifact,
        "secondary_artifacts": secondary_artifacts,
    }
    row.update(overrides)
    return row


def test_registry_headers_are_exact_and_utf8_lf():
    expected = {
        "data/dataset_registry.csv": DATASET_REGISTRY_FIELDS,
        "data/output_registry.csv": OUTPUT_REGISTRY_FIELDS,
    }
    for relative, fields in expected.items():
        raw = (ROOT / relative).read_bytes()
        assert b"\r" not in raw
        assert raw.splitlines()[0].decode("utf-8") == ",".join(fields)


def test_registry_loads_and_validates_current_counts():
    datasets = inventory_module.load_dataset_registry(ROOT / "data" / "dataset_registry.csv")
    outputs = inventory_module.load_output_registry(ROOT / "data" / "output_registry.csv")

    assert len(datasets) == 40
    assert sum(row["stage_action"] == "copy" for row in datasets) == 33
    assert sum(row["stage_action"] == "existing" for row in datasets) == 6
    assert sum(row["stage_action"] == "acquire" for row in datasets) == 1
    seed_ids = {
        "figure-01-source",
        "figure-02-aggregate-source",
        "figure-03-source",
        "figure-04-source",
        "figure-05-source",
        "model-parameters-v01",
    }
    assert {row["dataset_id"] for row in datasets if row["stage_action"] == "existing"} == seed_ids
    assert all(
        row["source_relative_path"] == "" or row["source_relative_path"] == f"source-id:{row['dataset_id']}"
        for row in datasets
        if row["stage_action"] in {"existing", "acquire"}
    )
    assert len(outputs) == 11
    assert inventory_module.validate_release_registry(ROOT) == {
        "datasets": 40,
        "outputs": 11,
        "referenced_datasets": 17,
    }


def test_dataset_registry_rejects_duplicate_ids(tmp_path: Path):
    root = _write_registry(
        tmp_path,
        [_dataset_row(), _dataset_row(dataset_id="dataset-1", public_path="data/other.csv")],
        [_output_row()],
    )

    with pytest.raises(ValueError, match="duplicate dataset_id"):
        inventory_module.load_dataset_registry(root / "data" / "dataset_registry.csv")


def test_output_registry_rejects_duplicate_ids(tmp_path: Path):
    root = _write_registry(
        tmp_path,
        [_dataset_row()],
        [_output_row(), _output_row(output_id="figure-01", expected_artifact="figures/other.png")],
    )

    with pytest.raises(ValueError, match="duplicate output_id"):
        inventory_module.load_output_registry(root / "data" / "output_registry.csv")


@pytest.mark.parametrize(
    "output_rows",
    [
        [],
        [
            _output_row(output_id=output_id)
            for output_id in EXPECTED_OUTPUT_IDS
            if output_id != "figure-02e"
        ],
    ],
)
def test_output_registry_requires_all_fixed_nonempty_output_ids(
    tmp_path: Path, output_rows: list[dict[str, str]]
):
    root = _write_registry(tmp_path, [_dataset_row()], output_rows)

    with pytest.raises(ValueError, match="all fixed output IDs"):
        inventory_module.load_output_registry(root / "data" / "output_registry.csv")


@pytest.mark.parametrize(
    "public_path",
    [
        "../outside.csv",
        "C:" + "/outside.csv",
        "/" + "outside.csv",
        "\\\\" + "server/share/outside.csv",
        "data/管道数据/secret.csv",
    ],
)
def test_dataset_registry_rejects_malformed_or_forbidden_paths(
    tmp_path: Path, public_path: str
):
    root = _write_registry(tmp_path, [_dataset_row(public_path=public_path)], [_output_row()])

    with pytest.raises(ValueError, match="path"):
        inventory_module.load_dataset_registry(root / "data" / "dataset_registry.csv")


def test_output_registry_rejects_malformed_expected_artifact_path(tmp_path: Path):
    root = _write_registry(
        tmp_path,
        [_dataset_row()],
        [_output_row(expected_artifact="../outside.png")],
    )

    with pytest.raises(ValueError, match="path"):
        inventory_module.load_output_registry(root / "data" / "output_registry.csv")


def test_dataset_registry_rejects_invalid_hash(tmp_path: Path):
    root = _write_registry(tmp_path, [_dataset_row(sha256="A" * 64)], [_output_row()])

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        inventory_module.load_dataset_registry(root / "data" / "dataset_registry.csv")


def test_dataset_registry_rejects_missing_required_field(tmp_path: Path):
    root = _write_registry(tmp_path, [_dataset_row(role="   ")], [_output_row()])

    with pytest.raises(ValueError, match="role"):
        inventory_module.load_dataset_registry(root / "data" / "dataset_registry.csv")


def test_release_registry_rejects_missing_dataset_reference(tmp_path: Path):
    root = _write_registry(
        tmp_path,
        [_dataset_row()],
        [_output_row(input_dataset_ids="dataset-missing")],
    )

    with pytest.raises(ValueError, match="dataset-missing"):
        inventory_module.validate_release_registry(root)


def test_release_registry_rejects_duplicate_expected_artifacts(tmp_path: Path):
    root = _write_registry(
        tmp_path,
        [_dataset_row(), _dataset_row(dataset_id="dataset-2", public_path="data/other.csv")],
        [
            _output_row(output_id="figure-01"),
            _output_row(
                output_id="figure-02",
                input_dataset_ids="dataset-2",
                input_path="data/other.csv",
            ),
        ],
    )

    with pytest.raises(ValueError, match="duplicate expected_artifact"):
        inventory_module.validate_release_registry(root)


def test_figure2e_has_concrete_generation_contract():
    row = next(
        row
        for row in inventory_module.load_output_registry(ROOT / "data" / "output_registry.csv")
        if row["output_id"] == "figure-02e"
    )
    assert row["input_dataset_ids"] == "figure-02-source-real"
    assert "data/figure_source/figure-02.csv" in row["generation_command"]
    assert row["generation_command"].strip()
    assert "--output" in row["generation_command"]
    assert row["expected_artifact"].endswith(".png")
    assert row["secondary_artifacts"] == "figures/figure-02e.pdf"
    assert not any(
        marker in row["generation_command"].casefold()
        for marker in ("withheld", "status", "not_reproduced")
    )


def test_output_registry_rejects_duplicate_or_unsafe_secondary_artifacts(
    tmp_path: Path,
):
    for secondary_artifacts in ("figures/figure-01.png", "../outside.pdf"):
        root = _write_registry(
            tmp_path / secondary_artifacts.replace("/", "_"),
            [_dataset_row()],
            [_output_row(secondary_artifacts=secondary_artifacts)],
        )
        with pytest.raises(ValueError, match="secondary_artifacts|artifact"):
            inventory_module.validate_release_registry(root)


@pytest.mark.parametrize(
    "mutation",
    [
        {"generation_command": ""},
        {"generation_command": "withheld"},
        {"generation_command": "status=NOT_REPRODUCED"},
        {"input_dataset_ids": "dataset-1"},
    ],
)
def test_release_registry_rejects_incomplete_figure2e_contract(
    tmp_path: Path, mutation: dict[str, str]
):
    output = _output_row(
        output_id="figure-02e",
        input_dataset_ids="figure-02-source-real",
    )
    output.update(mutation)
    root = _write_registry(
        tmp_path,
        [_dataset_row(dataset_id="figure-02-source-real")],
        [output],
    )

    with pytest.raises(ValueError, match="figure-02e"):
        inventory_module.validate_release_registry(root)


def test_output_commands_use_declared_inputs_and_exact_artifact_targets():
    assert inventory_module.validate_release_registry(ROOT) == {
        "datasets": 40,
        "outputs": 11,
        "referenced_datasets": 17,
    }


@pytest.mark.parametrize(
    "command",
    [
        "python scripts/build_output.py --input data/example.csv --output figures/other.png",
        "echo figures/figure-01.png",
        "python scripts/build_output.py --output figures/figure-01.png",
        "python scripts/build_output.py --input data/undeclared.csv --output figures/figure-01.png",
        "python scripts/build_output.py --input data/example.csv --input data/undeclared.csv --output figures/figure-01.png",
    ],
)
def test_release_registry_rejects_invalid_output_command_contract(
    tmp_path: Path, command: str
):
    root = _write_registry(
        tmp_path,
        [_dataset_row()],
        [_output_row(generation_command=command)],
    )

    with pytest.raises(ValueError, match="figure-01|generation_command|input"):
        inventory_module.validate_release_registry(root)


@pytest.mark.parametrize(
    "command",
    [
        "python scripts/build_figure_02.py --panel e --input data/example.csv --output figures/other.png",
        "python scripts/build_figure_02.py --panel e --output figures/figure-02e.png",
        "python scripts/build_figure_02.py --panel e --input data/undeclared.csv --output figures/figure-02e.png",
    ],
)
def test_release_registry_rejects_invalid_figure2e_command_contract(
    tmp_path: Path, command: str
):
    root = _write_registry(
        tmp_path,
        [_dataset_row(dataset_id="figure-02-source-real")],
        [
            _output_row(
                output_id="figure-02e",
                input_dataset_ids="figure-02-source-real",
                expected_artifact="figures/figure-02e.png",
                generation_command=command,
            )
        ],
    )

    with pytest.raises(ValueError, match="figure-02e|generation_command|input"):
        inventory_module.validate_release_registry(root)
