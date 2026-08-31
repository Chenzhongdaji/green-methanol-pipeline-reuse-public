# Output registry dictionary

`data/output_registry.csv` maps each claimed manuscript output to the command
that generates it and the dataset identifiers it consumes. The output
registry is intentionally separate from the dataset registry so that output
execution can validate provenance before running a command.

| Column | Definition | Missing-value policy |
| --- | --- | --- |
| output_id | Stable identifier for one manuscript output. | Blank and duplicates forbidden. |
| manuscript_location | Human-readable figure or panel location in the manuscript. | Blank forbidden. |
| generation_command | Repository command, including its concrete output target. | Blank forbidden. The Figure 2 panel-e row must contain an output-targeting command. |
| input_dataset_ids | Semicolon-delimited identifiers of declared input carriers. | Nonempty; each identifier must be declared in `dataset_registry.csv`. |
| expected_artifact | Repository-relative expected output path. | Blank, unsafe or duplicate paths forbidden. |

The Figure 2 panel-e row uses `figure-02-aggregate-source` as an interim
public input and points to the Figure 2 builder's panel-e output target. Its
future detailed topology inputs are added by the dedicated Figure 2 build
task; the registry contract remains concrete in the interim.

The registry validator returns the number of declared datasets, output rows
and distinct datasets referenced by outputs. It does not require physical
carrier or artifact existence, allowing a later staging task to populate the
declared paths without changing the provenance contract.
